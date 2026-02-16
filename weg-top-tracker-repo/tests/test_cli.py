import sys

import pytest

from wegtop import cli


def test_cli_parse_exits_on_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["wegtop", "parse", "--in_dir", str(tmp_path), "--out_dir", str(tmp_path / "out")],
    )
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "No PDFs found in" in str(exc.value)


def test_cli_no_subcommand_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["wegtop"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1


def test_cli_categorize_exits_on_missing_input(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["wegtop", "categorize", "--input", str(tmp_path / "nonexistent.xlsx")],
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "Input file not found" in str(exc.value)


def test_cli_categorize_exits_on_missing_api_key(tmp_path, monkeypatch):
    input_file = tmp_path / "tracker.xlsx"
    input_file.touch()
    monkeypatch.setattr(
        sys,
        "argv",
        ["wegtop", "categorize", "--input", str(input_file)],
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert "OPENAI_API_KEY" in str(exc.value)
