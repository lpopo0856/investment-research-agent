#!/usr/bin/env python3
"""Quarantined legacy SQLite importer for DB-to-Markdown migration.

This module is the only planned long-lived SQLite reader in the Markdown
ledger architecture.  It exists to read old ``transactions.db`` files during
``migration prepare/apply``.  It is not a runtime store, not a cache, and not a
fallback path for normal account/report operation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

LEGACY_TRANSACTION_DB_FILENAME = "transactions.db"
LEGACY_MARKET_CACHE_FILENAME = "market_data_cache.db"


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    """Open a legacy SQLite DB read-only via URI mode."""
    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def dump_legacy_transactions(db_path: Path) -> List[Dict[str, Any]]:
    """Return legacy transaction rows plus auxiliary lot-consumption metadata.

    The returned shape intentionally mirrors the current migration adapter's
    row dictionary contract so conversion can move here incrementally without
    changing event semantics.
    """
    if not db_path.exists():
        return []
    conn = connect_readonly(db_path)
    try:
        rows: List[Dict[str, Any]] = []
        for row in conn.execute("SELECT * FROM transactions ORDER BY date ASC, id ASC"):
            data = {key: row[key] for key in row.keys()}
            lots = list(
                conn.execute(
                    "SELECT acq_date, cost, qty FROM sell_lot_consumption WHERE transaction_id = ?",
                    (row["id"],),
                )
            )
            if lots:
                data["lots"] = [
                    {"acq_date": lot["acq_date"], "cost": lot["cost"], "qty": lot["qty"]}
                    for lot in lots
                ]
            rows.append(data)
        return rows
    finally:
        conn.close()
