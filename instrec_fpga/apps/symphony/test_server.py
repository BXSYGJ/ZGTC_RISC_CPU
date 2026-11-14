"""Exercise actual frozen model APIs, local HTTP boundaries and optional UART I/O."""

import hashlib
from http.client import HTTPConnection
import json
from pathlib import Path
import shutil
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import server


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="instrec-symphony-http-")
        root = Path(cls.temp.name)
        (root / "index.html").write_text('<script type="module" src="app.mjs"></script>', encoding="utf-8")
        (root / "app.mjs").write_text('export const title = "交响导聆";', encoding="utf-8")
        (root / "server.py").write_text("private source", encoding="utf-8")
        cls.state = server.AppState(app_root=root)
        cls.http = server.LocalHTTPServer(0, cls.state)
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.quiet = patch.object(server.Handler, "log_message", lambda *a: None)
        cls.quiet.start()
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join(timeout=2)
        cls.quiet.stop()
        cls.temp.cleanup()

    def request(self, path, method="GET", body=None, headers=None):
        conn = HTTPConnection("127.0.0.1", self.http.server_port, timeout=5)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def post(self, path, obj, headers=None):
        return self.request(path, "POST", json.dumps(obj),
                            {"Content-Type": "application/json", **(headers or {})})

    def test_project_uses_actual_deployment_class_order(self):
        code, _, raw = self.request("/api/project")
        value = json.loads(raw)
        self.assertEqual(code, 200)
        self.assertEqual(value["live"]["class_order"],
                         ["clarinet", "distorted electric guitar", "female singer", "flute",
                          "piano", "tenor saxophone", "trumpet", "violin"])
        self.assertEqual(value["live"]["system_clock_hz"], 125000000)
        self.assertFalse(value["reference"]["fpga_deployed"])
        self.assertFalse(value["live"]["full_probabilities_available"])
        self.assertFalse(value["capabilities"]["audio_inference"])

    def test_mjs_is_javascript_and_head_has_no_body(self):
        code, headers, raw = self.request("/app.mjs")
        self.assertEqual(code, 200)
        self.assertEqual(headers["Content-Type"], "text/javascript; charset=utf-8")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("交响导聆", raw.decode("utf-8"))
        code, headers, raw = self.request("/app.mjs", "HEAD")
        self.assertEqual((code, raw), (200, b""))
        self.assertGreater(int(headers["Content-Length"]), 0)

    def test_static_root_and_source_are_not_exposed(self):
        for path in ("/server.py", "/run.ps1", "/%2e%2e/AGENTS.md", "/..%5cAGENTS.md",
                     "/.git/config", "/%00", "/%ff", "/api/unknown"):
            with self.subTest(path=path):
                code, _, raw = self.request(path)
                self.assertGreaterEqual(code, 400)
                self.assertNotIn(b"private source", raw)

    def test_loopback_host_required(self):
        code, _, raw = self.request("/api/project", headers={"Host": "example.com"})
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(raw)["error"]["code"], "invalid_host")

    def test_actual_reference_logits_and_frozen_activations(self):
        import numpy as np
        code, _, raw = self.request("/api/reference")
        self.assertEqual(code, 200)
        value = json.loads(raw)
        source = server.MODEL_ROOT / "reference_vectors.npz"
        self.assertEqual(value["source"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertFalse(value["continuous"])
        self.assertFalse(value["audio_available"])
        self.assertEqual(value["segment_seconds"], 1.5)
        samples = value["samples"]
        self.assertEqual([s["row_index"] for s in samples], [17285, 17284, 17287, 34713, 31108])
        self.assertEqual(len(set(s["id"] for s in samples)), 5)
        with np.load(source, allow_pickle=False) as frozen:
            for i, sample in enumerate(samples):
                self.assertEqual((sample["start_seconds"], sample["end_seconds"]), (0, 1.5))
                np.testing.assert_array_equal(sample["activity_logits"], frozen["activity_logits"][i])
                np.testing.assert_array_equal(sample["dominance_logits"], frozen["dominance_logits"][i])
                np.testing.assert_allclose(sample["activities"], frozen["activities"][i], atol=2e-7)
                np.testing.assert_allclose(sample["dominance"], frozen["dominance"][i], atol=2e-7)
                np.testing.assert_array_equal(sample["labels"], frozen["labels"][i])
        self.assertGreater(sum(samples[0]["activities"]), 2)
        self.assertEqual(samples[3]["dominance"], [0, 0, 0, 0, 0])

    def test_reference_requires_optional_numpy(self):
        with patch.dict("sys.modules", {"numpy": None}):
            code, _, raw = self.request("/api/reference")
        self.assertEqual(code, 503)
        self.assertEqual(json.loads(raw)["error"]["code"], "numpy_unavailable")

    def test_serial_missing_dependency_is_explicit_and_no_device_is_opened(self):
        with patch.object(server, "optional_serial", return_value=(None, None)):
            code, _, raw = self.request("/api/ports")
            self.assertEqual(code, 200)
            value = json.loads(raw)
            self.assertFalse(value["available"])
            self.assertFalse(value["status"]["connected"])
            self.assertIn("pyserial", value["message"])
            code, _, raw = self.post("/api/serial/connect", {"port": "COM5", "baud": 115200})
            self.assertEqual(code, 503)
            self.assertEqual(json.loads(raw)["error"]["code"], "serial_unavailable")
        self.assertFalse(self.state.serial.status()["connected"])

    def test_serial_json_bounds_and_origin(self):
        code, _, _ = self.post("/api/serial/connect", {"port": "COM5"},
                               {"Origin": "https://example.com"})
        self.assertEqual(code, 403)
        for body, expected in (("{}", 415), ("[1]", 400), ("{", 400),
                               ('{"baud":NaN}', 400), (" " * (server.MAX_JSON_BYTES + 1), 413)):
            headers = {"Content-Type": "text/plain" if expected == 415 else "application/json"}
            code, _, _ = self.request("/api/serial/connect", "POST", body, headers)
            self.assertEqual(code, expected)
        for obj in ({"port": "COM5", "baud": True}, {"port": "COM5", "baud": 12345},
                    {"port": "COM5", "extra": 1}, {"baud": 115200}):
            self.assertEqual(self.post("/api/serial/connect", obj)[0], 400)

    def test_serial_disconnect_is_idempotent(self):
        for _ in range(2):
            code, _, raw = self.post("/api/serial/disconnect", {})
            self.assertEqual(code, 200)
            self.assertFalse(json.loads(raw)["connected"])

    def test_telemetry_query_is_bounded(self):
        for query in ("after=-1", "after=no", "limit=0", "limit=257", "after=1&after=2",
                      "after=1&limit=2&other=3", "a=1&b=2&c=3&d=4&e=5"):
            with self.subTest(query=query):
                self.assertEqual(self.request("/api/telemetry?" + query)[0], 400)
        serial = self.state.serial
        for _ in range(server.TELEMETRY_CAPACITY + 3):
            serial._append(b"observed UART line", "test-session")
        code, _, raw = self.request("/api/telemetry?after=0&limit=2")
        value = json.loads(raw)
        self.assertEqual(code, 200)
        self.assertEqual(len(value["events"]), 2)
        self.assertEqual(value["dropped"], 3)
        cursor = value["next_after"]
        follow = json.loads(self.request("/api/telemetry?after=" + str(cursor) + "&limit=1")[2])
        self.assertEqual(follow["events"][0]["id"], cursor + 1)


class ReferenceIntegrityTests(unittest.TestCase):
    def test_changed_asset_with_preserved_size_and_mtime_invalidates_cache(self):
        with tempfile.TemporaryDirectory(prefix="instrec-symphony-model-") as tmp:
            root = Path(tmp)
            model = root / "models" / server.MODEL_ROOT.name
            model.mkdir(parents=True)
            for name in ("manifest.json", "reference_vectors.npz", "train_config.json", "model_source.py"):
                shutil.copy2(server.MODEL_ROOT / name, model / name)
            state = server.AppState(instrec_root=root)
            self.assertEqual(len(state.reference()["samples"]), 5)
            target = model / "reference_vectors.npz"
            original_stat = target.stat()
            data = bytearray(target.read_bytes())
            data[-1] ^= 1
            target.write_bytes(data)
            import os
            os.utime(target, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                state.reference()


class SerialTests(unittest.TestCase):
    def test_optional_driver_opens_only_on_explicit_connect_and_never_writes(self):
        instances = []

        class FakeSerial:
            def __init__(self, **kwargs):
                self.options = kwargs
                self.opened = False
                self.closed = False
                self.buffer = bytearray(b"RTOS BOOT hz=125000000 tick=1000\r\n"
                                        b"RTOS NPU top1=3 last_class=7 last_p=0 c=31152091 seq=1 tick=249\r\n")
                instances.append(self)

            def open(self):
                self.opened = True

            @property
            def in_waiting(self):
                return len(self.buffer)

            def read(self, count):
                chunk = bytes(self.buffer[:count])
                del self.buffer[:count]
                if not chunk:
                    time.sleep(.005)
                return chunk

            def write(self, _):
                raise AssertionError("Read-only serial API attempted a write")

            def close(self):
                self.closed = True

        driver = SimpleNamespace(Serial=FakeSerial)
        ports = SimpleNamespace(comports=lambda: [SimpleNamespace(device="COM_TEST", description="fixture", hwid="fixture")])
        service = server.SerialService()
        with patch.object(server, "optional_serial", return_value=(driver, ports)):
            self.assertTrue(service.inventory()["available"])
            self.assertEqual(instances, [])
            with self.assertRaisesRegex(server.APIError, "当前设备列表"):
                service.connect("COM_UNKNOWN", 115200)
            self.assertEqual(instances, [])
            try:
                status = service.connect("COM_TEST", 115200)
                self.assertTrue(status["connected"])
                deadline = time.monotonic() + 2
                while len(service.tail(0, 10)["events"]) < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                events = service.tail(0, 10)["events"]
                self.assertEqual(len(events), 2)
                self.assertEqual(events[0]["parsed"]["clock_hz"], 125000000)
                result = events[1]["parsed"]
                self.assertEqual((result["top1"], result["last_class"], result["last_pct"]), (3, 7, 0))
                self.assertEqual((result["cycles"], result["tick"]), (31152091, 249))
                self.assertFalse(instances[0].dtr)
                self.assertFalse(instances[0].rts)
                with self.assertRaisesRegex(server.APIError, "先断开"):
                    service.connect("COM_TEST", 115200)
            finally:
                service.disconnect()
        self.assertTrue(instances[0].closed)
        self.assertFalse(service.status()["connected"])

    def test_invalid_or_truncated_uart_is_retained_without_a_classification(self):
        service = server.SerialService()
        for line in (b"NPU top1=8 last_class=7 last_p=50 c=1",
                     b"NPU top1=3 last_class=7 last_p=101 c=1", b"not an NPU result"):
            service._append(line, "fixture")
        self.assertTrue(all(e["parsed"] is None for e in service.tail(0, 10)["events"]))
        service._append(b"NPU top1=3 last_class=7 last_p=50 c=1", "fixture", truncated=True)
        final = service.tail(0, 10)["events"][-1]
        self.assertTrue(final["truncated"])
        self.assertIsNone(final["parsed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
