import json
import logging
from typing import Optional
import httpx
from app.config import settings

logger = logging.getLogger("app.agents.sql_generator")


class SqlGenerator:
    """
    Translates natural language questions into executable SQLite queries
    using Google Gemini API or an intelligent deterministic fallback.
    """

    SYSTEM_PROMPT = """
You are a Senior Principal Data Engineer & Analytics Architect specializing in SQLite.
Your mission is to generate a single, highly optimized, syntactically pristine SQLite query that directly answers the user's question based on the provided schema.

### STRICT RULES:
1. Output ONLY the raw SQL SELECT query. Do NOT wrap in markdown code blocks (no ```sql). Do NOT write any greetings or explanations.
2. Generate ONLY read-only SELECT queries. Destructive statements (DROP, DELETE, UPDATE, INSERT, ALTER) are strictly forbidden.
3. NEVER query sensitive columns such as 'password_hash', 'credit_card', or 'ssn'.
4. Do NOT use SELECT * on tables with sensitive columns. Always name explicit columns.
5. Ensure all JOIN conditions correctly align foreign keys (e.g. orders.user_id = users.id).
6. Always ensure proper GROUP BY columns when using aggregations like SUM, COUNT, AVG.
7. Dialect: Strict SQLite (use SQLite-compatible functions like strftime, round, coalesce).
"""

    async def generate_sql(self, question: str, pruned_schema: str) -> str:
        """Generates SQL query using Gemini API or Deterministic Fallback."""
        if not settings.GEMINI_API_KEY:
            logger.info("GEMINI_API_KEY is not configured. Using deterministic fallback generator.")
            return self._generate_fallback_sql(question)

        try:
            url = f"{settings.GEMINI_API_URL}/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
            prompt_content = f"""
### DATABASE SCHEMA DDL:
{pruned_schema}

### USER QUESTION:
{question}

Generate the exact SQLite query to answer the question:
"""
            payload = {
                "system_instruction": {"parts": [{"text": self.SYSTEM_PROMPT.strip()}]},
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": prompt_content.strip()}],
                    }
                ],
                "generationConfig": {
                    "temperature": 0.0,
                    "maxOutputTokens": 800,
                },
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()

            candidates = data.get("candidates", [])
            if not candidates:
                raise ValueError("Gemini returned empty candidates")

            sql_text = candidates[0]["content"]["parts"][0]["text"].strip()
            # Clean markdown if present
            if sql_text.startswith("```"):
                lines = sql_text.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                sql_text = "\n".join(lines).strip()

            return sql_text

        except Exception as ex:
            logger.warning(
                "Gemini API request failed (%s). Falling back to deterministic generator.",
                str(ex),
            )
            return self._generate_fallback_sql(question)

    def _generate_fallback_sql(self, question: str) -> str:
        """
        Deterministic mock generator for offline testing and Swagger UI demo questions.
        Matches Vietnamese and English queries to real database tables.
        """
        q = question.lower()

        # 1. Top products by revenue
        if any(w in q for w in ["doanh thu", "revenue", "bán chạy", "top", "best seller"]) and any(
            w in q for w in ["sản phẩm", "product", "mặt hàng"]
        ):
            return """
SELECT 
    p.id AS product_id,
    p.name AS product_name,
    p.category,
    ROUND(SUM(oi.quantity * (oi.unit_price * (1 - oi.discount))), 2) AS total_revenue,
    SUM(oi.quantity) AS total_quantity_sold
FROM order_items oi
JOIN products p ON oi.product_id = p.id
JOIN orders o ON oi.order_id = o.id
WHERE o.status = 'COMPLETED'
GROUP BY p.id, p.name, p.category
ORDER BY total_revenue DESC
LIMIT 5;
""".strip()

        # 2. Top cities by completed orders
        if any(w in q for w in ["thành phố", "city", "cities", "khu vực"]) and any(
            w in q for w in ["đơn hàng", "order", "khách", "user"]
        ):
            return """
SELECT 
    u.city,
    COUNT(o.id) AS completed_orders_count,
    ROUND(SUM(o.total_amount), 2) AS total_sales_volume
FROM orders o
JOIN users u ON o.user_id = u.id
WHERE o.status = 'COMPLETED'
GROUP BY u.city
ORDER BY completed_orders_count DESC
LIMIT 5;
""".strip()

        # 3. Payment methods distribution
        if any(w in q for w in ["thanh toán", "payment", "phương thức", "method"]):
            return """
SELECT 
    payment_method,
    COUNT(id) AS total_orders,
    ROUND(SUM(total_amount), 2) AS total_revenue,
    ROUND(AVG(total_amount), 2) AS average_order_value
FROM orders
GROUP BY payment_method
ORDER BY total_orders DESC;
""".strip()

        # 4. Reviews and customer ratings
        if any(w in q for w in ["đánh giá", "review", "rating", "sao"]):
            return """
SELECT 
    p.name AS product_name,
    p.category,
    ROUND(AVG(r.rating), 2) AS average_user_rating,
    COUNT(r.id) AS review_count
FROM reviews r
JOIN products p ON r.product_id = p.id
GROUP BY p.id, p.name, p.category
HAVING review_count >= 2
ORDER BY average_user_rating DESC
LIMIT 10;
""".strip()

        # Default fallback
        return """
SELECT 
    id AS product_id,
    name AS product_name,
    category,
    price,
    rating,
    stock_quantity
FROM products
ORDER BY rating DESC
LIMIT 10;
""".strip()


sql_generator = SqlGenerator()
