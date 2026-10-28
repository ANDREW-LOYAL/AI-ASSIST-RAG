"""SQLite persistence for chat conversations and model context."""
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from src.config import PathConfig


def _timestamp():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class ChatStore:
    """Small connection-per-operation repository for chat history."""

    def __init__(self, database_path=None, initialize=True):
        self.database_path = Path(database_path or PathConfig.CHAT_HISTORY_PATH)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        if initialize:
            self.initialize()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        """Create the database schema if it doesn't exist."""
        with self._connection() as connection:
            connection.executescript(
                """CREATE TABLE IF NOT EXISTS conversations (
                       id TEXT PRIMARY KEY,
                       title TEXT NOT NULL,
                       created_at TEXT NOT NULL,
                       updated_at TEXT NOT NULL,
                       model_history TEXT NOT NULL DEFAULT '[]'
                   );
                   CREATE TABLE IF NOT EXISTS messages (
                       id INTEGER PRIMARY KEY AUTOINCREMENT,
                       message_uid TEXT NOT NULL UNIQUE,
                       conversation_id TEXT NOT NULL REFERENCES conversations(id)
                           ON DELETE CASCADE,
                       role TEXT NOT NULL,
                       content TEXT NOT NULL,
                       status TEXT NOT NULL DEFAULT 'complete',
                       created_at TEXT NOT NULL
                   );
                   CREATE INDEX IF NOT EXISTS messages_by_conversation
                       ON messages(conversation_id, id);
                   UPDATE messages SET status = 'interrupted'
                       WHERE status = 'pending';"""
            )

    def create_conversation(self):
        """Create a new conversation and return its ID."""
        conversation_id = str(uuid.uuid4())
        now = _timestamp()
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO conversations (id, title, created_at, updated_at)
                   VALUES (?, ?, ?, ?)""",
                (conversation_id, "Nuevo chat", now, now),
            )
        return conversation_id

    def list_conversations(self):
        """List all conversations with their metadata."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT id, title, created_at, updated_at
                   FROM conversations ORDER BY updated_at DESC, created_at DESC"""
            ).fetchall()
        return [dict(row) for row in rows]

    def get_messages(self, conversation_id):
        """Retrieve all messages for a given conversation ID."""
        with self._connection() as connection:
            rows = connection.execute(
                """SELECT role, content, status, created_at
                   FROM messages WHERE conversation_id = ? ORDER BY id""",
                (conversation_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_model_history(self, conversation_id):
        """Retrieve the model history for a given conversation ID."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT model_history FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return []
        return json.loads(row["model_history"])

    def add_user_message(self, conversation_id, content):
        """Add a user message to the conversation and return its unique ID."""
        message_uid = str(uuid.uuid4())
        now = _timestamp()
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO messages
                   (message_uid, conversation_id, role, content, status, created_at)
                   VALUES (?, ?, 'user', ?, 'pending', ?)""",
                (message_uid, conversation_id, content, now),
            )
            first_line = content.strip().splitlines()[0] if content.strip() else "Nuevo chat"
            title = first_line[:48] + ("…" if len(first_line) > 48 else "")
            connection.execute(
                """UPDATE conversations
                   SET title = CASE WHEN title = 'Nuevo chat' THEN ? ELSE title END,
                       updated_at = ?
                   WHERE id = ?""",
                (title, now, conversation_id),
            )
        return message_uid

    def complete_turn(self, conversation_id, user_message_uid, answer, model_history):
        """Complete a conversation turn by adding the assistant's response and updating the model history."""
        now = _timestamp()
        with self._connection() as connection:
            connection.execute(
                """INSERT INTO messages
                   (message_uid, conversation_id, role, content, status, created_at)
                   VALUES (?, ?, 'assistant', ?, 'complete', ?)""",
                (str(uuid.uuid4()), conversation_id, answer, now),
            )
            connection.execute(
                "UPDATE messages SET status = 'complete' WHERE message_uid = ?",
                (user_message_uid,),
            )
            connection.execute(
                """UPDATE conversations
                   SET model_history = ?, updated_at = ? WHERE id = ?""",
                (
                    json.dumps(model_history, ensure_ascii=False),
                    now,
                    conversation_id,
                ),
            )

    def fail_turn(self, conversation_id, user_message_uid, error_message):
        """Mark a conversation turn as failed and add an error message."""
        now = _timestamp()
        with self._connection() as connection:
            connection.execute(
                "UPDATE messages SET status = 'failed' WHERE message_uid = ?",
                (user_message_uid,),
            )
            connection.execute(
                """INSERT INTO messages
                   (message_uid, conversation_id, role, content, status, created_at)
                   VALUES (?, ?, 'assistant', ?, 'failed', ?)""",
                (str(uuid.uuid4()), conversation_id, error_message, now),
            )
            connection.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (now, conversation_id),
            )
