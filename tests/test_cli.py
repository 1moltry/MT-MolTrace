"""CLI catalog wiring and config normalization (no analysis side effects)."""

from __future__ import annotations

import pytest

from nanopore.cli import build_parser, main
from nanopore.config import PipelineConfig
from nanopore.registry import detector_ids


def _run_args(*extra: str):
    return ["run", "not-needed.abf", *extra]


def test_cli_accepts_every_registered_detector():
    parser = build_parser()
    for det in detector_ids():
        args = parser.parse_args(_run_args("--detector", det))
        assert args.detector == det

    with pytest.raises(SystemExit):
        parser.parse_args(_run_args("--detector", "not-a-detector"))


def test_cli_save_config_normalizes_detector_and_modules(tmp_path):
    out = tmp_path / "saved.json"
    rc = main(_run_args("--detector", "plateau", "--mods", "refined_anomaly",
                        "--save-config", str(out)))
    assert rc == 0
    cfg = PipelineConfig.load(out)
    assert cfg.detector == "plateau"
    assert cfg.event_mode == "level"
    assert cfg.enabled_mods == ("dynamic_i0", "anomaly", "refined_anomaly")
