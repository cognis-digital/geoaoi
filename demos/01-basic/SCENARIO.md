# Demo 01 — Basic AOI workflow

A defensive GEOINT-metadata walkthrough using two coordinate logs of
friendly-asset positions around the National Mall, Washington DC.
Everything here is analysis/monitoring only — no targeting or control.

## Inputs

- `track_t0.csv` — asset positions at 12:00Z
- `track_t1.csv` — same assets at 12:30Z (one entered, one exited, one moved)

## 1. Bounding box of the area covered

```bash
python -m geoaoi bbox demos/01-basic/track_t0.csv
```

Reports the min/max lat-lon envelope, its center, and ground width/height
in meters — useful for sizing a map tile or AOI request.

## 2. Geofence membership (circular fence)

Is each asset within 2 km of a watch point near the Mall?

```bash
python -m geoaoi geofence demos/01-basic/track_t0.csv \
    --name mall-watch --center 38.8895,-77.0200 --radius 2000
```

Add `--require-inside` to make the command exit non-zero (alertable) if any
asset has left the AOI. The table includes a `distance_m` column for circles.

## 3. Geofence membership (polygon)

```bash
python -m geoaoi geofence demos/01-basic/track_t0.csv \
    --name corridor --polygon "38.880,-77.050;38.880,-77.000;38.900,-77.000;38.900,-77.050"
```

## 4. Change-event diff between the two epochs

```bash
python -m geoaoi --format json diff demos/01-basic/track_t0.csv demos/01-basic/track_t1.csv
```

Produces `enter` / `exit` / `move` / `static` events per asset, with the
displacement in meters. Use `--fail-on-change` in monitoring pipelines to
exit non-zero whenever movement is detected, and `--threshold` to tune the
move sensitivity.

Expected: ASSET-02 = move (~3.5 km), ASSET-03 = static (~14 m),
ASSET-04 = exit, ASSET-05 = enter, ASSET-01 = static.
