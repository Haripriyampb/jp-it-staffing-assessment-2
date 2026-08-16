"""Lead + settings persistence backed by a CSV file and a JSON settings file."""

import json
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd

import config

COLUMNS = [
    "id",
    "business_name",
    "owner_name",
    "email",
    "phone",
    "country",
    "source",
    "website",
    "score",
    "contacted",
    "created_at",
]

DEFAULT_SETTINGS: dict[str, Any] = {
    "catalog_filename": "",
    "email_subject": "",
    "email_template": "",
    "emails_sent": 0,
    "emails_failed": 0,
}


def _ensure_dirs() -> None:
    os.makedirs(os.path.dirname(config.LEADS_CSV_PATH) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(config.SETTINGS_PATH) or ".", exist_ok=True)


def init_storage() -> None:
    _ensure_dirs()
    if not os.path.exists(config.LEADS_CSV_PATH):
        pd.DataFrame(columns=COLUMNS).to_csv(config.LEADS_CSV_PATH, index=False)
    if not os.path.exists(config.SETTINGS_PATH):
        _write_settings(dict(DEFAULT_SETTINGS))


def read_leads() -> pd.DataFrame:
    init_storage()
    frame = pd.read_csv(config.LEADS_CSV_PATH, dtype=str, keep_default_na=False)
    for column in COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    frame = frame[COLUMNS]
    frame["id"] = pd.to_numeric(frame["id"], errors="coerce").fillna(0).astype(int)
    frame["score"] = (
        pd.to_numeric(frame["score"], errors="coerce").fillna(0).astype(int)
    )
    frame["contacted"] = frame["contacted"].isin(["Yes", "yes", "True", "true", "1"])
    return frame


def _write_leads(frame: pd.DataFrame) -> None:
    out = frame.copy()
    out["contacted"] = out["contacted"].map(lambda flag: "Yes" if flag else "No")
    out[COLUMNS].to_csv(config.LEADS_CSV_PATH, index=False)


def list_leads() -> list[dict[str, Any]]:
    frame = read_leads().sort_values(["score", "id"], ascending=[False, False])
    return frame.to_dict("records")


def get_lead(lead_id: int) -> dict[str, Any] | None:
    frame = read_leads()
    match = frame[frame["id"] == lead_id]
    return match.iloc[0].to_dict() if not match.empty else None


def add_lead(lead: dict[str, Any]) -> bool:
    """Append a lead. Returns False when a lead with the same email already exists."""
    frame = read_leads()
    email = (lead.get("email") or "").strip().lower()
    if (
        email
        and not frame.empty
        and (frame["email"].str.strip().str.lower() == email).any()
    ):
        return False

    row = {
        "id": int(frame["id"].max()) + 1 if not frame.empty else 1,
        "business_name": lead.get("business_name", ""),
        "owner_name": lead.get("owner_name", ""),
        "email": lead.get("email", ""),
        "phone": lead.get("phone", ""),
        "country": lead.get("country", ""),
        "source": lead.get("source", ""),
        "website": lead.get("website", ""),
        "score": int(lead.get("score") or 0),
        "contacted": bool(lead.get("contacted", False)),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    frame = pd.concat([frame, pd.DataFrame([row])], ignore_index=True)
    _write_leads(frame)
    return True


def delete_lead(lead_id: int) -> bool:
    frame = read_leads()
    remaining = frame[frame["id"] != lead_id]
    if len(remaining) == len(frame):
        return False
    _write_leads(remaining)
    return True


def mark_contacted(lead_id: int, contacted: bool = True) -> None:
    frame = read_leads()
    frame.loc[frame["id"] == lead_id, "contacted"] = contacted
    _write_leads(frame)


def _read_settings() -> dict[str, Any]:
    init_storage()
    try:
        with open(config.SETTINGS_PATH, encoding="utf-8") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError):
        data = {}
    return {**DEFAULT_SETTINGS, **data}


def _write_settings(settings: dict[str, Any]) -> None:
    _ensure_dirs()
    with open(config.SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, indent=2)


def get_setting(name: str, default: str = "") -> str:
    value = _read_settings().get(name, default)
    return default if value in ("", None) else str(value)


def set_setting(name: str, value: str) -> None:
    settings = _read_settings()
    settings[name] = value
    _write_settings(settings)


def get_counter(name: str) -> int:
    try:
        return int(_read_settings().get(name, 0))
    except (TypeError, ValueError):
        return 0


def increment_counter(name: str, amount: int = 1) -> None:
    settings = _read_settings()
    settings[name] = get_counter(name) + amount
    _write_settings(settings)


def stats() -> dict[str, int]:
    frame = read_leads()
    return {
        "total": len(frame),
        "contacted": int(frame["contacted"].sum()) if not frame.empty else 0,
        "emails_sent": get_counter("emails_sent"),
        "emails_failed": get_counter("emails_failed"),
    }
