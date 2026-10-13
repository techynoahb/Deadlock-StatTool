"""Remembers your default account ID so you don't have to type it every time."""

from __future__ import annotations

import json
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "deadlock-cli" / "config.json"


def load() -> dict:
    try:
        return json.loads(CONFIG_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(data: dict) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2))


def default_account_id() -> int | None:
    return load().get("account_id")


def set_default_account_id(account_id: int) -> None:
    data = load()
    data["account_id"] = account_id
    save(data)
