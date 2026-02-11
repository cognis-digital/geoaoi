# GEOAOI — Architecture

> Area-of-interest geospatial helper: bounding boxes, geofence checks, and change-event diffs from coordinate logs.

```
input ──▶ collect ──▶ rules/analyzers ──▶ score ──▶ findings ──▶ table · json
                              │                          │
                         (this repo)                 MCP tool (agents)
```

- **collect** normalizes the target (file/dir/API) into records.
- **rules/analyzers** apply the heuristics shipped in `geoaoi/core.py`.
- **score** ranks by severity.
- **MCP server** (`geoaoi mcp`) exposes `scan` for Cognis.Studio agents.

Extend by adding a rule + a test + a `demos/NN-*/SCENARIO.md`. See [CONTRIBUTING.md](../CONTRIBUTING.md).
