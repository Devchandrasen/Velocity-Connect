from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from prototype.velocity_connect.model import MeasurementStore, build_report, validate_sample
from prototype.velocity_connect.server import create_server


def sample(
    sequence: int = 1,
    *,
    condition: str = "baseline",
    run_id: str = "test-run",
    segment_id: str = "segment-001",
    seat_id: str = "1A",
) -> dict[str, object]:
    passive = condition == "passive"
    return {
        "schema_version": "1.0",
        "run_id": run_id,
        "sequence": sequence,
        "condition": condition,
        "source": "demo",
        "timestamp_utc": "2026-07-21T03:00:00+00:00",
        "segment_id": segment_id,
        "seat_id": seat_id,
        "speed_kmph": 300,
        "latitude": 30.0,
        "longitude": 78.0,
        "rsrp_dbm": -96.0 if passive else -108.0,
        "sinr_db": 7.0 if passive else -1.0,
        "dl_mbps": 34.0 if passive else 5.0,
        "ul_mbps": 9.0 if passive else 1.5,
        "latency_ms": 29.0 if passive else 75.0,
        "packet_loss_pct": 1.0 if passive else 14.0,
    }


class PrototypeModelTest(unittest.TestCase):
    def test_validate_sample_normalizes_values(self) -> None:
        result = validate_sample(sample())
        self.assertEqual(result["timestamp_utc"], "2026-07-21T03:00:00Z")
        self.assertEqual(result["speed_kmph"], 300.0)

    def test_validate_sample_rejects_invalid_range_and_schema(self) -> None:
        invalid = sample()
        invalid["rsrp_dbm"] = -200
        with self.assertRaisesRegex(ValueError, "rsrp_dbm"):
            validate_sample(invalid)
        invalid = sample()
        invalid["schema_version"] = "2.0"
        with self.assertRaisesRegex(ValueError, "schema_version"):
            validate_sample(invalid)

    def test_validate_sample_requires_timezone_and_safe_identity(self) -> None:
        invalid = sample()
        invalid["timestamp_utc"] = "2026-07-21T03:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            validate_sample(invalid)
        invalid = sample()
        invalid["run_id"] = "unsafe\nrun"
        with self.assertRaisesRegex(ValueError, "control character"):
            validate_sample(invalid)

    def test_store_persists_and_deduplicates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "samples.jsonl"
            store = MeasurementStore(path)
            self.assertTrue(store.add(sample()))
            self.assertFalse(store.add(sample()))
            self.assertTrue(store.add(sample(condition="passive")))
            self.assertEqual(path.read_text(encoding="utf-8").count("\n"), 2)
            reloaded = MeasurementStore(path)
            self.assertEqual(reloaded.status()["sample_count"], 2)

    def test_store_rejects_corrupt_historical_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "samples.jsonl"
            path.write_text("not-json\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, ":1"):
                MeasurementStore(path)

    def test_store_rejects_duplicate_historical_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "samples.jsonl"
            encoded = json.dumps(validate_sample(sample()))
            path.write_text(encoded + "\n" + encoded + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate evidence identity"):
                MeasurementStore(path)

    def test_store_cap_is_explicit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = MeasurementStore(Path(temporary) / "samples.jsonl", max_samples=1)
            store.add(sample())
            with self.assertRaisesRegex(OverflowError, "full"):
                store.add(sample(2))

    def test_concurrent_writes_do_not_corrupt_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "samples.jsonl"
            store = MeasurementStore(path)
            with ThreadPoolExecutor(max_workers=8) as pool:
                accepted = list(pool.map(lambda index: store.add(sample(index)), range(20)))
            self.assertEqual(sum(accepted), 20)
            self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), 20)
            self.assertEqual(MeasurementStore(path).status()["sample_count"], 20)

    def test_report_requires_paired_location(self) -> None:
        empty = build_report([])
        self.assertFalse(empty["ready"])
        self.assertIn("no samples", empty["reason"])
        report = build_report([sample()])
        self.assertFalse(report["ready"])
        self.assertEqual(report["paired"]["pairs"], 0)
        unpaired = sample(2, condition="passive", segment_id="segment-002")
        report = build_report([sample(), unpaired])
        self.assertFalse(report["ready"])
        self.assertEqual(report["paired"]["unpaired_locations"], 2)

    def test_report_computes_directional_improvements(self) -> None:
        report = build_report([sample(), sample(2, condition="passive")])
        self.assertTrue(report["ready"])
        self.assertEqual(report["paired"]["pairs"], 1)
        self.assertAlmostEqual(report["paired"]["rsrp_gain_db"], 12.0)
        self.assertAlmostEqual(report["paired"]["latency_reduction_ms"], 46.0)
        self.assertAlmostEqual(report["paired"]["outage_reduction_pct_points"], 100.0)


class PrototypeHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        dashboard = root / "dashboard.html"
        dashboard.write_text("<!doctype html><title>test</title>", encoding="utf-8")
        self.store = MeasurementStore(root / "samples.jsonl")
        self.server = create_server("127.0.0.1", 0, self.store, dashboard)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def _get_json(self, path: str) -> dict[str, object]:
        with urlopen(self.base_url + path, timeout=2) as response:
            return json.loads(response.read())

    def _post(self, payload: object) -> tuple[int, dict[str, object]]:
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.base_url + "/api/v1/samples",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return response.status, json.loads(response.read())

    def test_http_health_ingest_duplicate_and_report(self) -> None:
        self.assertEqual(self._get_json("/healthz")["status"], "ok")
        status, accepted = self._post(sample())
        self.assertEqual(status, 201)
        self.assertTrue(accepted["accepted"])
        status, duplicate = self._post(sample())
        self.assertEqual(status, 200)
        self.assertTrue(duplicate["duplicate"])
        self._post(sample(2, condition="passive"))
        report = self._get_json("/api/v1/report")
        self.assertTrue(report["ready"])
        self.assertEqual(self._get_json("/api/v1/status")["sample_count"], 2)

    def test_http_invalid_sample_has_visible_error(self) -> None:
        invalid = sample()
        invalid.pop("rsrp_dbm")
        body = json.dumps(invalid).encode("utf-8")
        request = Request(
            self.base_url + "/api/v1/samples", data=body, method="POST"
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 400)
        error = json.loads(raised.exception.read())
        self.assertIn("rsrp_dbm", error["error"])
        self.assertEqual(self.store.status()["sample_count"], 0)

    def test_http_dashboard_and_unknown_routes(self) -> None:
        with urlopen(self.base_url + "/", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertIn(b"<title>test</title>", response.read())
        with self.assertRaises(HTTPError) as raised:
            urlopen(self.base_url + "/missing", timeout=2)
        self.assertEqual(raised.exception.code, 404)

        request = Request(self.base_url + "/missing", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 404)

    def test_http_body_protocol_errors_are_visible(self) -> None:
        port = self.server.server_address[1]

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.request("POST", "/api/v1/samples", body=b"{")
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        self.assertIn("valid UTF-8 JSON", json.loads(response.read())["error"])
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.putrequest("POST", "/api/v1/samples")
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 411)
        response.read()
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.putrequest("POST", "/api/v1/samples")
        connection.putheader("Content-Length", str(64 * 1024 + 1))
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 413)
        response.read()
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        connection.putrequest("POST", "/api/v1/samples")
        connection.putheader("Content-Length", "not-a-number")
        connection.endheaders()
        response = connection.getresponse()
        self.assertEqual(response.status, 400)
        response.read()
        connection.close()

    def test_http_storage_limit_and_failure_are_visible(self) -> None:
        self.store.max_samples = 1
        self._post(sample())
        with self.assertRaises(HTTPError) as raised:
            self._post(sample(2))
        self.assertEqual(raised.exception.code, 507)
        self.assertIn("full", json.loads(raised.exception.read())["error"])

        with patch.object(self.store, "add", side_effect=OSError("disk unavailable")):
            with self.assertRaises(HTTPError) as raised:
                self._post(sample(3))
        self.assertEqual(raised.exception.code, 500)
        self.assertIn("persistence failed", json.loads(raised.exception.read())["error"])

    def test_create_server_requires_dashboard_file(self) -> None:
        missing = Path(self.temporary.name) / "missing.html"
        with self.assertRaisesRegex(FileNotFoundError, "dashboard not found"):
            create_server("127.0.0.1", 0, self.store, missing)


if __name__ == "__main__":
    unittest.main()
