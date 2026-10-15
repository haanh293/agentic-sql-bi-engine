import re
from typing import List, Optional, Set
import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from app.config import settings
from app.schemas.query_schema import SecurityAuditResult


class AstSecurityGuard:
    """
    SQL Abstract Syntax Tree (AST) Security Guard using sqlglot.
    Validates syntax, ensures Read-Only query structure, blocks DDL/DML mutation,
    blocks access to forbidden tables and sensitive columns, and enforces query LIMITs.
    """

    # Prohibited expression types in AST (Mutation, DDL, Administrative)
    PROHIBITED_EXPRESSION_TYPES = (
        exp.Drop,
        exp.Delete,
        exp.Update,
        exp.Insert,
        exp.Alter,
        exp.Create,
        exp.Command,
        exp.TruncateTable,
        exp.Merge,
        exp.Pragma,
    )

    def __init__(
        self,
        forbidden_tables: Optional[List[str]] = None,
        forbidden_columns: Optional[List[str]] = None,
        default_limit: int = settings.DEFAULT_QUERY_LIMIT,
        max_limit: int = settings.MAX_QUERY_LIMIT,
    ):
        self.forbidden_tables: Set[str] = set(
            t.lower() for t in (forbidden_tables or settings.FORBIDDEN_TABLES)
        )
        self.forbidden_columns: Set[str] = set(
            c.lower() for c in (forbidden_columns or settings.FORBIDDEN_COLUMNS)
        )
        self.default_limit: int = default_limit
        self.max_limit: int = max_limit

    def clean_sql_input(self, raw_sql: str) -> str:
        """Strips markdown code fences and whitespace from raw LLM output."""
        if not raw_sql:
            return ""
        cleaned = raw_sql.strip()
        # Remove ```sql or ``` fences
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned.rstrip(";")

    def audit_and_sanitize(self, raw_sql: str) -> SecurityAuditResult:
        """
        Parses SQL AST, performs comprehensive security auditing,
        and returns a sanitized executable query or violation report.
        """
        cleaned_sql = self.clean_sql_input(raw_sql)
        violations: List[str] = []
        tables_accessed: List[str] = []
        columns_accessed: List[str] = []
        limit_applied: Optional[int] = None

        if not cleaned_sql:
            return SecurityAuditResult(
                is_safe=False,
                original_sql=raw_sql,
                sanitized_sql=None,
                violations=["SQL query cannot be empty."],
                tables_accessed=[],
                columns_accessed=[],
            )

        # 1. Parse into AST statements
        try:
            statements = [s for s in sqlglot.parse(cleaned_sql, read="sqlite") if s]
        except ParseError as pe:
            return SecurityAuditResult(
                is_safe=False,
                original_sql=cleaned_sql,
                sanitized_sql=None,
                violations=[f"SQL Syntax Parse Error: {str(pe)}"],
                tables_accessed=[],
                columns_accessed=[],
            )
        except Exception as ex:
            return SecurityAuditResult(
                is_safe=False,
                original_sql=cleaned_sql,
                sanitized_sql=None,
                violations=[f"Unexpected AST parsing failure: {str(ex)}"],
                tables_accessed=[],
                columns_accessed=[],
            )

        # 2. Prevent multi-statement query chaining (SQL injection vector)
        if len(statements) == 0:
            return SecurityAuditResult(
                is_safe=False,
                original_sql=cleaned_sql,
                sanitized_sql=None,
                violations=["No valid SQL statement recognized."],
                tables_accessed=[],
                columns_accessed=[],
            )

        if len(statements) > 1:
            violations.append(
                f"Multi-statement queries are forbidden. Detected {len(statements)} statements."
            )

        root_stmt = statements[0]

        # 3. Verify root expression is a SELECT or UNION (Strict Read-Only)
        if not isinstance(root_stmt, (exp.Select, exp.Union)):
            violations.append(
                f"Only read-only SELECT queries are allowed. Prohibited root operation: '{root_stmt.key.upper()}'."
            )

        # 4. Deep AST Walk: check for any mutation or prohibited AST nodes
        for node in root_stmt.walk():
            if isinstance(node, self.PROHIBITED_EXPRESSION_TYPES):
                op_name = node.key.upper() if hasattr(node, "key") else str(type(node).__name__)
                violations.append(f"Prohibited destructive/mutation operation detected: '{op_name}'.")

        # 5. Extract and Validate Tables
        table_nodes = list(root_stmt.find_all(exp.Table))
        for t in table_nodes:
            t_name = t.name.lower()
            if t_name:
                tables_accessed.append(t_name)
                if t_name in self.forbidden_tables:
                    violations.append(f"Access to prohibited table '{t_name}' is blocked by security policy.")

        # Deduplicate tables list preserving order
        tables_accessed = list(dict.fromkeys(tables_accessed))

        # 6. Extract and Validate Columns
        has_star = bool(root_stmt.find(exp.Star))
        column_nodes = list(root_stmt.find_all(exp.Column))

        for c in column_nodes:
            col_name = c.name.lower()
            if col_name:
                columns_accessed.append(col_name)
                if col_name in self.forbidden_columns:
                    violations.append(
                        f"Access to sensitive/PII column '{col_name}' is strictly blocked."
                    )

        # Prevent 'SELECT * FROM users' from leaking password_hash
        if has_star and "users" in tables_accessed:
            violations.append(
                "Wildcard 'SELECT *' from table 'users' is blocked because it exposes sensitive column 'password_hash'. "
                "Specify explicit columns instead (e.g. id, full_name, email, city)."
            )

        columns_accessed = list(dict.fromkeys(columns_accessed))

        # 7. Check / Enforce Query LIMIT
        sanitized_sql: Optional[str] = None
        if not violations:
            limit_node = root_stmt.find(exp.Limit)
            if limit_node is None:
                # No limit clause found -> Automatically attach DEFAULT_QUERY_LIMIT
                root_stmt = root_stmt.limit(self.default_limit)
                limit_applied = self.default_limit
            else:
                # Limit clause exists -> Enforce maximum ceiling
                try:
                    current_limit_val = int(limit_node.expression.this)
                    if current_limit_val > self.max_limit:
                        root_stmt.set("limit", exp.Limit(expression=exp.Literal.number(self.max_limit)))
                        limit_applied = self.max_limit
                    elif current_limit_val <= 0:
                        root_stmt.set("limit", exp.Limit(expression=exp.Literal.number(self.default_limit)))
                        limit_applied = self.default_limit
                except Exception:
                    # In case of non-integer limit expression, default to safe limit
                    root_stmt.set("limit", exp.Limit(expression=exp.Literal.number(self.default_limit)))
                    limit_applied = self.default_limit

            sanitized_sql = root_stmt.sql(dialect="sqlite")

        return SecurityAuditResult(
            is_safe=len(violations) == 0,
            original_sql=cleaned_sql,
            sanitized_sql=sanitized_sql,
            violations=violations,
            tables_accessed=tables_accessed,
            columns_accessed=columns_accessed,
            limit_applied=limit_applied,
        )


# Global singleton instance for application use
ast_guard = AstSecurityGuard()
