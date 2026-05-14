"""Tests for ui.settings_io — read, diff/token, write, backup, staleness."""

import shutil
from pathlib import Path

import pytest

import ui.accounts as _accounts_mod
import ui.settings_io as _settings_mod


@pytest.fixture()
def fixture_account(tmp_path, monkeypatch):
    """Create a temporary accounts root with a 'fixture' account copied from default."""
    # Build tmp accounts root: tmp_path/accounts/fixture/
    accounts_root = tmp_path / "accounts"
    fixture_dir = accounts_root / "fixture"
    fixture_dir.mkdir(parents=True)

    # Copy tracked fixture settings, never private local account settings.
    real_settings = (
        Path(__file__).resolve().parent / "fixtures" / "accounts" / "default" / "SETTINGS.md"
    )
    shutil.copy(real_settings, fixture_dir / "SETTINGS.md")

    # Monkey-patch ACCOUNTS_ROOT in both modules so resolve_account_path resolves correctly
    monkeypatch.setattr(_accounts_mod, "ACCOUNTS_ROOT", accounts_root.resolve())
    monkeypatch.setattr(_settings_mod, "_accounts", _accounts_mod)

    return fixture_dir


# ---------------------------------------------------------------------------
# read_settings
# ---------------------------------------------------------------------------

def test_read_settings_returns_file_content(fixture_account):
    expected = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    from ui.settings_io import read_settings
    assert read_settings("fixture") == expected


# ---------------------------------------------------------------------------
# build_diff
# ---------------------------------------------------------------------------

def test_build_diff_returns_token_and_diff(fixture_account):
    from ui.settings_io import build_diff
    original = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    appended_line = "\n# test-sentinel-line\n"
    new_content = original + appended_line

    result = build_diff("fixture", new_content)

    assert "token" in result
    assert len(result["token"]) == 16
    assert result["token"].isalnum()
    assert appended_line.strip() in result["unified_diff"]


# ---------------------------------------------------------------------------
# write_settings — happy path (backup created)
# ---------------------------------------------------------------------------

def test_write_settings_creates_backup(fixture_account):
    from ui.settings_io import build_diff, write_settings
    original = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    new_content = original + "\n# written-by-test\n"

    diff_result = build_diff("fixture", new_content)
    token = diff_result["token"]

    write_result = write_settings("fixture", new_content, token)

    backup_path = Path(write_result["backup_path"])
    assert backup_path.name.startswith("SETTINGS.md.bak.")
    assert backup_path.read_text(encoding="utf-8") == original


def test_write_settings_updates_file(fixture_account):
    from ui.settings_io import build_diff, write_settings
    original = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    new_content = original + "\n# updated-content\n"

    diff_result = build_diff("fixture", new_content)
    write_settings("fixture", new_content, diff_result["token"])

    assert (fixture_account / "SETTINGS.md").read_text(encoding="utf-8") == new_content


# ---------------------------------------------------------------------------
# write_settings — token mismatch
# ---------------------------------------------------------------------------

def test_write_settings_wrong_token_raises(fixture_account):
    from ui.settings_io import build_diff, write_settings
    original = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    new_content = original + "\n# sentinel\n"

    build_diff("fixture", new_content)  # register a valid pending entry

    with pytest.raises(ValueError, match="token invalid or expired"):
        write_settings("fixture", new_content, "0000000000000000")


# ---------------------------------------------------------------------------
# write_settings — stale-old: file changed on disk after build_diff
# ---------------------------------------------------------------------------

def test_write_settings_stale_old_raises(fixture_account):
    from ui.settings_io import build_diff, write_settings
    original = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    new_content = original + "\n# proposed\n"

    diff_result = build_diff("fixture", new_content)
    token = diff_result["token"]

    # Directly mutate the file on disk — simulates concurrent modification
    (fixture_account / "SETTINGS.md").write_text(original + "\n# interleaved-write\n", encoding="utf-8")

    with pytest.raises(ValueError, match="token invalid or expired"):
        write_settings("fixture", new_content, token)


# ---------------------------------------------------------------------------
# Section parsing & per-section editing
# ---------------------------------------------------------------------------

from ui.settings_io import (  # noqa: E402
    build_section_diff,
    list_sections,
    write_section,
)


def test_list_sections_parses_level2_headings(fixture_account):
    result = list_sections("fixture")
    names = [s["name"] for s in result["sections"]]
    # default's SETTINGS.md has Language, Investment Style And Strategy, Base currency...
    assert "Language" in names
    assert "Investment Style And Strategy" in names
    # Indices are 0..N-1
    assert [s["index"] for s in result["sections"]] == list(range(len(result["sections"])))


def test_list_sections_body_is_byte_preserving(fixture_account):
    result = list_sections("fixture")
    on_disk = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    reassembled = result["preamble"] + "".join(s["body"] for s in result["sections"])
    assert reassembled == on_disk


def test_section_edit_roundtrip(fixture_account):
    original = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    sections = list_sections("fixture")["sections"]
    # Edit the first section by appending a probe line.
    sec = sections[0]
    new_body = sec["body"].rstrip("\n") + "\n<!-- probe -->\n"

    preview = build_section_diff("fixture", sec["index"], new_body)
    assert "<!-- probe -->" in preview["unified_diff"]
    assert len(preview["token"]) == 16

    write_section("fixture", sec["index"], new_body, preview["token"])

    after = (fixture_account / "SETTINGS.md").read_text(encoding="utf-8")
    assert "<!-- probe -->" in after
    # Other sections untouched: the rest of the file (everything outside section 0's body)
    # must equal the rest of the original.
    sections_after = list_sections("fixture")["sections"]
    for i, s_after in enumerate(sections_after):
        if i == 0:
            continue
        assert s_after["body"] == sections[i]["body"], f"section {i} changed unexpectedly"


def test_section_index_out_of_range_raises(fixture_account):
    with pytest.raises(ValueError, match="section index out of range"):
        build_section_diff("fixture", 999, "## bogus\n")


def test_section_write_token_validation(fixture_account):
    sections = list_sections("fixture")["sections"]
    sec = sections[0]
    new_body = sec["body"].rstrip("\n") + "\n<!-- a -->\n"

    preview = build_section_diff("fixture", sec["index"], new_body)
    # External mutation of the file invalidates the token.
    p = fixture_account / "SETTINGS.md"
    p.write_text(p.read_text(encoding="utf-8") + "\nexternal\n", encoding="utf-8")
    with pytest.raises(ValueError, match="token invalid or expired"):
        write_section("fixture", sec["index"], new_body, preview["token"])
