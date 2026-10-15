import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.config import settings
from app.database.seeder import seed_ecommerce_database
from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager:
    Automatically seeds the SQLite database with 2,000+ realistic E-commerce records on startup.
    """
    logger.info("============================================================================")
    logger.info(" Starting %s v%s", settings.APP_NAME, settings.APP_VERSION)
    logger.info("============================================================================")

    if settings.SEED_ON_STARTUP:
        logger.info("Checking database and running initial seeder...")
        seeded, row_count = seed_ecommerce_database(settings.DB_PATH)
        if seeded:
            logger.info("Successfully seeded database with %d fresh E-commerce records!", row_count)
        else:
            logger.info("Database already contains %d records. Skipping seeder.", row_count)

    yield

    logger.info("Shutting down %s.", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ### Production-Ready Multi-Agent Text-to-SQL & BI Analytics Engine
    
    **Key Capabilities:**
    - **Natural Language Data Analysis:** Ask questions in Vietnamese or English.
    - **Intelligent Schema Pruning:** Extracts and passes only relevant tables to optimize LLM context.
    - **AST Security Guard (`sqlglot`):** Blocks DDL/mutation (`DROP`, `DELETE`, `UPDATE`), blocks sensitive columns (`password_hash`), and enforces safe `LIMIT` clauses.
    - **Read-Only SQLite Execution:** Physical read-only URI mode (`file:...mode=ro`) preventing unauthorized writes.
    - **Autonomous Self-Healing Loop:** Automatically repairs invalid queries up to 3 times based on error tracebacks.
    - **BI Business Insights:** Returns structured tabular rows alongside concise executive summaries.
    - **Agent Observability:** Full step-by-step trace history with timestamps and AST status.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect root path to interactive Swagger documentation."""
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
