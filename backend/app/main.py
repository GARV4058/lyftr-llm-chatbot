import logging
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.cache import init_cache
from app.config import get_settings
from app.database import (
    get_connection,
    get_messages_for_session,
    init_db,
    save_chat_turn,
    session_exists,
)
from app.llm_gateway import execute_chat
from app.schemas import (
    ChatMetadata,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    SessionHistoryResponse,
    SessionMessage,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database and cache
    logger.info("Initializing SQLite database...")
    init_db()
    logger.info("Initializing LiteLLM cache...")
    init_cache()
    yield
    # Shutdown
    logger.info("Application shutting down.")


app = FastAPI(
    title="Lyftr LLM Chatbot Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins if settings.allowed_origins != ["*"] else ["*"],
    allow_origin_regex=".*" if "*" in settings.allowed_origins else None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Ensure all 422 validation errors match FastAPI's JSON detail shape."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Ensure HTTP exceptions return JSON with detail."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Never return HTML error page or raw stack traces."""
    logger.exception(f"Unhandled server error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# 1. GET /health
@app.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Health check endpoint",
)
async def health_check():
    """
    Returns 200 once the app is running, the database is reachable,
    and the key pool is loaded.
    """
    # Check DB accessibility
    try:
        conn = get_connection()
        conn.execute("SELECT 1;").fetchone()
        conn.close()
    except Exception as exc:
        logger.error(f"Database health check failed: {exc}")
        raise HTTPException(status_code=503, detail="database unavailable")

    current_settings = get_settings()
    return HealthResponse(
        status="ok",
        keys_configured=len(current_settings.keys),
        cache_enabled=True,
    )


# 2. POST /chat
@app.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Chat completion with caching and key failover",
)
async def chat_endpoint(
    req: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure"),
):
    """
    Multi-turn chat completion endpoint.
    - Caches responses via LiteLLM built-in cache
    - Fails over automatically across configured keys
    - Supports X-Simulate-Failure header for testing
    """
    session_id = req.session_id
    user_message = req.message  # already trimmed by Pydantic validator

    # Reconstruct multi-turn conversation history from SQLite
    history_records = get_messages_for_session(session_id)
    
    # Build full message list for LLM
    llm_messages = []
    if req.system_prompt and req.system_prompt.strip():
        llm_messages.append({"role": "system", "content": req.system_prompt.strip()})
        
    for past_msg in history_records:
        llm_messages.append({"role": past_msg["role"], "content": past_msg["content"]})
        
    # Append the current user message
    llm_messages.append({"role": "user", "content": user_message})

    # Execute chat with caching, key failover, and simulation hook
    result = await execute_chat(
        session_id=session_id,
        messages=llm_messages,
        simulate_failure_header=x_simulate_failure,
    )

    reply_text = result["reply"]
    metadata_dict = result["metadata"]

    # Persist the successful turn to SQLite
    save_chat_turn(
        session_id=session_id,
        user_message=user_message,
        assistant_reply=reply_text,
        assistant_metadata=metadata_dict,
    )

    return ChatResponse(
        session_id=session_id,
        reply=reply_text,
        metadata=ChatMetadata(**metadata_dict),
    )


# 3. GET /sessions/{session_id}/messages
@app.get(
    "/sessions/{session_id}/messages",
    response_model=SessionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get session history",
)
async def get_session_history(session_id: str):
    """
    Returns stored history of one session from SQLite, oldest first,
    without the system prompt.
    Returns 404 if the session is unknown.
    """
    clean_id = session_id.strip()
    if not clean_id or not session_exists(clean_id):
        raise HTTPException(status_code=404, detail="session not found")

    messages_data = get_messages_for_session(clean_id)
    session_messages = [SessionMessage(**msg) for msg in messages_data]

    return SessionHistoryResponse(
        session_id=clean_id,
        messages=session_messages,
    )
