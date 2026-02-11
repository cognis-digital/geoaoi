"""GEOAOI MCP server — exposes scan() as an MCP tool for Cognis.Studio."""
from __future__ import annotations
from geoaoi.core import scan, to_json

def serve() -> int:
    """Start an MCP stdio server. Requires the optional 'mcp' extra:
        pip install "cognis-geoaoi[mcp]"
    """
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception:
        print("Install the MCP extra: pip install 'cognis-geoaoi[mcp]'")
        return 1
    app = FastMCP("geoaoi")

    @app.tool()
    def geoaoi_scan(target: str) -> str:
        """Area-of-interest geospatial helper: bounding boxes, geofence checks, and change-event diffs from coordinate logs.. Returns JSON findings."""
        return to_json(scan(target))

    app.run()
    return 0
