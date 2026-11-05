"""Saves which Deadlock account belongs to which Discord user (SQLite)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB = Path("deadlock_bot.db")


class LinkStore:
    def __init__(self, path: str | Path = DEFAULT_DB):
        self.conn = sqlite3.connect(str(path))
        self.conn.execute(
            """CREATE TABLE IF NOT EXISTS links (
                   discord_id INTEGER PRIMARY KEY,
                   account_id INTEGER NOT NULL
               )"""
        )
        self.conn.commit()

    def link(self, discord_id: int, account_id: int) -> None:
        self.conn.execute(
            "INSERT INTO links (discord_id, account_id) VALUES (?, ?) "
            "ON CONFLICT(discord_id) DO UPDATE SET account_id = excluded.account_id",
            (discord_id, account_id),
        )
        self.conn.commit()

    def unlink(self, discord_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM links WHERE discord_id = ?", (discord_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def get(self, discord_id: int) -> int | None:
        row = self.conn.execute(
            "SELECT account_id FROM links WHERE discord_id = ?", (discord_id,)
        ).fetchone()
        return row[0] if row else None

    def close(self) -> None:
        self.conn.close()
