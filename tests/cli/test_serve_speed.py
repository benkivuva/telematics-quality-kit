"""CLI parsing for a running simulator clock speed."""

import pytest

from telematics.cli import main as cli_main


def test_serve_speed_flag_is_parsed_and_forwarded(monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, object] = {}

    def fake_serve(**kwargs: object) -> int:
        called.update(kwargs)
        return 0

    monkeypatch.setattr(cli_main, "_serve", fake_serve)

    status = cli_main.main(["serve", "--speed", "60x"])

    assert status == 0
    assert called["speed"] == 60.0


def test_serve_rejects_invalid_speed_with_usage_exit_code() -> None:
    with pytest.raises(SystemExit) as raised:
        cli_main.main(["serve", "--speed", "0x"])

    assert raised.value.code == 2
