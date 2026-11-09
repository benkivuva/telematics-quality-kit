"""Accessible, local SVG tracks and freshness timelines."""

from html import escape

from telematics.models.quality import Verdict
from telematics.report.builder import ReportVehicle

_WIDTH = 600
_HEIGHT = 220
_PAD = 22


def render_track(vehicle: ReportVehicle) -> str:
    """Draw a normalized track and mark drift or coverage issues geometrically."""
    points = vehicle.summary.points
    latitudes = [point.latitude for point in points]
    longitudes = [point.longitude for point in points]
    min_lat, max_lat = min(latitudes), max(latitudes)
    min_lon, max_lon = min(longitudes), max(longitudes)
    lat_span = max(max_lat - min_lat, 0.0001)
    lon_span = max(max_lon - min_lon, 0.0001)
    coordinates = [
        (
            _PAD + (point.longitude - min_lon) / lon_span * (_WIDTH - 2 * _PAD),
            _HEIGHT - _PAD - (point.latitude - min_lat) / lat_span * (_HEIGHT - 2 * _PAD),
        )
        for point in points
    ]
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
    last_x, last_y = coordinates[-1]
    checks = {check.name: check.verdict for check in vehicle.summary.data_quality.checks}
    drift = "gps_drift" in vehicle.active_faults or checks.get("drift") is not Verdict.PASS
    blackout = bool(
        {"rural_blackout", "stale_device"}.intersection(vehicle.active_faults)
        or checks.get("freshness") is not Verdict.PASS
    )
    markers = [
        f'<circle class="track-dot" cx="{x:.2f}" cy="{y:.2f}" r="2.2" />' for x, y in coordinates
    ]
    if drift:
        markers.append(
            f'<polygon class="drift-mark" points="{last_x:.2f},{last_y - 7:.2f} '
            f'{last_x - 6:.2f},{last_y + 5:.2f} {last_x + 6:.2f},{last_y + 5:.2f}" />'
        )
    if blackout:
        markers.append(
            f'<path class="blackout-mark" d="M {last_x - 5:.2f},{last_y - 5:.2f} '
            f"L {last_x + 5:.2f},{last_y + 5:.2f} M {last_x + 5:.2f},{last_y - 5:.2f} "
            f'L {last_x - 5:.2f},{last_y + 5:.2f}" />'
        )
    vehicle_id = escape(vehicle.vehicle_id)
    description = "Local projection of the reported GPS path; no map tiles are used."
    return (
        f'<svg class="track" viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img">'
        f"<title>Track for {vehicle_id}</title><desc>{description}</desc>"
        f'<polyline class="track-line" points="{polyline}" />' + "".join(markers) + "</svg>"
    )


def render_withheld_track(vehicle: ReportVehicle) -> str:
    """Show fault geometry without coordinates when BLOCK withholds locations."""
    checks = {check.name: check.verdict for check in vehicle.summary.data_quality.checks}
    center_x, center_y = _WIDTH / 2, _HEIGHT / 2
    markers: list[str] = []
    if "gps_drift" in vehicle.active_faults or checks.get("drift") is not Verdict.PASS:
        markers.append(
            f'<polygon class="drift-mark" points="{center_x:.1f},{center_y - 8:.1f} '
            f'{center_x - 7:.1f},{center_y + 6:.1f} {center_x + 7:.1f},{center_y + 6:.1f}" />'
        )
    if {"rural_blackout", "stale_device"}.intersection(vehicle.active_faults) or checks.get(
        "freshness"
    ) is not Verdict.PASS:
        markers.append(
            f'<path class="blackout-mark" d="M {center_x - 6:.1f},{center_y - 6:.1f} '
            f"L {center_x + 6:.1f},{center_y + 6:.1f} M {center_x + 6:.1f},{center_y - 6:.1f} "
            f'L {center_x - 6:.1f},{center_y + 6:.1f}" />'
        )
    vehicle_id = escape(vehicle.vehicle_id)
    return (
        f'<svg class="track" viewBox="0 0 {_WIDTH} {_HEIGHT}" role="img">'
        f"<title>Track withheld for {vehicle_id}</title>"
        "<desc>Coordinates are withheld because this vehicle has a BLOCK verdict.</desc>"
        + "".join(markers)
        + "</svg>"
    )


def render_timeline(vehicle: ReportVehicle) -> str:
    """Show point arrivals and gaps as a compact geometric freshness timeline."""
    points = vehicle.summary.points
    times = [point.device_time.timestamp() for point in points]
    start, end = min(times), max(times)
    span = max(end - start, 1.0)
    y = 28.0
    locations = [(_PAD + (value - start) / span * (_WIDTH - 2 * _PAD), y) for value in times]
    markers: list[str] = []
    for index, ((x, _), current_time) in enumerate(zip(locations, times, strict=True)):
        markers.append(f'<circle class="arrival-dot" cx="{x:.2f}" cy="{y:.2f}" r="3" />')
        if index and current_time - times[index - 1] > vehicle.expected_interval_seconds * 2:
            previous_x = locations[index - 1][0]
            markers.append(
                f'<line class="timeline-gap" x1="{previous_x:.2f}" y1="{y:.2f}" '
                f'x2="{x:.2f}" y2="{y:.2f}" />'
            )
    vehicle_id = escape(vehicle.vehicle_id)
    description = f"{len(points)} report arrivals; dashed segments mark heuristic gaps."
    return (
        f'<svg class="timeline" viewBox="0 0 {_WIDTH} 56" role="img">'
        f"<title>Freshness timeline for {vehicle_id}</title><desc>{description}</desc>"
        f'<line class="timeline-axis" x1="{_PAD}" y1="{y:.2f}" '
        f'x2="{_WIDTH - _PAD}" y2="{y:.2f}" />' + "".join(markers) + "</svg>"
    )
