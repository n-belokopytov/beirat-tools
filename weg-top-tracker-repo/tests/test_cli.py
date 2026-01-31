import sys

import pytest

from wegtop import cli


def test_cli_exits_on_empty_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys,
        "argv",
        ["wegtop", "--in_dir", str(tmp_path), "--out_dir", str(tmp_path / "out")],
    )
    with pytest.raises(SystemExit):
        cli.main()
