import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Set test environment variables BEFORE importing app
temp_dir = tempfile.mkdtemp()
test_db_path = os.path.join(temp_dir, "test.db")
os.environ["DATABASE_URL"] = f"sqlite:///{test_db_path.replace(os.sep, '/')}"
os.environ["LLM_API_KEYS"] = "test_key_1,test_key_2,test_key_3"
os.environ["ENABLE_FAILURE_SIMULATION"] = "true"
os.environ["LLM_MODEL"] = "gemini/gemini-2.0-flash"
os.environ["ALLOWED_ORIGINS"] = "http://localhost:3000,http://127.0.0.1:3000"

from app.cache import clear_cache, init_cache
from app.database import init_db
from app.main import app


@pytest.fixture(autouse=True)
def setup_teardown():
    # Fresh database and cache for each test
    init_db()
    init_cache()
    clear_cache()
    yield
    clear_cache()
    # Clean database tables
    import sqlite3
    from app.database import resolve_sqlite_path
    path = resolve_sqlite_path(os.environ["DATABASE_URL"])
    if os.path.exists(path):
        conn = sqlite3.connect(path)
        with conn:
            conn.execute("DELETE FROM messages;")
        conn.close()


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def mock_litellm():
    """Mock litellm.completion to return predictable responses."""
    with patch("litellm.completion") as mock_comp:
        def side_effect(model, messages, api_key, **kwargs):
            # Deterministic mock reply based on last message
            last_msg = messages[-1]["content"] if messages else ""
            mock_resp = MagicMock()
            mock_choice = MagicMock()
            mock_choice.message.content = f"Echo: {last_msg}"
            mock_resp.choices = [mock_choice]
            mock_resp.model = model
            mock_resp.usage = MagicMock()
            mock_resp.usage.prompt_tokens = len(last_msg.split()) + 10
            mock_resp.usage.completion_tokens = len(last_msg.split()) + 5
            return mock_resp

        mock_comp.side_effect = side_effect
        yield mock_comp
