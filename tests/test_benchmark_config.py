from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from benchmark_config import load_benchmark_config  # noqa: E402


def test_default_taiwan_benchmarks_use_local_0050_etf():
    config = load_benchmark_config(None)

    assert config["markets"]["tw"] == {"ticker": "0050.TW", "market": "TW"}
    assert config["markets"]["two"] == {"ticker": "00928.TW", "market": "TW"}


def test_settings_override_can_still_replace_taiwan_benchmark(tmp_path):
    settings = tmp_path / "SETTINGS.md"
    settings.write_text(
        "\n".join(
            [
                "## Benchmark ETFs (optional)",
                "",
                "- Taiwan listed benchmark: EWT",
                "- Taiwan OTC benchmark: none",
            ]
        ),
        encoding="utf-8",
    )

    config = load_benchmark_config(settings)

    assert config["markets"]["tw"] == {"ticker": "EWT", "market": "US"}
    assert config["markets"]["two"] is None
