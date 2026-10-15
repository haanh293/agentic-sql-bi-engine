import re
from typing import Dict, List, Set
from app.database.connection import get_database_schema_ddl


class SchemaPruner:
    """
    Intelligently prunes database schema DDL down to only tables relevant
    to the user's natural language question, optimizing LLM prompt tokens.
    """

    # Keyword mappings for Vietnamese and English
    TABLE_KEYWORDS: Dict[str, List[str]] = {
        "users": [
            "user", "users", "customer", "customers", "người dùng", "khách hàng", "account",
            "thành viên", "city", "thành phố", "email", "phone", "số điện thoại", "địa chỉ"
        ],
        "products": [
            "product", "products", "item", "items", "sản phẩm", "hàng hóa", "mặt hàng",
            "price", "giá", "cost", "giá vốn", "category", "danh mục", "stock", "tồn kho", "rating"
        ],
        "orders": [
            "order", "orders", "đơn hàng", "đơn", "mua hàng", "doanh thu", "revenue", "sales",
            "tiền", "thanh toán", "payment", "status", "trạng thái", "shipping", "phí ship", "ngày đặt"
        ],
        "order_items": [
            "order item", "order_item", "order_items", "chi tiết đơn", "số lượng mua", "quantity",
            "chiết khấu", "discount", "doanh số", "bán chạy", "top bán", "best seller", "mặt hàng trong đơn"
        ],
        "reviews": [
            "review", "reviews", "đánh giá", "nhận xét", "comment", "bình luận", "rating",
            "sao", "điểm", "feedback", "hài lòng"
        ],
    }

    # Foreign key dependency map (if table A is needed, include related foreign keys)
    RELATIONSHIPS: Dict[str, Set[str]] = {
        "order_items": {"orders", "products"},
        "orders": {"users", "order_items"},
        "reviews": {"users", "products"},
    }

    def prune_schema(self, question: str, full_ddl: str = None) -> str:
        """
        Filters full DDL to only relevant tables based on query semantic keywords.
        Always includes core related tables to enable multi-table JOINs.
        """
        if not full_ddl:
            full_ddl = get_database_schema_ddl()

        if not full_ddl:
            return ""

        q_lower = question.lower()
        selected_tables: Set[str] = set()

        for table_name, keywords in self.TABLE_KEYWORDS.items():
            for kw in keywords:
                if kw in q_lower:
                    selected_tables.add(table_name)
                    break

        # If question mentions revenue, best seller, top products -> include order_items, orders, products
        if any(w in q_lower for w in ["doanh thu", "revenue", "bán chạy", "best seller", "top", "doanh số"]):
            selected_tables.update(["orders", "order_items", "products"])

        # Add relationships for JOIN feasibility
        for table in list(selected_tables):
            if table in self.RELATIONSHIPS:
                selected_tables.update(self.RELATIONSHIPS[table])

        # Fallback: if no specific table matched, include all main tables
        if not selected_tables:
            selected_tables = {"users", "products", "orders", "order_items"}

        # Extract only matching table DDL blocks
        pruned_blocks: List[str] = []
        blocks = full_ddl.split("\n\n")

        for block in blocks:
            for table in selected_tables:
                # Matches "-- Table: table_name" or "CREATE TABLE table_name"
                if re.search(rf"\b(Table:\s+{table}|CREATE\s+TABLE\s+[\"']?{table}[\"']?)\b", block, re.IGNORECASE):
                    pruned_blocks.append(block.strip())
                    break

        return "\n\n".join(pruned_blocks) if pruned_blocks else full_ddl


schema_pruner = SchemaPruner()
