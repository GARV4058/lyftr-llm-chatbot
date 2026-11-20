import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.config import get_settings


def resolve_sqlite_path(db_url: str) -> str:
    """Resolve sqlite connection string to a filesystem path."""
    if db_url.startswith("sqlite:////"):
        # Unix absolute path: sqlite:////data/app.db -> /data/app.db
        path = "/" + db_url[len("sqlite:////"):]
    elif db_url.startswith("sqlite:///"):
        # Relative or windows path: sqlite:///./app.db or sqlite:///C:/...
        path = db_url[len("sqlite:///"):]
    else:
        path = db_url
    
    # In Windows or Linux, ensure parent directory exists if path has a directory
    dirname = os.path.dirname(os.path.abspath(path))
    if dirname:
        os.makedirs(dirname, exist_ok=True)
    return path


def get_connection(db_url: Optional[str] = None) -> sqlite3.Connection:
    url = db_url or get_settings().database_url
    path = resolve_sqlite_path(url)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_url: Optional[str] = None) -> None:
    """Initialize SQLite database and create messages table."""
    conn = get_connection(db_url)
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages(session_id, id);
                """
            )
    finally:
        conn.close()


def session_exists(session_id: str, db_url: Optional[str] = None) -> bool:
    """Check if any message has been stored for this session_id."""
    conn = get_connection(db_url)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM messages WHERE session_id = ? LIMIT 1;", (session_id,))
        row = cursor.fetchone()
        return row is not None
    finally:
        conn.close()


def get_messages_for_session(session_id: str, db_url: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return all messages for session_id in chronological order (oldest first)."""
    conn = get_connection(db_url)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT role, content, metadata
            FROM messages
            WHERE session_id = ?
            ORDER BY id ASC;
            """,
            (session_id,),
        )
        rows = cursor.fetchall()
        
        result: List[Dict[str, Any]] = []
        for r in rows:
            role = r["role"]
            content = r["content"]
            raw_meta = r["metadata"]
            
            msg_obj: Dict[str, Any] = {
                "role": role,
                "content": content
            }
            if role == "assistant" and raw_meta:
                try:
                    msg_obj["metadata"] = json.loads(raw_meta)
                except Exception:
                    msg_obj["metadata"] = None
            result.append(msg_obj)
        return result
    finally:
        conn.close()


def save_chat_turn(
    session_id: str,
    user_message: str,
    assistant_reply: str,
    assistant_metadata: Dict[str, Any],
    db_url: Optional[str] = None,
) -> None:
    """Atomically save user message and assistant reply to SQLite."""
    now_iso = datetime.now(timezone.utc).isoformat()
    meta_json = json.dumps(assistant_metadata)
    
    conn = get_connection(db_url)
    try:
        with conn:
            # 1. User message
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata, created_at)
                VALUES (?, 'user', ?, NULL, ?);
                """,
                (session_id, user_message, now_iso),
            )
            # 2. Assistant message
            conn.execute(
                """
                INSERT INTO messages (session_id, role, content, metadata, created_at)
                VALUES (?, 'assistant', ?, ?, ?);
                """,
                (session_id, assistant_reply, meta_json, now_iso),
            )
    finally:
        conn.close()
