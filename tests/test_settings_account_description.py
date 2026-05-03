from __future__ import annotations

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import account  # noqa: E402
from portfolio_snapshot import (  # noqa: E402
    BookPacing,
    SCHEMA_VERSION,
    Snapshot,
    deserialize_snapshot,
    parse_settings_profile,
    serialize_snapshot,
)


def test_parse_settings_profile_reads_account_description(tmp_path: Path):
    settings = tmp_path / "SETTINGS.md"
    settings.write_text(
        "\n".join(
            [
                "## Account description (optional)",
                "",
                "- Description: Taiwan tax-aware core account",
                "",
                "## Language",
                "",
                "- traditional chinese",
                "",
                "## Base currency (optional, default USD)",
                "",
                "- Base currency: TWD",
                "",
                "## Investment Style And Strategy",
                "- Description: this strategy description is not the account purpose",
            ]
        ),
        encoding="utf-8",
    )

    profile = parse_settings_profile(settings)

    assert profile.account_description == "Taiwan tax-aware core account"
    assert profile.locale == "zh-Hant"
    assert profile.base_currency == "TWD"


def test_snapshot_settings_round_trip_preserves_account_description(tmp_path: Path):
    settings = tmp_path / "SETTINGS.md"
    settings.write_text(
        "\n".join(
            [
                "## Account description (optional)",
                "- Description: Roth IRA for long-term US equities",
                "## Language",
                "- english",
            ]
        ),
        encoding="utf-8",
    )
    profile = parse_settings_profile(settings)

    snap = Snapshot(
        schema_version=SCHEMA_VERSION,
        generated_at="2026-05-04T00:00:00Z",
        today="2026-05-04",
        base_currency=profile.base_currency,
        settings_locale=profile.locale,
        settings_display_name=profile.display_name,
        settings_raw_language=profile.raw_language,
        settings_missing=profile.missing,
        settings_account_description=profile.account_description,
        config={},
        aggregates={},
        totals={},
        fx={},
        fx_details={},
        missing_fx=[],
        book_pacing=BookPacing(
            avg_hold_years=None,
            oldest=None,
            newest=None,
            pct_held_over_1y=None,
            distribution_pct={},
        ),
        risk_heat=[],
        special_checks=[],
    )
    payload = serialize_snapshot(snap)
    restored = deserialize_snapshot(payload)

    assert payload["settings"]["account_description"] == "Roth IRA for long-term US equities"
    assert restored.settings_account_description == "Roth IRA for long-term US equities"


def test_read_account_description_is_safe_read_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(account, "REPO_ROOT", tmp_path)
    acct = tmp_path / "accounts" / "japan"
    acct.mkdir(parents=True)
    (acct / "SETTINGS.md").write_text(
        "\n".join(
            [
                "## Account description (optional)",
                "- Description: Japan sleeve for yen-denominated equities",
                "## Investment Style And Strategy",
                "- Description: Not the account description",
            ]
        ),
        encoding="utf-8",
    )

    assert account.read_account_description("japan") == "Japan sleeve for yen-denominated equities"
    assert account.read_account_description("missing") == ""
    assert account.read_account_description("Bad Name") == ""
