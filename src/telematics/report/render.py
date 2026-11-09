"""Secure, self-contained HTML rendering for deterministic fleet reports."""

from datetime import timedelta, timezone
from html import escape

from telematics.models.quality import CheckResult, Verdict
from telematics.report.builder import ReportData, ReportVehicle
from telematics.report.svg import render_timeline, render_track, render_withheld_track

_LABELS = {Verdict.PASS: "trust it", Verdict.WARN: "be careful", Verdict.BLOCK: "don't trust it"}
_SYMBOLS = {Verdict.PASS: "✓", Verdict.WARN: "⚠", Verdict.BLOCK: "⛔"}
_CHECKS = ("freshness", "drift", "duplicates", "ignition", "plausibility", "fuel")
_EAT = timezone(timedelta(hours=3), "EAT")

_CSS = """:root {
  color-scheme: dark;
  --bg: #0b0e10;
  --surface: #111619;
  --surface-raised: #171d20;
  --text: #e5ebed;
  --muted: #88969b;
  --border: #293438;
  --grid: #202a2e;
  --pass: #39c98a;
  --pass-tint: rgba(57, 201, 138, .10);
  --warn: #efad50;
  --warn-tint: rgba(239, 173, 80, .11);
  --block: #f05a68;
  --block-tint: rgba(240, 90, 104, .12);
  --accent: #b7c5c8;
  font-family: system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); }
main { max-width: 1480px; margin: 0 auto; padding: 30px 34px 42px; }
header { border-bottom: 1px solid var(--border); padding-bottom: 22px; }
.topline { display:flex; justify-content:space-between; align-items:center; gap:18px; }
.eyebrow, .section-kicker { color:var(--muted); font-size:11px; font-weight:700; letter-spacing:.13em; text-transform:uppercase; }
.synthetic { color:var(--warn); border:1px solid var(--border); padding:5px 8px; font-size:10px; font-weight:700; letter-spacing:.11em; }
h1 { font-size:27px; line-height:1.15; margin:15px 0 8px; letter-spacing:-.035em; font-weight:650; }
.subtitle { color:var(--muted); margin:0; font-size:13px; }
.metadata { display:flex; flex-wrap:wrap; gap:8px 20px; margin-top:18px; color:var(--muted); font-size:12px; }
.mono, code, time, .numeric { font-family:ui-monospace, 'Cascadia Code', 'Source Code Pro', monospace; font-variant-numeric:tabular-nums; }
.metadata code { color:var(--text); }
section { margin-top:26px; }
.section-head { display:flex; justify-content:space-between; align-items:baseline; gap:18px; margin-bottom:11px; }
h2 { font-size:14px; letter-spacing:.01em; margin:0; font-weight:650; }
.section-note { color:var(--muted); font-size:11px; }
.stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
.stat { min-height:78px; background:var(--surface); border:1px solid var(--border); padding:12px 14px; }
.stat-label { color:var(--muted); font-size:10px; letter-spacing:.1em; text-transform:uppercase; }
.stat-value { display:flex; align-items:baseline; gap:8px; margin-top:8px; font:600 22px ui-monospace, 'Cascadia Code', 'Source Code Pro', monospace; }
.stat-count { color:var(--muted); font-size:11px; font-weight:500; }
.score-track { display:flex; height:4px; margin-top:9px; background:var(--grid); overflow:hidden; }
.score-track span { height:100%; }
.score-track .pass { background:var(--pass); }.score-track .warn { background:var(--warn); }.score-track .block { background:var(--block); }
.verdict { display:inline-flex; gap:5px; align-items:center; border:1px solid currentColor; border-radius:4px; padding:3px 7px; font-size:10px; line-height:1.25; font-weight:700; white-space:nowrap; }
.verdict.pass { color:var(--pass); background:var(--pass-tint); }.verdict.warn { color:var(--warn); background:var(--warn-tint); }.verdict.block { color:var(--block); background:var(--block-tint); }
.fleet-table { width:100%; border-collapse:collapse; border:1px solid var(--border); background:var(--surface); font-size:11px; }
.fleet-table caption { text-align:left; padding:0 0 9px; color:var(--muted); }
.fleet-table th { background:var(--surface-raised); color:var(--muted); text-align:left; font-size:9px; font-weight:700; text-transform:uppercase; letter-spacing:.09em; }
.fleet-table th, .fleet-table td { border-bottom:1px solid var(--grid); padding:8px 9px; vertical-align:middle; }
.fleet-table tbody tr:last-child td { border-bottom:0; }
.fleet-table .numeric { text-align:right; white-space:nowrap; }
.vehicle-id { color:var(--text); font-weight:650; white-space:nowrap; }
.profile-cell { color:var(--muted); }
.check-list { display:flex; flex-wrap:wrap; gap:3px; }
.check-pill { border:1px solid var(--border); padding:2px 4px; border-radius:3px; font-size:9px; white-space:nowrap; }
.check-pill.pass { color:var(--pass); }.check-pill.warn { color:var(--warn); }.check-pill.block { color:var(--block); }
.caveat { color:var(--muted); max-width:250px; }
.vehicle-card { border:1px solid var(--border); background:var(--surface); margin-top:12px; }
.card-head { display:flex; justify-content:space-between; align-items:center; gap:12px; border-bottom:1px solid var(--border); padding:11px 13px; }
.card-title { display:flex; gap:11px; align-items:center; min-width:0; }
.card-title h3 { margin:0; font:600 13px ui-monospace, 'Cascadia Code', 'Source Code Pro', monospace; overflow-wrap:anywhere; }
.card-meta { color:var(--muted); font-size:10px; margin-top:4px; }
.card-body { display:grid; grid-template-columns:minmax(240px,.85fr) minmax(300px,1.15fr); gap:16px; padding:13px; }
.detail-label { color:var(--muted); font-size:9px; text-transform:uppercase; letter-spacing:.1em; margin:0 0 7px; }
.caveats { margin:0 0 13px; padding-left:17px; color:var(--muted); font-size:11px; }
.caveats li { margin:4px 0; }
.check-grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:5px; }
.check-detail { border:1px solid var(--grid); padding:7px; min-width:0; }
.check-detail-head { display:flex; justify-content:space-between; gap:5px; font-size:10px; font-weight:650; }
.metric { color:var(--muted); font-size:9px; line-height:1.5; margin-top:4px; overflow-wrap:anywhere; }
.metric code { color:var(--text); font-size:9px; }
.visual-label { margin-top:12px; }
.track, .timeline { display:block; width:100%; height:auto; overflow:visible; }
.track { background:var(--bg); border:1px solid var(--grid); }
.track-line { fill:none; stroke:var(--accent); stroke-width:1.35; vector-effect:non-scaling-stroke; }
.track-dot { fill:var(--muted); opacity:.6; }.drift-mark { fill:var(--bg); stroke:var(--warn); stroke-width:2; vector-effect:non-scaling-stroke; }
.blackout-mark { fill:none; stroke:var(--block); stroke-width:2; vector-effect:non-scaling-stroke; }
.timeline-axis { stroke:var(--border); stroke-width:1; }.arrival-dot { fill:var(--accent); }.timeline-gap { stroke:var(--warn); stroke-width:2; stroke-dasharray:3 3; }
.fault-list { color:var(--muted); font-size:11px; line-height:1.6; }
.empty { color:var(--muted); font-size:11px; padding:13px; border:1px dashed var(--border); }
footer { border-top:1px solid var(--border); margin-top:28px; padding-top:14px; color:var(--muted); font-size:10px; line-height:1.7; }
footer p { margin:3px 0; }
@media (prefers-color-scheme: light) {
  :root { color-scheme:light; --bg:#f4f6f5; --surface:#fff; --surface-raised:#edf1ef; --text:#17201f; --muted:#657270; --border:#cbd4d1; --grid:#e1e7e4; --pass:#137a50; --pass-tint:rgba(19,122,80,.08); --warn:#98600b; --warn-tint:rgba(152,96,11,.08); --block:#b32435; --block-tint:rgba(179,36,53,.08); --accent:#546460; }
}
@media (max-width:900px) { main {padding:20px 14px 30px}.card-body {grid-template-columns:1fr}.fleet-table {font-size:10px}.check-list {max-width:300px} }
@media (max-width:650px) { .stats {grid-template-columns:repeat(2,minmax(0,1fr))}.fleet-table {display:block;overflow-x:auto}.metadata {gap:8px 12px}h1 {font-size:23px} }
@media print {
  :root, body { color-scheme:light; --bg:#fff; --surface:#fff; --surface-raised:#fff; --text:#000; --muted:#333; --border:#777; --grid:#bbb; --pass:#000; --warn:#000; --block:#000; --pass-tint:transparent; --warn-tint:transparent; --block-tint:transparent; --accent:#222; }
  *, *::before, *::after { color:#000 !important; background:transparent !important; box-shadow:none !important; text-shadow:none !important; }
  main {max-width:none;padding:0}.vehicle-card,.fleet-table,.stat {break-inside:avoid;border-color:#777}.verdict,.check-pill {border-color:#555}.score-track {display:none}.track,.timeline {max-height:180px}
}
"""


def _verdict_class(verdict: Verdict) -> str:
    return verdict.value.lower()


def _render_badge(verdict: Verdict, label: str | None = None) -> str:
    return (
        f'<span class="verdict {_verdict_class(verdict)}">'
        f"{_SYMBOLS[verdict]} {escape(label or _LABELS[verdict])}</span>"
    )


def _check_map(checks: tuple[CheckResult, ...]) -> dict[str, CheckResult]:
    return {check.name: check for check in checks}


def _render_check_pills(vehicle: ReportVehicle) -> str:
    checks = _check_map(vehicle.summary.data_quality.checks)
    parts: list[str] = []
    for name in _CHECKS:
        check = checks.get(name)
        if check is None:
            continue
        verdict_class = _verdict_class(check.verdict)
        parts.append(
            f'<span class="check-pill {verdict_class}" title="{escape(check.verdict.value)}">'
            f"{escape(name[:3])} {_SYMBOLS[check.verdict]}</span>"
        )
    return '<div class="check-list">' + "".join(parts) + "</div>"


def _render_row(vehicle: ReportVehicle) -> str:
    quality = vehicle.summary.data_quality
    age = quality.age_seconds
    caveat = quality.caveats[0] if quality.caveats else "No heuristic checks flagged."
    return (
        "<tr>"
        f'<td class="mono vehicle-id">{escape(vehicle.vehicle_id)}</td>'
        f'<td class="profile-cell">{escape(vehicle.profile_name)} · {escape(vehicle.protocol)}</td>'
        f"<td>{_render_badge(quality.verdict)}</td>"
        f'<td class="numeric mono">{quality.trust_score:.2f}</td>'
        f"<td>{_render_check_pills(vehicle)}</td>"
        f'<td class="numeric mono">{age}s</td>'
        f'<td class="caveat">{escape(caveat)}</td>'
        "</tr>"
    )


def _render_check_detail(check: CheckResult) -> str:
    metrics = " · ".join(
        f"<code>{escape(str(key))}={escape(str(value))}</code>"
        for key, value in sorted(check.metric.items())
    )
    verdict_class = _verdict_class(check.verdict)
    return (
        f'<div class="check-detail {verdict_class}">'
        f'<div class="check-detail-head"><span>{escape(check.name)}</span>'
        f"<span>{_SYMBOLS[check.verdict]} {escape(check.verdict.value)}</span></div>"
        f'<div class="metric">score {check.score:.2f} · {metrics}</div></div>'
    )


def _render_vehicle_card(vehicle: ReportVehicle) -> str:
    summary = vehicle.summary
    quality = summary.data_quality
    caveats = quality.caveats or ("No current heuristic checks flagged.",)
    caveat_html = "".join(f"<li>{escape(caveat)}</li>" for caveat in caveats)
    checks_html = "".join(_render_check_detail(check) for check in quality.checks)
    faults = ", ".join(escape(item) for item in vehicle.active_faults) or "none"
    latest = summary.latest
    if quality.usable_for_decision:
        location = f"{latest.latitude:.5f}, {latest.longitude:.5f}"
        visuals = f"{render_track(vehicle)}{render_timeline(vehicle)}"
    else:
        location = "coordinates withheld"
        visuals = render_withheld_track(vehicle)
    return (
        '<article class="vehicle-card">'
        '<div class="card-head"><div class="card-title">'
        f"<div><h3>{escape(vehicle.vehicle_id)}</h3>"
        f'<div class="card-meta">{escape(vehicle.profile_name)} · {escape(vehicle.protocol)} · '
        f"{location} · {latest.device_time.isoformat()}</div></div></div>"
        f"{_render_badge(quality.verdict)}</div>"
        '<div class="card-body"><div><p class="detail-label">Why this verdict</p>'
        f'<ul class="caveats">{caveat_html}</ul><p class="detail-label">Faults in this run</p>'
        f'<div class="fault-list">{faults}</div><p class="detail-label visual-label">Quality checks</p>'
        f'<div class="check-grid">{checks_html}</div></div>'
        '<div><p class="detail-label">Local track · geometric projection</p>'
        f'{visuals}<p class="detail-label visual-label">Freshness timeline · expected interval '
        f"{vehicle.expected_interval_seconds}s</p></div></div></article>"
    )


def render_report(report: ReportData) -> str:
    """Render report data as escaped, single-file HTML with a strict CSP."""
    shown = report.vehicles[: report.detail]
    total = len(report.vehicles)
    shown_note = f"showing {len(shown)} of {total}, worst first"
    rows = "".join(_render_row(vehicle) for vehicle in shown)
    cards = "".join(_render_vehicle_card(vehicle) for vehicle in shown)
    counts = report.verdict_counts
    pass_count = counts.get(Verdict.PASS, 0)
    warn_count = counts.get(Verdict.WARN, 0)
    block_count = counts.get(Verdict.BLOCK, 0)
    pass_width = pass_count / total * 100 if total else 0
    warn_width = warn_count / total * 100 if total else 0
    block_width = block_count / total * 100 if total else 0
    eat_start = report.start.astimezone(_EAT).strftime("%Y-%m-%d %H:%M:%S EAT")
    eat_end = report.end.astimezone(_EAT).strftime("%Y-%m-%d %H:%M:%S EAT")
    fault_lines = (
        "".join(
            f"<li>{escape(spec.fault)} on {escape(spec.vehicle_id)} · {escape(spec.severity)}</li>"
            for spec in report.faults
        )
        or "<li>none</li>"
    )
    csp = escape("default-src 'none'; style-src 'unsafe-inline'")
    return "".join(
        [
            '<!doctype html><html lang="en"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width,initial-scale=1">',
            f'<meta http-equiv="Content-Security-Policy" content="{csp}">',
            f"<title>Fleet quality report · {escape(report.scenario)}</title>",
            f"<style>{_CSS}</style></head><body><main>",
            '<header><div class="topline"><span class="eyebrow">Telematics quality / report</span>',
            '<span class="synthetic">SYNTHETIC DATA</span></div>',
            "<h1>Fleet quality report</h1>",
            (
                f'<p class="subtitle">Scenario: <strong>{escape(report.scenario)}</strong> · '
                f"seed <code>{report.seed}</code> · tool version 0.1.0</p>"
            ),
            f'<div class="metadata"><span>Window <time>{eat_start}</time> → <time>{eat_end}</time></span>',
            f'<div>Faults <ul class="fault-list">{fault_lines}</ul></div></div></header>',
            '<section aria-labelledby="summary-heading"><div class="section-head">',
            '<h2 id="summary-heading">Fleet summary</h2><span class="section-note">heuristic scoring · ',
            f'{total} vehicles</span></div><div class="stats">',
            f'<div class="stat"><div class="stat-label">Fleet trust score</div><div class="stat-value">{report.fleet_trust_score:.2f}</div>',
            f'<div class="score-track" role="img" aria-label="Verdict distribution: {pass_count} pass, {warn_count} warn, {block_count} block">',
            f'<span class="pass" style="width:{pass_width:.2f}%"></span>',
            f'<span class="warn" style="width:{warn_width:.2f}%"></span>',
            f'<span class="block" style="width:{block_width:.2f}%"></span></div></div>',
            f'<div class="stat"><div class="stat-label">Trust it</div><div class="stat-value" style="color:var(--pass)">✓ {pass_count}</div></div>',
            f'<div class="stat"><div class="stat-label">Be careful</div><div class="stat-value" style="color:var(--warn)">⚠ {warn_count}</div></div>',
            f'<div class="stat"><div class="stat-label">Don’t trust it</div><div class="stat-value" style="color:var(--block)">⛔ {block_count}</div></div>',
            "</div></section>",
            '<section aria-labelledby="vehicles-heading"><div class="section-head">',
            '<h2 id="vehicles-heading">Vehicles</h2>',
            f'<span class="section-note">{escape(shown_note)}</span></div>',
            '<table class="fleet-table"><caption>Worst-first synthetic fleet quality; values use configured heuristic thresholds.</caption>',
            '<thead><tr><th scope="col">Vehicle</th><th scope="col">Profile / protocol</th>',
            '<th scope="col">Verdict</th><th scope="col" class="numeric">Trust</th>',
            '<th scope="col">Checks</th><th scope="col" class="numeric">Age</th>',
            '<th scope="col">Top caveat</th></tr></thead><tbody>',
            rows or '<tr><td colspan="7">No vehicles.</td></tr>',
            "</tbody></table></section>",
            '<section aria-labelledby="detail-heading"><div class="section-head">',
            '<h2 id="detail-heading">Vehicle detail</h2>',
            '<span class="section-note">checks, report cadence, and local track</span></div>',
            cards or '<div class="empty">No vehicle detail is available.</div>',
            "</section><footer><p>Scoring contract v0.1 · thresholds are heuristics, not ground truth.</p>",
            f"<p>Regenerate: <code>{escape(report.command)}</code> · seed {report.seed}</p>",
            "<p>PASS = trust it · WARN = be careful · BLOCK = don’t trust it. A BLOCK withholds values.</p>",
            "</footer></main></body></html>",
        ]
    )
