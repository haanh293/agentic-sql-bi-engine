from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NaturalQueryRequest(BaseModel):
    """Input request for natural language analytics query."""

    query: str = Field(
        ...,
        description="Natural language question in Vietnamese or English",
        examples=[
            "Top 5 sản phẩm có doanh thu cao nhất năm 2025 là gì?",
            "What are the top 3 cities with the highest number of completed orders?",
            "Cho tôi xem tỉ lệ đơn hàng theo từng phương thức thanh toán",
        ],
    )
    include_trace: bool = Field(
        default=True,
        description="Whether to include step-by-step agent traces in the response",
    )


class AgentStepTrace(BaseModel):
    """Detailed audit trace for a single step/attempt in the agentic workflow."""

    attempt: int = Field(..., description="Attempt iteration number (1-based)")
    step_name: str = Field(..., description="Name of the pipeline step")
    input_sql: Optional[str] = Field(None, description="SQL statement generated or fed into step")
    ast_status: str = Field(
        ..., description="Result of AST security inspection (PASSED, REJECTED, MODIFIED)"
    )
    db_error: Optional[str] = Field(None, description="Database error traceback if query failed")
    healed_sql: Optional[str] = Field(
        None, description="Revised SQL statement produced by the Self-Healing Agent"
    )
    execution_time_ms: float = Field(0.0, description="Latency of the step in milliseconds")


class SecurityAuditResult(BaseModel):
    """Detailed result of SQL AST syntactic security inspection via sqlglot."""

    is_safe: bool = Field(..., description="True if query passes all security and safety checks")
    original_sql: str = Field(..., description="Original SQL statement received")
    sanitized_sql: Optional[str] = Field(
        None, description="Rewritten/sanitized SQL (with LIMIT enforced if needed)"
    )
    violations: List[str] = Field(default_factory=list, description="List of security violations")
    tables_accessed: List[str] = Field(
        default_factory=list, description="Tables extracted from AST"
    )
    columns_accessed: List[str] = Field(
        default_factory=list, description="Columns extracted from AST"
    )
    limit_applied: Optional[int] = Field(
        None, description="Limit enforced on query if original query had none"
    )


class ValidateSqlRequest(BaseModel):
    """Request payload to manually validate and inspect a raw SQL query."""

    sql: str = Field(
        ...,
        description="SQL query string to audit with sqlglot AST Guard",
        examples=[
            "SELECT id, full_name, email FROM users ORDER BY id ASC LIMIT 10",
            "DROP TABLE users; -- malicious attempt",
            "SELECT id, full_name, password_hash FROM users",
        ],
    )


class QueryExecutionResponse(BaseModel):
    """Final response returned to user with data results and BI business summary."""

    question: str = Field(..., description="Original user question")
    executed_sql: str = Field(..., description="Final sanitized SQL query that was executed")
    columns: List[str] = Field(default_factory=list, description="List of returned column names")
    row_count: int = Field(0, description="Total number of returned rows")
    data: List[Dict[str, Any]] = Field(
        default_factory=list, description="Tabular query results as list of row dictionaries"
    )
    business_summary: str = Field(
        ..., description="Concise, executive BI insight and business summary"
    )
    is_healed: bool = Field(
        False, description="True if query encountered errors and was repaired by Self-Healing"
    )
    total_attempts: int = Field(1, description="Number of generation/repair attempts made")
    execution_time_ms: float = Field(
        0.0, description="Total end-to-end execution time in milliseconds"
    )
    agent_traces: List[AgentStepTrace] = Field(
        default_factory=list, description="Step-by-step agent execution traces for full observability"
    )
