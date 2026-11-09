"""Static report determinism, accessibility, styling, and safety tests."""

import re
from dataclasses import replace
from datetime import timedelta
from html.parser import HTMLParser

import pytest

from telematics.cli import main as cli_main
from telematics.report.builder import FaultSpec, build_report_data
from telematics.report.render import render_report
from telematics.report.svg import render_track


class ReportParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.attrs: list[dict[str, str | None]] = []
        self.svg: list[dict[str, bool]] = []
        self._svg_depth = 0
        self._style_depth = 0
        self.style_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.append(dict(attrs))
        if tag == "svg":
            self.svg.append({"title": False, "desc": False})
            self._svg_depth += 1
        elif tag == "style":
            self._style_depth += 1
        elif self._svg_depth and tag in {"title", "desc"}:
            self.svg[-1][tag] = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "svg":
            self._svg_depth -= 1
        elif tag == "style":
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self.style_text.append(data)


def _parse(html: str) -> ReportParser:
    parser = ReportParser()
    parser.feed(html)
    parser.close()
    return parser


@pytest.mark.integration
def test_report_is_byte_deterministic_for_same_seed_and_options() -> None:
    options = {
        "seed": 42,
        "vehicles": 2,
        "duration": timedelta(seconds=60),
        "clean": True,
        "detail": 2,
    }

    first = render_report(build_report_data(**options))
    second = render_report(build_report_data(**options))

    assert first.encode("utf-8") == second.encode("utf-8")


@pytest.mark.integration
def test_report_has_security_accessibility_and_design_contracts() -> None:
    report = build_report_data(
        seed=42,
        vehicles=2,
        duration=timedelta(seconds=60),
        faults=(FaultSpec("gps_drift", "TRK-0001", "high"),),
        detail=2,
    )
    html = render_report(report)
    parser = _parse(html)
    tags = parser.tags
    styles = " ".join(parser.style_text)

    assert "script" not in tags and "link" not in tags
    assert not re.search(r"@import|url\s*\(", styles, re.IGNORECASE)
    assert all(not ("src" in attrs or "href" in attrs) for attrs in parser.attrs)
    assert "default-src &#x27;none&#x27;; style-src &#x27;unsafe-inline&#x27;" in html
    assert "--bg:" in styles and "--text:" in styles and "--border:" in styles
    assert "@media (prefers-color-scheme: light)" in styles
    assert "@media print" in styles
    assert "system-ui" in styles and "ui-monospace" in styles
    assert "--pass:" in styles and "--warn:" in styles and "--block:" in styles
    assert "--pass: #39c98a" in styles
    assert "--warn: #efad50" in styles
    assert "--block: #f05a68" in styles
    assert "linear-gradient" not in styles
    assert "background:transparent!important" in re.sub(r"\s+", "", styles)
    assert "blackout-mark" in html
    assert "<polygon" in render_track(report.vehicles[0])
    assert parser.svg and all(svg["title"] and svg["desc"] for svg in parser.svg)
    assert tags.count("table") == tags.count("caption")
    csp = next(
        attrs
        for tag, attrs in zip(tags, parser.attrs)
        if tag == "meta" and attrs.get("http-equiv") == "Content-Security-Policy"
    )
    assert csp.get("content") == "default-src 'none'; style-src 'unsafe-inline'"


@pytest.mark.integration
def test_hostile_dynamic_vehicle_text_is_escaped_before_html_parsing() -> None:
    report = build_report_data(
        seed=42,
        vehicles=1,
        duration=timedelta(seconds=30),
        clean=True,
        detail=1,
    )
    hostile = '<img src=x onerror="alert(1)"><script>alert(1)</script>'
    vehicle = replace(report.vehicles[0], vehicle_id=hostile, profile_name=hostile)
    html = render_report(replace(report, vehicles=(vehicle,)))
    parser = _parse(html)

    assert "img" not in parser.tags and "script" not in parser.tags
    assert "&lt;script&gt;" in html
    assert "&lt;img" in html


@pytest.mark.integration
def test_report_faults_are_visible_and_svg_marks_use_geometry() -> None:
    report = build_report_data(
        seed=42,
        vehicles=1,
        duration=timedelta(seconds=60),
        faults=(FaultSpec("rural_blackout", "TRK-0001", "medium"),),
        detail=1,
    )
    html = render_report(report)

    assert "rural_blackout" in html
    assert "blackout-mark" in html
    assert '<path class="blackout-mark"' in html


@pytest.mark.integration
def test_block_report_withholds_location_and_track_values() -> None:
    report = build_report_data(
        seed=42,
        vehicles=1,
        duration=timedelta(minutes=6),
        faults=(FaultSpec("stale_device", "TRK-0001", "high"),),
        detail=1,
    )

    assert report.vehicles[0].summary.data_quality.verdict.value == "BLOCK"
    html = render_report(report)

    assert "coordinates withheld" in html
    assert "Coordinates are withheld because this vehicle has a BLOCK verdict." in html
    assert "<polyline" not in html


def test_report_cli_writes_a_deterministic_file(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "fleet.html"
    args = [
        "report",
        "--vehicles",
        "1",
        "--seed",
        "42",
        "--duration",
        "30s",
        "--clean",
        "--out",
        str(target),
    ]

    assert cli_main.main(args) == 0
    first = target.read_bytes()
    assert cli_main.main(args) == 0
    assert target.read_bytes() == first
    assert "wrote report" in capsys.readouterr().out


def test_report_cli_loads_safe_scenario_and_applies_its_fault(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    scenario = tmp_path / "drill.yaml"
    scenario.write_text(
        "name: cli-drill\nseed: 9\nvehicles: 1\nduration: 30s\nfaults:\n"
        "  - fault: stale_device\n    vehicle_id: TRK-0001\n    severity: high\n",
        encoding="utf-8",
    )
    target = tmp_path / "scenario-report.html"

    status = cli_main.main(["report", "--scenario", str(scenario), "--out", str(target)])

    assert status == 0
    html = target.read_text(encoding="utf-8")
    assert "cli-drill" in html
    assert "stale_device" in html
    assert "BLOCK" in html
    assert "--scenario" in html
    assert "wrote report" in capsys.readouterr().out


def test_report_cli_warns_when_output_exceeds_five_megabytes(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli_main, "render_report", lambda _data: "x" * (5 * 1024 * 1024 + 1))
    target = tmp_path / "large.html"

    status = cli_main.main(
        ["report", "--vehicles", "1", "--duration", "30s", "--clean", "--out", str(target)]
    )

    assert status == 0
    assert "over 5 MB" in capsys.readouterr().err
    assert target.stat().st_size > 5 * 1024 * 1024
