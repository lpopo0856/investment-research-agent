"""Markdown ledger event-file helpers for the non-destructive migration path.

This module intentionally has no dependency on ``transactions.py`` so it can be
used by migration, lint, cache, and report-archive tooling without creating an
import cycle.  It parses and writes account-local event files such as::

    accounts/<account>/ledger/events/2026/05/txn-20260513-000001-buy-nvda.md

Generated cache files are rebuildable artifacts and must carry the DO_NOT_EDIT
marker defined here; canonical history lives only in event Markdown files plus
migration/archive durable records outside ``ledger/generated``.
"""

from __future__ import annotations

import datetime as _dt
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

LEDGER_SCHEMA = "investment-ledger-event/v1"
CACHE_SCHEMA = "investment-ledger-generated-cache/v1"
DB_CANONICAL = "db_canonical"
DUAL_READ_PARITY = "dual_read_parity"
CUTOVER_PROPOSAL_READY = "cutover_proposal_ready"
MARKDOWN_CANONICAL = "markdown_canonical"
STORE_STATES = {
    DB_CANONICAL,
    DUAL_READ_PARITY,
    CUTOVER_PROPOSAL_READY,
    MARKDOWN_CANONICAL,
}
DO_NOT_EDIT = "DO_NOT_EDIT: generated from canonical Markdown ledger events; rebuild with tooling."

EVENT_FIELD_ORDER: Sequence[str] = (
    "schema",
    "id",
    "date",
    "type",
    "ticker",
    "qty",
    "price",
    "gross",
    "fees",
    "net",
    "amount",
    "currency",
    "cash_account",
    "bucket",
    "market",
    "from_amount",
    "from_currency",
    "from_cash_account",
    "to_amount",
    "to_currency",
    "to_cash_account",
    "rate",
    "target_event_id",
    "legacy_db_id",
    "legacy_target_id",
    "source",
    "source_ref",
    "created_at",
    "tags",
    "rationale",
)

_FIELD_RE = re.compile(r"^\s*-\s*(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(?P<value>.*?)\s*$")
_LOT_RE = re.compile(
    r"^\s*-\s+(?P<acq_date>\d{4}-\d{2}-\d{2})@(?P<cost>[^\s:]*[0-9][0-9.,]*)\s*:\s*(?P<qty>-?[0-9.,]+)\s*$"
)
_NUMERIC_CLEAN_RE = re.compile(r"[^\d.\-]")
_SLUG_RE = re.compile(r"[^a-z0-9._-]+")
_EVENT_ID_RE = re.compile(r"^txn-(?P<date>\d{8})-(?P<ord>\d{6})-(?P<kind>[a-z0-9_]+)(?:-(?P<ticker>[a-z0-9._-]+))?$")


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ledger_dir_for_account_dir(account_dir: Path) -> Path:
    return account_dir / "ledger"


def events_dir(ledger_dir: Path) -> Path:
    return ledger_dir / "events"


def generated_dir(ledger_dir: Path) -> Path:
    return ledger_dir / "generated"


def migrations_dir(ledger_dir: Path) -> Path:
    return ledger_dir / "migrations"


def archive_reports_dir(ledger_dir: Path) -> Path:
    return ledger_dir / "archive" / "reports"


def normalize_event_id(value: str) -> str:
    return value.strip().lower()


def slugify(value: Optional[str]) -> str:
    if value is None:
        return "cash"
    cleaned = _SLUG_RE.sub("-", value.strip().lower()).strip("-._")
    return cleaned or "cash"


def event_id_for(date: str, txn_type: str, ticker: Optional[str], ordinal: int) -> str:
    compact_date = date.replace("-", "")
    suffix = slugify(ticker)
    return f"txn-{compact_date}-{ordinal:06d}-{txn_type.lower()}-{suffix}"


def event_path_for(ledger_dir: Path, event: Dict[str, Any]) -> Path:
    event_id = normalize_event_id(str(event["id"]))
    date = str(event["date"])
    year, month = date[0:4], date[5:7]
    return events_dir(ledger_dir) / year / month / f"{event_id}.md"


def ordinal_from_event_id(event_id: str) -> Optional[int]:
    m = _EVENT_ID_RE.match(normalize_event_id(event_id))
    if not m:
        return None
    return int(m.group("ord"))


def sort_key(event: Dict[str, Any], fallback_index: int = 0) -> Tuple[str, int, str]:
    event_id = str(event.get("id") or "")
    ordinal = ordinal_from_event_id(event_id)
    return (str(event.get("date") or ""), ordinal if ordinal is not None else fallback_index, event_id)


def parse_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text or text == "?":
        return None
    cleaned = _NUMERIC_CLEAN_RE.sub("", text)
    if cleaned in {"", ".", "-"}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _stringify(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.10f}".rstrip("0").rstrip(".")
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    return str(value)


def _encode_field_value(value: Any) -> str:
    text = _stringify(value)
    if "\n" in text or "\r" in text:
        raw = text.encode("utf-8")
        return "base64:" + base64.b64encode(raw).decode("ascii")
    return text


def _decode_field_value(value: str) -> str:
    if value.startswith("base64:"):
        try:
            return base64.b64decode(value[len("base64:"):].encode("ascii")).decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - validation surfaces bad event content
            raise ValueError(f"invalid base64 field value: {exc}") from exc
    return value


def format_event_markdown(event: Dict[str, Any]) -> str:
    missing = validate_event_dict(event)
    if missing:
        raise ValueError("invalid event: " + "; ".join(missing))

    event_id = normalize_event_id(str(event["id"]))
    ticker = event.get("ticker")
    heading_ticker = f" {ticker}" if ticker not in (None, "") else ""
    lines: List[str] = [
        f"# {event_id}",
        "",
        f"## {event['date']} {str(event['type']).upper()}{heading_ticker}",
    ]
    seen = set()
    for key in EVENT_FIELD_ORDER:
        if key not in event:
            continue
        value = event.get(key)
        if value in (None, ""):
            continue
        lines.append(f"- {key}: {_encode_field_value(value)}")
        seen.add(key)
    for key in sorted(k for k in event.keys() if k not in seen and k != "lots" and not str(k).startswith("_")):
        value = event.get(key)
        if value in (None, ""):
            continue
        lines.append(f"- {key}: {_encode_field_value(value)}")

    lots = event.get("lots") or []
    if lots:
        lines.extend(["", "## Lots Consumed"])
        for lot in lots:
            lines.append(f"- {lot['acq_date']}@{_stringify(lot['cost'])}: {_stringify(lot['qty'])}")
    return "\n".join(lines).rstrip() + "\n"


def write_event_file(event: Dict[str, Any], path: Path) -> None:
    text = format_event_markdown(event)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing != text:
            raise FileExistsError(f"refusing to overwrite divergent event file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def parse_event_text(text: str, *, source_path: Optional[Path] = None) -> Dict[str, Any]:
    fields: Dict[str, Any] = {}
    lots: List[Dict[str, Any]] = []
    in_lots = False
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.strip().lower() in {"## lots consumed", "### lots consumed"}:
            in_lots = True
            continue
        lot_match = _LOT_RE.match(line)
        if in_lots and lot_match:
            cost = parse_number(lot_match.group("cost"))
            qty = parse_number(lot_match.group("qty"))
            if cost is not None and qty is not None:
                lots.append({
                    "acq_date": lot_match.group("acq_date"),
                    "cost": cost,
                    "qty": qty,
                })
            continue
        field_match = _FIELD_RE.match(line)
        if field_match:
            key = field_match.group("key").lower().replace("-", "_")
            fields[key] = _decode_field_value(field_match.group("value").strip())
            in_lots = False
            continue
        if line.startswith("#"):
            continue
    if source_path is not None:
        fields.setdefault("_path", str(source_path))
    if lots:
        fields["lots"] = lots
    return fields


def parse_event_file(path: Path) -> Dict[str, Any]:
    return parse_event_text(path.read_text(encoding="utf-8"), source_path=path)


def load_event_dicts(ledger_dir: Path) -> List[Dict[str, Any]]:
    root = events_dir(ledger_dir)
    if not root.exists():
        return []
    events = [parse_event_file(path) for path in sorted(root.glob("**/*.md"))]
    ids: Dict[str, Path] = {}
    for idx, event in enumerate(events):
        event_id = normalize_event_id(str(event.get("id") or ""))
        if not event_id:
            raise ValueError(f"ledger event missing id: {event.get('_path', '<unknown>')}")
        if event_id in ids:
            raise ValueError(f"duplicate event id {event_id}: {ids[event_id]} and {event.get('_path')}")
        ids[event_id] = Path(str(event.get("_path", "")))
        event["id"] = event_id
    indexed = list(enumerate(events))
    indexed.sort(key=lambda pair: sort_key(pair[1], pair[0]))
    return [event for _idx, event in indexed]


def validate_event_dict(event: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    for key in ("schema", "id", "date", "type"):
        if event.get(key) in (None, ""):
            errors.append(f"missing {key}")
    if event.get("schema") not in (None, "", LEDGER_SCHEMA):
        errors.append(f"unsupported schema {event.get('schema')!r}")
    txn_type = str(event.get("type") or "").upper()
    if txn_type in {"BUY", "SELL"}:
        for key in ("ticker", "qty", "price"):
            if event.get(key) in (None, ""):
                errors.append(f"{txn_type} missing {key}")
    if txn_type in {"DEPOSIT", "WITHDRAW", "DIVIDEND", "FEE"} and event.get("amount") in (None, ""):
        errors.append(f"{txn_type} missing amount")
    if txn_type == "FX_CONVERT":
        for key in ("from_amount", "from_currency", "to_amount", "to_currency"):
            if event.get(key) in (None, ""):
                errors.append(f"FX_CONVERT missing {key}")
    if txn_type == "REVERSAL" and event.get("target_event_id") in (None, ""):
        errors.append("REVERSAL missing target_event_id")
    event_id = str(event.get("id") or "")
    if event_id and not event_id.startswith("txn-"):
        errors.append("id must start with txn-")
    date = str(event.get("date") or "")
    try:
        if date:
            _dt.date.fromisoformat(date)
    except ValueError:
        errors.append(f"invalid date {date!r}")
    for key in ("qty", "price", "gross", "fees", "net", "amount", "from_amount", "to_amount", "rate"):
        if key in event and event.get(key) not in (None, "") and parse_number(event.get(key)) is None:
            errors.append(f"invalid numeric {key}")
    for lot in event.get("lots") or []:
        if not isinstance(lot, dict):
            errors.append("lot must be an object")
            continue
        if not lot.get("acq_date"):
            errors.append("lot missing acq_date")
        if parse_number(lot.get("cost")) is None:
            errors.append("lot missing/invalid cost")
        if parse_number(lot.get("qty")) is None:
            errors.append("lot missing/invalid qty")
    return errors


def validate_event_set(events: Sequence[Dict[str, Any]]) -> List[str]:
    errors: List[str] = []
    ids = set()
    for event in events:
        path = event.get("_path") or event.get("id") or "<unknown>"
        for err in validate_event_dict(event):
            errors.append(f"{path}: {err}")
        event_id = normalize_event_id(str(event.get("id") or ""))
        if event_id:
            if event_id in ids:
                errors.append(f"duplicate id {event_id}")
            ids.add(event_id)
    for event in events:
        target = normalize_event_id(str(event.get("target_event_id") or ""))
        if target and target not in ids:
            errors.append(f"{event.get('_path') or event.get('id')}: unknown target_event_id {target}")
    return errors


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_tree(root: Path) -> str:
    h = hashlib.sha256()
    if not root.exists():
        return hashlib.sha256(b"").hexdigest()
    for path in sorted(p for p in root.glob("**/*") if p.is_file()):
        h.update(str(path.relative_to(root)).encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def generated_payload(name: str, ledger_dir: Path, data: Any, *, generated_at: Optional[str] = None) -> Dict[str, Any]:
    return {
        "_meta": {
            "schema": CACHE_SCHEMA,
            "name": name,
            "generated_at": generated_at or now_utc(),
            "source_tree_hash": hash_tree(events_dir(ledger_dir)),
            "notice": DO_NOT_EDIT,
        },
        "data": data,
    }


def ensure_ledger_skeleton(ledger_dir: Path) -> None:
    events_dir(ledger_dir).mkdir(parents=True, exist_ok=True)
    generated_dir(ledger_dir).mkdir(parents=True, exist_ok=True)
    migrations_dir(ledger_dir).mkdir(parents=True, exist_ok=True)
    archive_reports_dir(ledger_dir).mkdir(parents=True, exist_ok=True)
    readme = ledger_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Markdown ledger\n\n"
            "Canonical transaction history lives in `events/`. Generated files under "
            "`generated/` are rebuildable and must not be edited by hand. Legacy SQLite "
            "evidence is import/archive-only after migration.\n",
            encoding="utf-8",
        )
    schema = ledger_dir / "schema.md"
    if not schema.exists():
        schema.write_text(
            "# Ledger schema\n\n"
            f"Current event schema: `{LEDGER_SCHEMA}`. Each event file contains a "
            "stable `id`, `date`, `type`, optional trade/cash/FX fields, migration "
            "metadata, and optional `Lots Consumed` block for SELL/REVERSAL audit.\n",
            encoding="utf-8",
        )
    marker = generated_dir(ledger_dir) / "DO_NOT_EDIT.md"
    marker.write_text(f"# Generated cache directory\n\n{DO_NOT_EDIT}\n", encoding="utf-8")
