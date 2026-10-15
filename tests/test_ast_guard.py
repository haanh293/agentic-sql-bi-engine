import pytest
from app.security.ast_guard import AstSecurityGuard


@pytest.fixture
def guard():
    return AstSecurityGuard(
        forbidden_tables=["admin_secrets", "api_keys"],
        forbidden_columns=["password_hash", "credit_card", "ssn"],
        default_limit=100,
        max_limit=500,
    )


def test_valid_select_query_passes(guard):
    sql = "SELECT id, name, price FROM products WHERE price > 100 ORDER BY price DESC"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is True
    assert len(result.violations) == 0
    assert result.limit_applied == 100
    assert "LIMIT 100" in result.sanitized_sql.upper()
    assert "products" in result.tables_accessed


def test_drop_table_is_blocked(guard):
    sql = "DROP TABLE users;"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is False
    assert any("DROP" in v.upper() for v in result.violations)
    assert result.sanitized_sql is None


def test_delete_and_update_are_blocked(guard):
    del_sql = "DELETE FROM orders WHERE id = 1"
    del_result = guard.audit_and_sanitize(del_sql)
    assert del_result.is_safe is False
    assert any("DELETE" in v.upper() for v in del_result.violations)

    update_sql = "UPDATE products SET price = 99.0 WHERE id = 1"
    up_result = guard.audit_and_sanitize(update_sql)
    assert up_result.is_safe is False
    assert any("UPDATE" in v.upper() for v in up_result.violations)


def test_sensitive_column_password_hash_is_blocked(guard):
    sql = "SELECT id, email, password_hash FROM users"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is False
    assert any("password_hash" in v.lower() for v in result.violations)


def test_wildcard_select_star_from_users_is_blocked(guard):
    # 'users' table contains password_hash, SELECT * would leak it
    sql = "SELECT * FROM users"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is False
    assert any("password_hash" in v.lower() for v in result.violations)


def test_automatic_limit_addition_when_missing(guard):
    sql = "SELECT id, name FROM products"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is True
    assert result.limit_applied == 100
    assert "LIMIT 100" in result.sanitized_sql.upper()


def test_excessive_limit_is_capped_to_max(guard):
    sql = "SELECT id, name FROM products LIMIT 5000"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is True
    assert result.limit_applied == 500
    assert "LIMIT 500" in result.sanitized_sql.upper()


def test_multi_statement_sql_injection_is_blocked(guard):
    sql = "SELECT 1; DROP TABLE users;"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is False
    assert any("MULTI-STATEMENT" in v.upper() for v in result.violations)


def test_forbidden_table_access_is_blocked(guard):
    sql = "SELECT * FROM admin_secrets"
    result = guard.audit_and_sanitize(sql)

    assert result.is_safe is False
    assert any("admin_secrets" in v.lower() for v in result.violations)
