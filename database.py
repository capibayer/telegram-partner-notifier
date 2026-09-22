import sqlite3
from pathlib import Path
from typing import Any, Optional, Union

from config import settings


class Database:
    def __init__(self, db_path: Union[str, Path]):
        self.db_path = str(db_path)
        self._ensure_parent_dir()
        self.init_db()

    def _ensure_parent_dir(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self.get_connection() as conn:
            columns = conn.execute("PRAGMA table_info(partner_chats)").fetchall()
            needs_partner_chat_migration = bool(columns) and "id" not in {column["name"] for column in columns}

            if needs_partner_chat_migration:
                conn.execute("ALTER TABLE partner_chats RENAME TO partner_chats_legacy")

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS partner_chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    chat_id INTEGER NOT NULL,
                    chat_title TEXT,
                    active INTEGER DEFAULT 1,
                    created_at TEXT,
                    updated_at TEXT,
                    UNIQUE(email, chat_id)
                )
                """
            )
            if needs_partner_chat_migration:
                conn.execute(
                    """
                    INSERT INTO partner_chats (
                        email, chat_id, chat_title, active, created_at, updated_at
                    )
                    SELECT email, chat_id, chat_title, active, created_at, updated_at
                    FROM partner_chats_legacy
                    """
                )
                conn.execute("DROP TABLE partner_chats_legacy")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    manager_id INTEGER,
                    message_text TEXT NOT NULL,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS managers (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_recipients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    notification_id INTEGER,
                    email TEXT,
                    chat_id INTEGER,
                    status TEXT,
                    error TEXT,
                    sent_at TEXT
                )
                """
            )
            conn.commit()

    def add_manager(self, user_id: int, added_by: int) -> None:
        with self.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO managers (user_id, added_by, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO NOTHING
                """,
                (int(user_id), int(added_by), __import__("datetime").datetime.utcnow().isoformat(timespec="seconds")),
            )
            conn.commit()

    def remove_manager(self, user_id: int) -> None:
        with self.get_connection() as conn:
            conn.execute("DELETE FROM managers WHERE user_id = ?", (int(user_id),))
            conn.commit()

    def is_manager(self, user_id: int) -> bool:
        with self.get_connection() as conn:
            return conn.execute("SELECT 1 FROM managers WHERE user_id = ?", (int(user_id),)).fetchone() is not None

    def get_managers(self) -> list[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute("SELECT * FROM managers ORDER BY created_at").fetchall()

    def upsert_partner_chat(self, email: str, chat_id: int, chat_title: Optional[str], active: int = 1) -> None:
        with self.get_connection() as conn:
            now = __import__("datetime").datetime.utcnow().isoformat(timespec="seconds")
            conn.execute(
                """
                INSERT INTO partner_chats (email, chat_id, chat_title, active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(email, chat_id) DO UPDATE SET
                    chat_title = excluded.chat_title,
                    active = excluded.active,
                    updated_at = excluded.updated_at
                """,
                (
                    email.lower(),
                    int(chat_id),
                    chat_title,
                    active,
                    now,
                    now,
                ),
            )
            conn.commit()

    def set_chat_inactive_for_email(self, email: str) -> None:
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE partner_chats SET active = 0, updated_at = ? WHERE email = ?",
                (__import__("datetime").datetime.utcnow().isoformat(timespec="seconds"), email.lower()),
            )
            conn.commit()

    def find_chat_by_email(self, email: str) -> Optional[sqlite3.Row]:
        with self.get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM partner_chats WHERE email = ? AND active = 1 ORDER BY updated_at DESC LIMIT 1",
                (email.lower(),),
            ).fetchone()
            return row

    def get_active_chats_for_email(self, email: str) -> list[sqlite3.Row]:
        with self.get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM partner_chats WHERE email = ? AND active = 1 ORDER BY updated_at",
                (email.lower(),),
            ).fetchall()
            return rows

    def find_conflicting_chats(self, email: str) -> list[sqlite3.Row]:
        return self.get_active_chats_for_email(email)

    def get_statistics(self) -> dict[str, int]:
        with self.get_connection() as conn:
            total = conn.execute("SELECT COUNT(*) AS cnt FROM partner_chats").fetchone()["cnt"]
            active = conn.execute("SELECT COUNT(*) AS cnt FROM partner_chats WHERE active = 1").fetchone()["cnt"]
            inactive = conn.execute("SELECT COUNT(*) AS cnt FROM partner_chats WHERE active = 0").fetchone()["cnt"]
            last_updated = conn.execute(
                "SELECT updated_at FROM partner_chats ORDER BY updated_at DESC LIMIT 1"
            ).fetchone()
            return {
                "total": total,
                "active": active,
                "inactive": inactive,
                "last_updated": last_updated["updated_at"] if last_updated else None,
            }

    def save_notification(self, manager_id: int, message_text: str) -> int:
        with self.get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO notifications (manager_id, message_text, created_at) VALUES (?, ?, ?)",
                (manager_id, message_text, __import__("datetime").datetime.utcnow().isoformat(timespec="seconds")),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def save_recipients(self, notification_id: int, recipients: list[dict[str, Any]]) -> None:
        with self.get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO notification_recipients (
                    notification_id, email, chat_id, status, error, sent_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        notification_id,
                        row["email"],
                        row["chat_id"],
                        row["status"],
                        row.get("error"),
                        row.get("sent_at"),
                    )
                    for row in recipients
                ],
            )
            conn.commit()

    def get_recent_notifications(self, limit: int = 10) -> list[sqlite3.Row]:
        with self.get_connection() as conn:
            return conn.execute(
                """
                SELECT
                    notifications.id,
                    notifications.manager_id,
                    notifications.message_text,
                    notifications.created_at,
                    COUNT(notification_recipients.id) AS total_recipients,
                    COALESCE(SUM(notification_recipients.status = 'sent'), 0) AS sent_count,
                    COALESCE(SUM(notification_recipients.status = 'failed'), 0) AS failed_count
                FROM notifications
                LEFT JOIN notification_recipients
                    ON notification_recipients.notification_id = notifications.id
                GROUP BY notifications.id
                ORDER BY notifications.id DESC
                LIMIT ?
                """,
                (max(1, int(limit)),),
            ).fetchall()


db = Database(settings.db_path)
