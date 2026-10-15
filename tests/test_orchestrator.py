import os
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

from app.config import settings
from app.database.seeder import seed_ecommerce_database
from app.main import app
from app.schemas.query_schema import NaturalQueryRequest
from app.agents.orchestrator import orchestrator


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    """Seeds the test database once before running tests."""
    test_db = "test_ecommerce.db"
    settings.DB_PATH = test_db
    seed_ecommerce_database(test_db, force_reseed=True)
    yield
    if os.path.exists(test_db):
        try:
            os.remove(test_db)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_self_healing_loop_repairs_invalid_column_name():
    """
    Core Requirement Test:
    Attempt 1: Generates invalid SQL with non-existent column 'user_name'.
    SQLite raises 'no such column: user_name'.
    Attempt 2: Self-Healer diagnoses error and rewrites column to 'full_name'.
    Query executes successfully and returns valid rows.
    """
    failing_sql = "SELECT user_name, city FROM users LIMIT 5;"
    healed_sql = "SELECT full_name, city FROM users LIMIT 5;"

    # Mock sql_generator to return the bad SQL
    with patch("app.agents.orchestrator.sql_generator.generate_sql", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = failing_sql

        # Mock self_healer to return the corrected SQL
        with patch("app.agents.orchestrator.self_healer.heal_sql", new_callable=AsyncMock) as mock_heal:
            mock_heal.return_value = healed_sql

            request = NaturalQueryRequest(
                query="Danh sách 5 người dùng và thành phố của họ",
                include_trace=True,
            )
            response = await orchestrator.execute_analytics_workflow(request)

            # Assertions for Self-Healing state
            assert response.is_healed is True
            assert response.total_attempts == 2
            assert response.row_count == 5
            assert len(response.data) == 5
            assert "full_name" in response.columns
            assert "city" in response.columns

            # Verify Agent Traces
            traces = response.agent_traces
            assert len(traces) == 2

            # Trace 1: Failed on database execution
            assert traces[0].attempt == 1
            assert traces[0].step_name == "SELF_HEALING_REPAIR"
            assert "no such column: user_name" in traces[0].db_error.lower()
            assert traces[0].healed_sql == healed_sql

            # Trace 2: Successfully executed healed query
            assert traces[1].attempt == 2
            assert traces[1].step_name == "EXECUTE_READONLY_QUERY"
            assert traces[1].db_error is None


@pytest.mark.asyncio
async def test_end_to_end_analytics_ask_api():
    """Tests the full POST /api/v1/analytics/ask endpoint via AsyncClient."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "query": "Top 5 sản phẩm có doanh thu cao nhất",
            "include_trace": True,
        }
        res = await client.post("/api/v1/analytics/ask", json=payload)
        assert res.status_code == 200
        data = res.json()

        assert "executed_sql" in data
        assert "columns" in data
        assert data["row_count"] > 0
        assert len(data["data"]) > 0
        assert len(data["business_summary"]) > 10
        assert "agent_traces" in data
        assert len(data["agent_traces"]) >= 1


@pytest.mark.asyncio
async def test_security_validate_sql_api():
    """Tests the POST /api/v1/security/validate-sql endpoint blocking dangerous queries."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test Malicious DROP TABLE
        bad_payload = {"sql": "DROP TABLE users;"}
        bad_res = await client.post("/api/v1/security/validate-sql", json=bad_payload)
        assert bad_res.status_code == 200
        bad_data = bad_res.json()
        assert bad_data["is_safe"] is False
        assert any("DROP" in v.upper() for v in bad_data["violations"])

        # Test Safe SELECT with auto-limit
        safe_payload = {"sql": "SELECT id, name, price FROM products"}
        safe_res = await client.post("/api/v1/security/validate-sql", json=safe_payload)
        assert safe_res.status_code == 200
        safe_data = safe_res.json()
        assert safe_data["is_safe"] is True
        assert safe_data["limit_applied"] == 100
        assert "LIMIT 100" in safe_data["sanitized_sql"].upper()


@pytest.mark.asyncio
async def test_health_and_schema_endpoints():
    """Tests /api/v1/analytics/health and /api/v1/analytics/schema endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Health check
        h_res = await client.get("/api/v1/analytics/health")
        assert h_res.status_code == 200
        assert h_res.json()["status"] == "HEALTHY"

        # Schema inspection
        s_res = await client.get("/api/v1/analytics/schema")
        assert s_res.status_code == 200
        s_data = s_res.json()
        assert s_data["total_records"] > 2000
        assert "users" in s_data["table_row_counts"]
        assert "products" in s_data["table_row_counts"]
