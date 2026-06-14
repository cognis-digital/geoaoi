"""Smoke tests for GEOAOI — stdlib unittest, no network."""

import json
import pathlib
import tempfile
import unittest
from io import StringIO
from contextlib import redirect_stdout

from geoaoi import (
    TOOL_NAME,
    TOOL_VERSION,
    Geofence,
    compute_bbox,
    diff_events,
    geofence_check,
    haversine_m,
    parse_points_csv,
    parse_polygon,
    point_in_polygon,
)
from geoaoi.cli import main


T0 = (
    "ident,lat,lon,timestamp\n"
    "ASSET-01,38.8895,-77.0353,2026-06-08T12:00:00Z\n"
    "ASSET-02,38.8899,-77.0091,2026-06-08T12:00:00Z\n"
    "ASSET-03,38.8870,-77.0200,2026-06-08T12:00:00Z\n"
)
T1 = (
    "ident,lat,lon,timestamp\n"
    "ASSET-01,38.8895,-77.0353,2026-06-08T12:30:00Z\n"
    "ASSET-02,38.9100,-77.0400,2026-06-08T12:30:00Z\n"
    "ASSET-05,38.8800,-77.0500,2026-06-08T12:30:00Z\n"
)


class TestGeodesy(unittest.TestCase):
    def test_haversine_known_distance(self):
        # ~1 degree of latitude ~= 111 km.
        d = haversine_m(0.0, 0.0, 1.0, 0.0)
        self.assertAlmostEqual(d, 111195.0, delta=200.0)

    def test_haversine_zero(self):
        self.assertEqual(haversine_m(10.0, 20.0, 10.0, 20.0), 0.0)

    def test_point_in_polygon(self):
        sq = [(0, 0), (0, 10), (10, 10), (10, 0)]
        self.assertTrue(point_in_polygon(5, 5, sq))
        self.assertFalse(point_in_polygon(20, 20, sq))
        self.assertTrue(point_in_polygon(0, 5, sq))  # boundary counts


class TestEngine(unittest.TestCase):
    def test_bbox(self):
        box = compute_bbox(parse_points_csv(T0))
        self.assertEqual(box.count, 3)
        self.assertAlmostEqual(box.min_lon, -77.0353)
        self.assertAlmostEqual(box.max_lon, -77.0091)
        self.assertGreater(box.width_m, 0)

    def test_bbox_empty_raises(self):
        with self.assertRaises(ValueError):
            compute_bbox([])

    def test_geofence_circle(self):
        pts = parse_points_csv(T0)
        fence = Geofence(name="w", center=(38.8895, -77.0200), radius_m=2000)
        res = geofence_check(pts, fence)
        self.assertTrue(all("distance_m" in r for r in res))
        inside = {r["ident"]: r["inside"] for r in res}
        self.assertTrue(inside["ASSET-03"])  # ~14m from center

    def test_geofence_polygon(self):
        pts = parse_points_csv(T0)
        poly = parse_polygon("38.880,-77.050;38.880,-77.000;38.900,-77.000;38.900,-77.050")
        fence = Geofence(name="c", polygon=poly)
        res = geofence_check(pts, fence)
        self.assertEqual(len(res), 3)
        self.assertTrue(all(r["inside"] for r in res))

    def test_diff_events(self):
        events = {e["ident"]: e for e in diff_events(parse_points_csv(T0), parse_points_csv(T1))}
        self.assertEqual(events["ASSET-01"]["event"], "static")
        self.assertEqual(events["ASSET-02"]["event"], "move")
        self.assertEqual(events["ASSET-03"]["event"], "exit")
        self.assertEqual(events["ASSET-05"]["event"], "enter")
        self.assertGreater(events["ASSET-02"]["moved_m"], 1000)

    def test_bad_latitude_rejected(self):
        with self.assertRaises(ValueError):
            parse_points_csv("ident,lat,lon\nX,200,0\n")

    def test_polygon_too_few_vertices(self):
        with self.assertRaises(ValueError):
            parse_polygon("0,0;1,1")

    def test_polygon_extra_comma_raises(self):
        # "lat,lon,extra" should raise a clear ValueError, not a bare unpack error.
        with self.assertRaises(ValueError) as ctx:
            parse_polygon("0,0,extra;1,1;2,2")
        self.assertIn("vertex 1", str(ctx.exception))

    def test_polygon_non_numeric_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_polygon("abc,def;1,1;2,2")
        self.assertIn("non-numeric", str(ctx.exception))

    def test_polygon_out_of_range_lat_raises(self):
        with self.assertRaises(ValueError) as ctx:
            parse_polygon("200,0;1,1;2,2")
        self.assertIn("latitude", str(ctx.exception))

    def test_polygon_empty_spec_raises(self):
        with self.assertRaises(ValueError):
            parse_polygon("")

    def test_diff_negative_threshold_raises(self):
        from geoaoi.core import Point
        with self.assertRaises(ValueError) as ctx:
            diff_events([Point("A", 0.0, 0.0)], [Point("A", 0.0, 0.0)], move_threshold_m=-1.0)
        self.assertIn("move_threshold_m", str(ctx.exception))

    def test_diff_zero_threshold_valid(self):
        # threshold=0 is valid; any displacement >= 0 m counts as a move (haversine=0 still >= 0).
        # The important thing is that it does NOT raise — it produces a result.
        from geoaoi.core import Point
        events = diff_events([Point("A", 0.0, 0.0)], [Point("A", 0.0, 0.0)], move_threshold_m=0.0)
        self.assertEqual(len(events), 1)
        self.assertIn(events[0]["event"], ("static", "move"))


class TestCLI(unittest.TestCase):
    def _run(self, argv):
        buf = StringIO()
        with redirect_stdout(buf):
            code = main(argv)
        return code, buf.getvalue()

    def _write(self, tmp, name, text):
        p = tmp / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_version_metadata(self):
        self.assertEqual(TOOL_NAME, "geoaoi")
        self.assertTrue(TOOL_VERSION)
        with self.assertRaises(SystemExit):
            main(["--version"])

    def test_bbox_json(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            f = self._write(tmp, "t0.csv", T0)
            code, out = self._run(["--format", "json", "bbox", f])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["count"], 3)

    def test_geofence_require_inside_fails(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            f = self._write(tmp, "t0.csv", T0)
            # Tiny fence far away -> all outside -> exit 1.
            code, _ = self._run([
                "geofence", f, "--center", "0,0", "--radius", "10", "--require-inside",
            ])
            self.assertEqual(code, 1)

    def test_diff_fail_on_change(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            a = self._write(tmp, "t0.csv", T0)
            b = self._write(tmp, "t1.csv", T1)
            code, out = self._run(["--format", "json", "diff", a, b, "--fail-on-change"])
            self.assertEqual(code, 1)
            self.assertTrue(json.loads(out))

    def test_missing_file_exit_2(self):
        code, _ = self._run(["bbox", "does-not-exist.csv"])
        self.assertEqual(code, 2)

    def test_geofence_negative_radius_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            f = self._write(tmp, "t0.csv", T0)
            code, _ = self._run(["geofence", f, "--center", "38.89,-77.02", "--radius", "-5"])
            self.assertEqual(code, 2)

    def test_geofence_bad_center_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            f = self._write(tmp, "t0.csv", T0)
            code, _ = self._run(["geofence", f, "--center", "notlat,notlon", "--radius", "100"])
            self.assertEqual(code, 2)

    def test_geofence_bad_polygon_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            f = self._write(tmp, "t0.csv", T0)
            # extra comma in vertex -> clear error, exit 2
            code, _ = self._run(["geofence", f, "--polygon", "0,0,extra;1,1;2,2"])
            self.assertEqual(code, 2)

    def test_diff_negative_threshold_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            a = self._write(tmp, "t0.csv", T0)
            b = self._write(tmp, "t1.csv", T1)
            code, _ = self._run(["diff", a, b, "--threshold", "-1"])
            self.assertEqual(code, 2)

    def test_mcp_server_importable(self):
        # mcp_server must be importable without raising (the mcp package itself is optional).
        import importlib
        mod = importlib.import_module("geoaoi.mcp_server")
        self.assertTrue(callable(getattr(mod, "serve", None)))


if __name__ == "__main__":
    unittest.main()
