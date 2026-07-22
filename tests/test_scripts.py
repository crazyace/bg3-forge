"""The dev scripts must at least import cleanly (CI guard against rot)."""

import importlib.util
from pathlib import Path


def test_wiring_survey_imports():
    path = Path(__file__).resolve().parents[1] / "scripts" / "wiring_survey.py"
    spec = importlib.util.spec_from_file_location("wiring_survey", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # runs imports/defs only; main() is guarded
    assert callable(module.main)
