import sqlite3
from pathlib import Path

from telegram.ext import ChatMemberHandler, MessageHandler

from bot import build_application
from database import Database
from parser import extract_email_from_chat, extract_email_from_chat_title, normalize_email_list


def test_build_application_registers_chat_member_handler():
    app = build_application()
    handlers = [handler for group in app.handlers.values() for handler in group]
    assert any(isinstance(handler, ChatMemberHandler) for handler in handlers)
    assert any(isinstance(handler, MessageHandler) for handler in handlers)


def test_normalize_email_list_removes_duplicates_and_invalid():
    text = """
    partner1@gmail.com
    partner2@gmail.com
    unknown@gmail.com
    partner3@gmail.com
    partner1@gmail.com
    """
    assert normalize_email_list(text) == [
        "partner1@gmail.com",
        "partner2@gmail.com",
        "unknown@gmail.com",
        "partner3@gmail.com",
    ]


def test_extract_email_from_chat_title_accepts_list_ru_email():
    assert extract_email_from_chat_title("RP $ 15th@list.ru") == "15th@list.ru"


def test_extract_email_from_chat_prefers_title_then_description():
    assert extract_email_from_chat("Partner | title@example.com", "description@example.com") == "title@example.com"
    assert extract_email_from_chat("Partner", "Контакт: description@example.com") == "description@example.com"


def test_database_detects_conflicting_active_chats(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    db.upsert_partner_chat("same@gmail.com", -1001, "Chat 1")
    db.upsert_partner_chat("same@gmail.com", -1002, "Chat 2")

    rows = db.get_active_chats_for_email("same@gmail.com")
    assert len(rows) == 2
    assert {row["chat_id"] for row in rows} == {-1001, -1002}


def test_database_persists_managers(tmp_path: Path):
    db = Database(tmp_path / "test.db")

    db.add_manager(42, 1)

    assert db.is_manager(42)
    assert [row["user_id"] for row in db.get_managers()] == [42]
    db.remove_manager(42)
    assert not db.is_manager(42)


def test_database_returns_recent_notifications_with_delivery_counts(tmp_path: Path):
    db = Database(tmp_path / "test.db")
    notification_id = db.save_notification(42, "Test notification")
    db.save_recipients(
        notification_id,
        [
            {"email": "sent@example.com", "chat_id": -1, "status": "sent", "error": None, "sent_at": "2026-09-22"},
            {"email": "failed@example.com", "chat_id": -2, "status": "failed", "error": "Forbidden", "sent_at": None},
        ],
    )

    history = db.get_recent_notifications()

    assert len(history) == 1
    assert history[0]["message_text"] == "Test notification"
    assert history[0]["total_recipients"] == 2
    assert history[0]["sent_count"] == 1
    assert history[0]["failed_count"] == 1


def test_database_migrates_legacy_partner_chat_schema(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE partner_chats (
                email TEXT PRIMARY KEY,
                chat_id INTEGER NOT NULL,
                chat_title TEXT,
                active INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO partner_chats VALUES (?, ?, ?, ?, ?, ?)",
            ("15th@list.ru", -1001, "RP $ 15th@list.ru", 1, "2026-09-22", "2026-09-22"),
        )

    db = Database(db_path)

    db.upsert_partner_chat("15th@list.ru", -1002, "Second chat")
    rows = db.get_active_chats_for_email("15th@list.ru")
    assert {row["chat_id"] for row in rows} == {-1001, -1002}
