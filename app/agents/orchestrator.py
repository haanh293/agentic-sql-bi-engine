import logging
import time
from typing import Any, Dict, List, Tuple
import httpx
from fastapi import HTTPException

from app.config import settings
from app.database.connection import execute_readonly_query, get_database_schema_ddl
from app.schemas.query_schema import (
    AgentStepTrace,
    NaturalQueryRequest,
    QueryExecutionResponse,
    SecurityAuditResult,
)
from app.security.ast_guard import ast_guard
from app.agents.schema_pruner import schema_pruner
from app.agents.sql_generator import sql_generator
from app.agents.self_healer import self_healer

logger = logging.getLogger("app.agents.orchestrator")


class AnalyticsOrchestrator:
    """
    Central State Machine coordinating the multi-agent Text-to-SQL workflow:
    Schema Pruning -> SQL Generation -> AST Security Guard -> Read-Only DB Execution ->
    Self-Healing Loop (max 3 attempts) -> Business Insight Summarization.
    """

    async def execute_analytics_workflow(
        self, request: NaturalQueryRequest
    ) -> QueryExecutionResponse:
        workflow_start = time.perf_counter()
        question = request.query.strip()
        traces: List[AgentStepTrace] = []

        # 1. Schema Pruning Step
        full_ddl = get_database_schema_ddl()
        pruned_schema = schema_pruner.prune_schema(question, full_ddl)

        # 2. Initial SQL Generation
        gen_start = time.perf_counter()
        current_sql = await sql_generator.generate_sql(question, pruned_schema)
        gen_time = (time.perf_counter() - gen_start) * 1000.0

        is_healed = False
        final_sql = current_sql
        final_columns: List[str] = []
        final_rows: List[Dict[str, Any]] = []

        # 3. State Machine Loop: AST Guard -> Execution -> Self-Healing
        max_attempts = settings.MAX_SELF_HEAL_ATTEMPTS

        for attempt in range(1, max_attempts + 1):
            step_start = time.perf_counter()
            logger.info("Starting execution attempt %d/%d for query: '%s'", attempt, max_attempts, question)

            # Step 3A: AST Security Inspection via sqlglot
            audit: SecurityAuditResult = ast_guard.audit_and_sanitize(current_sql)
            step_latency = (time.perf_counter() - step_start) * 1000.0

            if not audit.is_safe:
                # Security or syntax violation detected by AST
                violation_summary = " | ".join(audit.violations)
                logger.warning("[Attempt %d] AST Guard flagged violations: %s", attempt, violation_summary)

                if attempt < max_attempts:
                    healed_sql = await self_healer.heal_sql(
                        question=question,
                        failing_sql=current_sql,
                        error_message=f"AST Security Violation: {violation_summary}",
                        pruned_schema=pruned_schema,
                        attempt=attempt,
                    )
                    traces.append(
                        AgentStepTrace(
                            attempt=attempt,
                            step_name="AST_SECURITY_GUARD_REPAIR",
                            input_sql=current_sql,
                            ast_status="REJECTED",
                            db_error=violation_summary,
                            healed_sql=healed_sql,
                            execution_time_ms=round(step_latency, 2),
                        )
                    )
                    current_sql = healed_sql
                    is_healed = True
                    continue
                else:
                    traces.append(
                        AgentStepTrace(
                            attempt=attempt,
                            step_name="AST_SECURITY_GUARD_FAILED",
                            input_sql=current_sql,
                            ast_status="REJECTED",
                            db_error=violation_summary,
                            healed_sql=None,
                            execution_time_ms=round(step_latency, 2),
                        )
                    )
                    raise HTTPException(
                        status_code=400,
                        detail={
                            "error": "SECURITY_VIOLATION",
                            "message": f"Query blocked by AST Security Guard: {violation_summary}",
                            "traces": [t.model_dump() for t in traces],
                        },
                    )

            # AST Check Passed -> Target sanitized query
            executable_sql = audit.sanitized_sql or current_sql
            ast_status_label = "MODIFIED" if audit.limit_applied else "PASSED"

            # Step 3B: Database Execution on Read-Only Connection
            db_exec_start = time.perf_counter()
            try:
                columns, rows = execute_readonly_query(executable_sql)
                db_latency = (time.perf_counter() - db_exec_start) * 1000.0
                total_step_time = (time.perf_counter() - step_start) * 1000.0

                traces.append(
                    AgentStepTrace(
                        attempt=attempt,
                        step_name="EXECUTE_READONLY_QUERY",
                        input_sql=executable_sql,
                        ast_status=ast_status_label,
                        db_error=None,
                        healed_sql=None,
                        execution_time_ms=round(total_step_time, 2),
                    )
                )

                final_sql = executable_sql
                final_columns = columns
                final_rows = rows
                break  # Successful execution, exit loop

            except Exception as db_err:
                db_latency = (time.perf_counter() - db_exec_start) * 1000.0
                error_msg = str(db_err)
                logger.warning("[Attempt %d] SQLite execution error: %s", attempt, error_msg)

                if attempt < max_attempts:
                    healed_sql = await self_healer.heal_sql(
                        question=question,
                        failing_sql=executable_sql,
                        error_message=f"SQLite Operational Error: {error_msg}",
                        pruned_schema=pruned_schema,
                        attempt=attempt,
                    )
                    traces.append(
                        AgentStepTrace(
                            attempt=attempt,
                            step_name="SELF_HEALING_REPAIR",
                            input_sql=executable_sql,
                            ast_status=ast_status_label,
                            db_error=error_msg,
                            healed_sql=healed_sql,
                            execution_time_ms=round(db_latency, 2),
                        )
                    )
                    current_sql = healed_sql
                    is_healed = True
                else:
                    traces.append(
                        AgentStepTrace(
                            attempt=attempt,
                            step_name="SELF_HEALING_EXHAUSTED",
                            input_sql=executable_sql,
                            ast_status=ast_status_label,
                            db_error=error_msg,
                            healed_sql=None,
                            execution_time_ms=round(db_latency, 2),
                        )
                    )
                    raise HTTPException(
                        status_code=500,
                        detail={
                            "error": "SQL_EXECUTION_FAILED",
                            "message": f"Query execution failed after {max_attempts} attempts. Last error: {error_msg}",
                            "traces": [t.model_dump() for t in traces],
                        },
                    )

        # 4. Summarize Insight
        summary = await self._generate_business_summary(question, final_sql, final_rows)
        total_workflow_time = (time.perf_counter() - workflow_start) * 1000.0

        return QueryExecutionResponse(
            question=question,
            executed_sql=final_sql,
            columns=final_columns,
            row_count=len(final_rows),
            data=final_rows,
            business_summary=summary,
            is_healed=is_healed,
            total_attempts=len(traces),
            execution_time_ms=round(total_workflow_time, 2),
            agent_traces=traces if request.include_trace else [],
        )

    async def _generate_business_summary(
        self, question: str, sql: str, rows: List[Dict[str, Any]]
    ) -> str:
        """
        Synthesizes tabular query results into executive business insights.
        Uses Gemini if configured, otherwise produces a dynamic rule-based summary.
        """
        if not rows:
            return "Không tìm thấy dữ liệu phù hợp với điều kiện truy vấn trong cơ sở dữ liệu."

        if not settings.GEMINI_API_KEY:
            return self._heuristic_summary(question, rows)

        try:
            url = f"{settings.GEMINI_API_URL}/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
            sample_data = rows[:8]  # Limit tokens for summary
            prompt = f"""
Bạn là một Giám đốc Phân tích Kinh doanh (Head of Business Intelligence & Data Analytics).
Dựa trên câu hỏi của người dùng và bảng kết quả truy vấn SQL dưới đây:

Câu hỏi: {question}
Dữ liệu ({len(rows)} dòng kết quả):
{sample_data}

Hãy viết một đoạn tóm tắt ngắn gọn (2-3 câu), chuyên nghiệp bằng chính ngôn ngữ của câu hỏi (Tiếng Việt hoặc Tiếng Anh).
Nêu bật số liệu quan trọng nhất, các tỉ lệ phần trăm hoặc đề xuất hành động kinh doanh thực tế. Không viết lại câu SQL.
"""
            payload = {
                "contents": [{"role": "user", "parts": [{"text": prompt.strip()}]}],
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 300},
            }

            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            summary = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            return summary

        except Exception as ex:
            logger.warning("Gemini BI summary generation failed: %s", str(ex))
            return self._heuristic_summary(question, rows)

    def _heuristic_summary(self, question: str, rows: List[Dict[str, Any]]) -> str:
        """Dynamic heuristic business summary when LLM API is offline."""
        row_count = len(rows)
        first_row = rows[0]

        # Extract numeric values if present
        numeric_items = {k: v for k, v in first_row.items() if isinstance(v, (int, float))}
        string_items = {k: v for k, v in first_row.items() if isinstance(v, str)}

        top_entity = list(string_items.values())[0] if string_items else "thực thể đầu bảng"
        top_metric = (
            f"{list(numeric_items.keys())[0]}: {list(numeric_items.values())[0]:,}"
            if numeric_items
            else ""
        )

        return (
            f"Phân tích dữ liệu từ {row_count} bản ghi cho thấy '{top_entity}' đang giữ vị trí dẫn đầu "
            f"với chỉ số {top_metric}. Đây là phân khúc trọng điểm cần tiếp tục tối ưu hóa chiến lược vận hành."
        )


orchestrator = AnalyticsOrchestrator()
