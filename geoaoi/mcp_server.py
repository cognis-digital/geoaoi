"""GEOAOI MCP server — exposes core operations as MCP tools for Cognis.Studio."""
from __future__ import annotations

import json


def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-geoaoi[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        print("Install the MCP extra: pip install 'cognis-geoaoi[mcp]'")
        return 1

    from geoaoi.core import (
        Geofence,
        compute_bbox,
        diff_events,
        geofence_check,
        parse_points_csv,
        parse_polygon,
    )

    app = FastMCP("geoaoi")

    @app.tool()
    def geoaoi_bbox(csv_text: str) -> str:
        """Compute bounding box of a coordinate log CSV. Returns JSON with min/max lat/lon, center, dimensions, and count."""
        pts = parse_points_csv(csv_text)
        if not pts:
            return json.dumps({"error": "no valid points in CSV"})
        return json.dumps(compute_bbox(pts).to_dict())

    @app.tool()
    def geoaoi_geofence(
        csv_text: str,
        polygon: str = "",
        center_lat: float = 0.0,
        center_lon: float = 0.0,
        radius_m: float = 0.0,
        fence_name: str = "aoi",
    ) -> str:
        """Check point membership in a geofence. Provide either polygon ('lat,lon;lat,lon;...') or center_lat/center_lon/radius_m. Returns JSON list of per-point results."""
        pts = parse_points_csv(csv_text)
        if polygon:
            fence = Geofence(name=fence_name, polygon=parse_polygon(polygon))
        elif radius_m > 0:
            fence = Geofence(name=fence_name, center=(center_lat, center_lon), radius_m=radius_m)
        else:
            return json.dumps({"error": "provide polygon or center_lat/center_lon/radius_m"})
        return json.dumps(geofence_check(pts, fence))

    @app.tool()
    def geoaoi_diff(
        before_csv: str,
        after_csv: str,
        move_threshold_m: float = 50.0,
    ) -> str:
        """Diff two coordinate log CSVs into change events (enter/exit/move/static). Returns JSON list of events."""
        if move_threshold_m < 0:
            return json.dumps({"error": "move_threshold_m must be >= 0"})
        before = parse_points_csv(before_csv)
        after = parse_points_csv(after_csv)
        return json.dumps(diff_events(before, after, move_threshold_m=move_threshold_m))

    app.run()
    return 0
