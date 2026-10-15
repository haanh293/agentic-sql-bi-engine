from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException, status
from app.config import settings
from app.database.connection import get_database_schema_ddl, get_readonly_connection
from app.schemas.query_schema import (
    NaturalQueryRequest,
    QueryExecutionResponse,
    SecurityAuditResult,
    ValidateSqlRequest,
)
from app.security.ast_guard import ast_guard
from app.agents.orchestrator import orchestrator

router = APIRouter(prefix="/api/v1", tags=["Analytics & Security"])


@router.post(
    "/analytics/ask",
    response_model=QueryExecutionResponse,
    summary="Natural Language Analytics Query (Text-to-SQL)",
    description="""
    Accepts a natural language question (Vietnamese or English), prunes the schema,
    generates SQLite SQL, performs AST security validation via `sqlglot`, executes on
    Read-Only SQLite, auto-repairs errors via Self-Healing Loop (max 3 times), and returns
    data rows with executive BI insights and step-by-step agent traces.
    """,
)
async def ask_analytics(request: NaturalQueryRequest) -> QueryExecutionResponse:
    try:
        return await orchestrator.execute_analytics_workflow(request)
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "INTERNAL_SERVER_ERROR", "message": str(ex)},
        )


@router.post(
    "/security/validate-sql",
    response_model=SecurityAuditResult,
    summary="Validate Raw SQL via AST Security Guard",
    description="""
    Inspects any arbitrary SQL statement using `sqlglot` AST syntactic analysis.
    Verifies that the statement is strictly a read-only SELECT, blocks DDL/mutation operations
    (DROP, DELETE, UPDATE, INSERT, ALTER), blocks prohibited tables and sensitive PII columns
    (password_hash, credit_card), and enforces safe LIMITs.
    """,
)
async def validate_sql(request: ValidateSqlRequest) -> SecurityAuditResult:
    return ast_guard.audit_and_sanitize(request.sql)


@router.get(
    "/analytics/schema",
    summary="Inspect Database Schema and Row Counts",
    description="Returns current E-commerce database tables, schema DDL, and active row statistics.",
)
async def get_schema_overview() -> Dict[str, Any]:
    ddl = get_database_schema_ddl()
    conn = get_readonly_connection()
    table_stats = {}
    try:
        cursor = conn.cursor()
        for tbl in ["users", "products", "orders", "order_items", "reviews"]:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                table_stats[tbl] = cursor.fetchone()[0]
            except Exception:
                table_stats[tbl] = 0
    finally:
        conn.close()

    return {
        "database_type": "SQLite (Read-Only Mode)",
        "total_records": sum(table_stats.values()),
        "table_row_counts": table_stats,
        "schema_ddl": ddl,
    }


@router.get(
    "/analytics/health",
    summary="System Health & Diagnostic Status",
    description="Returns API service health, active AI model configuration, and database connectivity.",
)
async def health_check() -> Dict[str, Any]:
    return {
        "status": "HEALTHY",
        "app_name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "ai_model": settings.GEMINI_MODEL,
        "api_key_configured": bool(settings.GEMINI_API_KEY),
        "self_healing_max_attempts": settings.MAX_SELF_HEAL_ATTEMPTS,
        "default_query_limit": settings.DEFAULT_QUERY_LIMIT,
    }
