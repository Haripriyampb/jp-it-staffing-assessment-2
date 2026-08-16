import os
import sqlite3
from typing import Any

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    business_name TEXT NOT NULL DEFAULT '',
    owner_name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    contacted INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_email
    ON leads(email) WHERE email <> '';

CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""

LEAD_FIELDS = (
    "business_name",
    "owner_name",
    "email",
    "phone",
    "country",
    "source",
    "website",
    "score",
)


def connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def add_lead(lead: dict[str, Any]) -> bool:
    """Insert a lead. Returns False when a lead with the same email already exists."""
    values = {field: lead.get(field, "") for field in LEAD_FIELDS}
    values["score"] = int(lead.get("score") or 0)
    columns = ", ".join(LEAD_FIELDS)
    placeholders = ", ".join(f":{field}" for field in LEAD_FIELDS)
    with connect() as conn:
        try:
            conn.execute(
                f"INSERT INTO leads ({columns}) VALUES ({placeholders})", values
            )
        except sqlite3.IntegrityError:
            return False
    return True


def list_leads() -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM leads ORDER BY score DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_lead(lead_id: int) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    return dict(row) if row else None


def delete_lead(lead_id: int) -> bool:
    with connect() as conn:
        cursor = conn.execute("DELETE FROM leads WHERE id = ?", (lead_id,))
    return cursor.rowcount > 0


def mark_contacted(lead_id: int, contacted: bool = True) -> None:
    with connect() as conn:
        conn.execute(
            "UPDATE leads SET contacted = ? WHERE id = ?",
            (1 if contacted else 0, lead_id),
        )


def increment_counter(name: str, amount: int = 1) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO counters (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = value + excluded.value",
            (name, amount),
        )


def get_counter(name: str) -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM counters WHERE name = ?", (name,)
        ).fetchone()
    return int(row["value"]) if row else 0


def set_setting(name: str, value: str) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO settings (name, value) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (name, value),
        )


def get_setting(name: str, default: str = "") -> str:
    with connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE name = ?", (name,)
        ).fetchone()
    return row["value"] if row else default


def stats() -> dict[str, int]:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, COALESCE(SUM(contacted), 0) AS contacted FROM leads"
        ).fetchone()
    return {
        "total": int(row["total"]),
        "contacted": int(row["contacted"]),
        "emails_sent": get_counter("emails_sent"),
        "emails_failed": get_counter("emails_failed"),
    }
