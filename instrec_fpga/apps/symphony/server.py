"""Local symphony guide API. Run with Python 3.10+; NumPy loads on demand."""

from __future__ import annotations

import argparse
from collections import deque
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import mimetypes
from pathlib import Path
import re
import socket
import sys
import threading
from urllib.parse import parse_qs, unquote, urlsplit
import uuid


APP_ROOT = Path(__file__).resolve().parent
INSTREC_ROOT = APP_ROOT.parents[1]
MODEL_ROOT = INSTREC_ROOT / "models" / "group5_v3_float_20261102"
MAX_JSON_BYTES = 16_384
MAX_STATIC_BYTES = 8 * 1024 * 1024
MAX_LINE_BYTES = 1024
TELEMETRY_CAPACITY = 2048
BAUD_RATES = (9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600, 1000000)
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    **{x: mimetypes.guess_type("file" + x)[0] for x in
       (".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff", ".woff2")},
}


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    if path.stat().st_size > 2 * 1024 * 1024:
        raise ValueError("Metadata file exceeds size limit")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Metadata must be a JSON object")
    return data


def optional_serial():
    """Import only; enumeration never opens a device."""
    try:
        import serial
        from serial.tools import list_ports
        if not hasattr(serial, "Serial"):
            return None, None
        return serial, list_ports
    except (ImportError, OSError):
        return None, None


def parse_telemetry(line: str) -> dict | None:
    boot = re.fullmatch(r"RTOS BOOT hz=(\d+) tick=(\d+)", line.strip())
    if boot:
        return {"kind": "boot", "clock_hz": int(boot[1]), "tick_hz": int(boot[2])}
    match = re.fullmatch(
        r"(?P<rtos>RTOS )?NPU top1=(?P<top1>\d+) last_class=(?P<last_class>\d+)"
        r" last_p=(?P<last_pct>\d+) c=(?P<cycles>\d+)"
        r"(?: seq=(?P<sequence>\d+) tick=(?P<tick>\d+))?", line.strip())
    if not match:
        return None
    values = {k: int(v) for k, v in match.groupdict().items()
              if k != "rtos" and v is not None}
    if (values["top1"] > 7 or values["last_class"] > 7
            or values["last_pct"] > 100 or any(v > 0xFFFFFFFF for v in values.values())):
        return None
    return {"kind": "npu", "firmware": "rtos" if match["rtos"] else "baseline", **values}


class SerialService:
    """A bounded, read-only serial tail, started exclusively by connect()."""

    def __init__(self):
        self._lock = threading.RLock()
        self._operation_lock = threading.Lock()
        self._events = deque(maxlen=TELEMETRY_CAPACITY)
        self._next_id = 1
        self._serial = None
        self._thread = None
        self._stop = threading.Event()
        self._status = {"connected": False, "port": None, "baud": None,
                        "session_id": None, "error": None, "read_only": True}

    def status(self) -> dict:
        with self._lock:
            return dict(self._status)

    def inventory(self) -> dict:
        module, list_ports = optional_serial()
        if module is None:
            return {"available": False, "ports": [], "status": self.status(),
                    "message": "串口读取需要可选依赖 pyserial：python -m pip install pyserial"}
        try:
            ports = [{"device": str(p.device)[:256], "description": str(p.description)[:256],
                      "hwid": str(p.hwid)[:256]}
                     for p in list(list_ports.comports())[:128]]
        except Exception as exc:
            return {"available": False, "ports": [], "status": self.status(),
                    "message": "串口枚举失败：" + str(exc)[:300]}
        return {"available": True, "ports": ports, "status": self.status(),
                "message": "仅列出设备；点击连接后开始只读接收。"}

    def connect(self, port: str, baud: int) -> dict:
        with self._operation_lock:
            return self._connect(port, baud)

    def _connect(self, port: str, baud: int) -> dict:
        if (not isinstance(port, str) or not port or len(port) > 256
                or any(ord(c) < 32 for c in port)):
            raise APIError(400, "invalid_port", "请选择列表中的串口。")
        if type(baud) is not int or baud not in BAUD_RATES:
            raise APIError(400, "invalid_baud", "波特率不在支持列表中。")
        inventory = self.inventory()
        if not inventory["available"]:
            raise APIError(503, "serial_unavailable", inventory["message"])
        if port not in {p["device"] for p in inventory["ports"]}:
            raise APIError(400, "unknown_port", "该串口未出现在当前设备列表中。")
        module, _ = optional_serial()
        with self._lock:
            if self._status["connected"]:
                raise APIError(409, "already_connected", "请先断开当前串口。")
            try:
                stream = module.Serial(port=None, baudrate=baud, timeout=0.2,
                                       write_timeout=0.2, xonxoff=False,
                                       rtscts=False, dsrdtr=False)
                # Configure control lines before opening; this application writes no bytes.
                stream.dtr = False
                stream.rts = False
                stream.port = port
                stream.open()
            except Exception as exc:
                if "stream" in locals():
                    try:
                        stream.close()
                    except Exception:
                        pass
                raise APIError(409, "serial_open_failed", "串口打开失败：" + str(exc)[:300]) from exc
            self._stop = threading.Event()
            self._serial = stream
            session_id = uuid.uuid4().hex
            self._status.update(connected=True, port=port, baud=baud,
                                session_id=session_id, error=None)
            self._thread = threading.Thread(target=self._read, args=(stream, self._stop, session_id),
                                            daemon=True, name="symphony-serial-reader")
            self._thread.start()
            return self.status()

    def _append(self, raw: bytes, session_id: str, truncated: bool = False):
        line = raw[:MAX_LINE_BYTES].decode("utf-8", errors="replace").strip("\r\n")
        if not line:
            return
        truncated = truncated or len(raw) > MAX_LINE_BYTES
        with self._lock:
            self._events.append({"id": self._next_id,
                                 "received_at": datetime.now(timezone.utc).isoformat(),
                                 "session_id": session_id, "line": line,
                                 "truncated": truncated,
                                 "parsed": None if truncated else parse_telemetry(line)})
            self._next_id += 1

    def _read(self, stream, stop: threading.Event, session_id: str):
        pending = bytearray()
        discarding = False
        try:
            while not stop.is_set():
                piece = stream.read(min(512, max(1, stream.in_waiting)))
                if not piece:
                    continue
                for value in piece:
                    if value == 10:
                        if not discarding:
                            self._append(bytes(pending), session_id)
                        pending.clear()
                        discarding = False
                    elif not discarding:
                        pending.append(value)
                        if len(pending) > MAX_LINE_BYTES:
                            self._append(bytes(pending), session_id, truncated=True)
                            pending.clear()
                            discarding = True
            if pending and not discarding:
                self._append(bytes(pending), session_id)
        except Exception as exc:
            if not stop.is_set():
                with self._lock:
                    if self._status["session_id"] == session_id:
                        self._status["error"] = str(exc)[:300]
        finally:
            try:
                stream.close()
            except Exception:
                pass
            with self._lock:
                if self._status["session_id"] == session_id:
                    self._status["connected"] = False

    def disconnect(self) -> dict:
        with self._operation_lock:
            return self._disconnect()

    def _disconnect(self) -> dict:
        with self._lock:
            self._stop.set()
            stream, thread = self._serial, self._thread
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=1)
        with self._lock:
            self._status["connected"] = False
            self._serial = None
            self._thread = None
            return self.status()

    def tail(self, after: int, limit: int) -> dict:
        with self._lock:
            oldest = self._events[0]["id"] if self._events else self._next_id
            events = [dict(e) for e in self._events if e["id"] > after][:limit]
            return {"events": events, "next_after": events[-1]["id"] if events else after,
                    "oldest_id": oldest, "dropped": max(0, oldest - after - 1),
                    "capacity": TELEMETRY_CAPACITY, "status": self.status()}


class AppState:
    def __init__(self, app_root: Path = APP_ROOT, instrec_root: Path = INSTREC_ROOT):
        self.app_root = app_root.resolve()
        self.instrec_root = instrec_root.resolve()
        self.model_root = self.instrec_root / "models" / MODEL_ROOT.name
        self.serial = SerialService()
        self._reference_lock = threading.Lock()
        self._reference_cache = None
        self._reference_key = None

    def project(self) -> dict:
        contract = read_json(self.instrec_root / "scripts" / "outputs" / "layer_contract.json")
        classes = contract["classes"]
        if classes["num_classes"] != 8 or len(classes["names"]) != 8:
            raise ValueError("Eight-class deployment contract does not match")
        manifest = read_json(self.model_root / "manifest.json")
        config = read_json(self.model_root / "train_config.json")
        release_path = self.instrec_root / "releases" / "rtos125-20261114-175148" / "RELEASE.json"
        release = read_json(release_path) if release_path.is_file() else {}
        numpy_available = importlib.util.find_spec("numpy") is not None
        return {
            "schema_version": 1,
            "project": {"name": "交响导聆与片段标注", "id": "instrec-symphony",
                        "mode": "local", "serial_connected": self.serial.status()["connected"]},
            "live": {"class_order": classes["names"], "class_order_zh": classes["names_zh"],
                     "system_clock_hz": release.get("clock_hz", 125_000_000),
                     "tick_hz": release.get("tick_hz", 1000),
                     "kernel": release.get("kernel", "FreeRTOS"), "baud": 115200,
                     "model": "8-class INT8 NPU", "activity_available": False,
                     "full_probabilities_available": False, "transport": "read-only UART text",
                     "source": "scripts/outputs/layer_contract.json",
                     "release": "releases/rtos125-20261114-175148/RELEASE.json",
                     "board_test_executed": release.get("board_test_executed", False)},
            "reference": {"available": numpy_available,
                          "model": MODEL_ROOT.name, "group_order": manifest["group_order"],
                          "group_order_zh": config["group_names_zh"],
                          "sample_count": len(manifest["validation_rows"]),
                          "sample_rate_hz": manifest["sample_rate_hz"],
                          "segment_seconds": manifest["segment_samples"] / manifest["sample_rate_hz"],
                          "fpga_deployed": manifest["fpga_deployed"],
                          "continuous": False, "audio_available": False},
            "capabilities": {"reference_vectors": numpy_available, "local_audio": "browser",
                             "segment_annotations": "browser", "uart_file_import": "browser",
                             "serial": optional_serial()[0] is not None,
                             "serial_write": False, "audio_inference": False,
                             "automatic_audio_uart_alignment": False},
        }

    def reference(self) -> dict:
        try:
            import numpy as np
        except ImportError as exc:
            raise APIError(503, "numpy_unavailable", "参考向量读取需要 NumPy：python -m pip install numpy") from exc
        paths = [self.model_root / n for n in
                 ("manifest.json", "reference_vectors.npz", "train_config.json", "model_source.py")]
        if any(p.stat().st_size > 16 * 1024 * 1024 for p in paths):
            raise ValueError("Reference asset exceeds size limit")
        key = tuple(digest(p) for p in paths)
        with self._reference_lock:
            if key == self._reference_key:
                return self._reference_cache
            manifest, config = read_json(paths[0]), read_json(paths[2])
            for path in paths[1:]:
                if path.stat().st_size > 16 * 1024 * 1024:
                    raise ValueError("Reference asset exceeds size limit")
                if digest(path) != manifest["assets"][path.name]:
                    raise ValueError("Frozen reference asset hash mismatch: " + path.name)
            names = manifest["group_order"]
            if names != ["strings", "woodwinds", "brass", "percussion", "keys"] or config["group_names"] != names:
                raise ValueError("Five-group model order does not match")
            with np.load(paths[1], allow_pickle=False) as data:
                rows = data["row_indices"].astype(int).tolist()
                act = np.asarray(data["activity_logits"], dtype=np.float64)
                dom = np.asarray(data["dominance_logits"], dtype=np.float64)
                labels = np.asarray(data["labels"], dtype=np.float64)
                count = len(rows)
                if (not 1 <= count <= 128 or rows != manifest["validation_rows"]
                        or any(a.shape != (count, 5) for a in (act, dom, labels))
                        or data["features"].shape != (count, 1, 64, 130)
                        or not all(np.isfinite(a).all() for a in (act, dom, labels))
                        or not np.isin(labels, [0, 1]).all()):
                    raise ValueError("Reference dimensions or values do not match frozen contract")
                activities = np.empty_like(act)
                positive = act >= 0
                activities[positive] = 1 / (1 + np.exp(-act[positive]))
                exp_negative = np.exp(act[~positive])
                activities[~positive] = exp_negative / (1 + exp_negative)
                softmax = np.exp(dom - dom.max(axis=1, keepdims=True))
                softmax /= softmax.sum(axis=1, keepdims=True)
                masked = softmax * (activities > 0.5)
                totals = masked.sum(axis=1, keepdims=True)
                dominance = np.divide(masked, totals, out=np.zeros_like(masked), where=totals > 0)
                if not (np.allclose(activities, data["activities"], rtol=2e-6, atol=2e-7)
                        and np.allclose(dominance, data["dominance"], rtol=2e-6, atol=2e-7)):
                    raise ValueError("Activation reconstruction disagrees with frozen model output")
            seconds = manifest["segment_samples"] / manifest["sample_rate_hz"]
            result = {
                "schema_version": 1,
                "source": {"model": MODEL_ROOT.name,
                           "path": "models/" + MODEL_ROOT.name + "/reference_vectors.npz",
                           "sha256": digest(paths[1]), "manifest_sha256": digest(paths[0]),
                           "model_source_sha256": digest(paths[3]),
                           "train_config_sha256": digest(paths[2]),
                           "checkpoint_epoch": manifest["checkpoint_epoch"],
                           "fpga_deployed": manifest["fpga_deployed"], "kind": "frozen_float_reference"},
                "group_order": names, "group_order_zh": config["group_names_zh"],
                "sample_rate_hz": manifest["sample_rate_hz"], "segment_seconds": seconds,
                "continuous": False, "audio_available": False,
                "activity_activation": manifest["activity_activation"],
                "dominance_activation": manifest["dominance_activation"],
                "samples": [{"id": "group5-row-" + str(row), "name": "参考样本 · " + str(row),
                             "row_index": row, "duration_seconds": seconds,
                             "start_seconds": 0, "end_seconds": seconds,
                             "activity_logits": act[i].tolist(), "dominance_logits": dom[i].tolist(),
                             "activities": activities[i].tolist(), "dominance": dominance[i].tolist(),
                             "labels": labels[i].tolist(),
                             "active_groups": [names[g] for g in range(5) if activities[i, g] > .5]}
                            for i, row in enumerate(rows)],
            }
            self._reference_key, self._reference_cache = key, result
            return result


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16

    def __init__(self, port: int, state: AppState):
        self.state = state
        self._slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", port), Handler)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            try:
                request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nConnection: close\r\nContent-Length: 0\r\n\r\n")
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def server_close(self):
        self.state.serial.disconnect()
        super().server_close()


class Handler(BaseHTTPRequestHandler):
    server_version = "InstRecSymphony/1"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, fmt, *args):
        # BaseHTTPRequestHandler escapes control characters before reaching this hook.
        super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; "
                         "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                         "media-src 'self' blob:; connect-src 'self'; worker-src 'self' blob:; "
                         "object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.close_connection = True
        super().end_headers()

    def _json(self, status: int, data: dict):
        body = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _context(self):
        port = self.server.server_port
        hosts = {"127.0.0.1:" + str(port), "localhost:" + str(port)}
        if port == 80:
            hosts |= {"127.0.0.1", "localhost"}
        if self.headers.get("Host", "").lower() not in hosts:
            raise APIError(403, "invalid_host", "请通过本机回环地址访问应用。")
        if len(self.path) > 4096:
            raise APIError(414, "path_too_long", "请求路径超出长度上限。")
        parsed = urlsplit(self.path)
        if parsed.scheme or parsed.netloc:
            raise APIError(400, "invalid_target", "请求路径格式错误。")
        try:
            path = unquote(parsed.path, errors="strict")
        except UnicodeError as exc:
            raise APIError(400, "invalid_path", "请求路径 UTF-8 编码错误。") from exc
        if "\x00" in path or "\\" in path:
            raise APIError(400, "invalid_path", "请求路径格式错误。")
        return path, parsed.query

    def _body(self) -> dict:
        port = self.server.server_port
        if self.headers.get("Origin") not in (None, "http://127.0.0.1:" + str(port),
                                               "http://localhost:" + str(port)):
            raise APIError(403, "invalid_origin", "串口控制请求需要来自本地应用页面。")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise APIError(403, "invalid_origin", "串口控制请求需要来自本地应用页面。")
        if self.headers.get("Transfer-Encoding"):
            raise APIError(400, "unsupported_encoding", "请提交带 Content-Length 的 JSON。")
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"\d{1,8}", lengths[0]):
            raise APIError(411, "length_required", "JSON 请求需要单一 Content-Length。")
        length = int(lengths[0])
        if length > MAX_JSON_BYTES:
            raise APIError(413, "body_too_large", "JSON 请求超过 16 KiB 上限。")
        if self.headers.get_content_type() != "application/json":
            raise APIError(415, "json_required", "请提交 application/json。")
        raw = self.rfile.read(length)
        if len(raw) != length:
            raise APIError(400, "incomplete_body", "JSON 请求未完整接收。")
        try:
            def reject_constant(value):
                raise ValueError("JSON constant is not finite: " + value)
            obj = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
        except (ValueError, UnicodeError) as exc:
            raise APIError(400, "invalid_json", "JSON 格式或 UTF-8 编码错误。") from exc
        if not isinstance(obj, dict):
            raise APIError(400, "object_required", "请求体需要 JSON 对象。")
        return obj

    def _static(self, path: str):
        root = self.server.state.app_root
        relative = "index.html" if path == "/" else path.lstrip("/")
        if any(p.startswith(".") for p in relative.split("/")):
            raise APIError(403, "invalid_path", "该路径未开放。")
        file = (root / relative).resolve()
        if not file.is_relative_to(root) or not file.is_file() or file.suffix.lower() not in STATIC_TYPES:
            raise APIError(404, "not_found", "页面资源不存在。")
        size = file.stat().st_size
        if size > MAX_STATIC_BYTES:
            raise APIError(413, "file_too_large", "页面资源超过大小上限。")
        self.send_response(200)
        self.send_header("Content-Type", STATIC_TYPES[file.suffix.lower()] or "application/octet-stream")
        self.send_header("Content-Length", str(size))
        self.end_headers()
        if self.command != "HEAD":
            with file.open("rb") as source:
                while chunk := source.read(65_536):
                    self.wfile.write(chunk)

    def _dispatch(self):
        try:
            path, query = self._context()
            state = self.server.state
            if self.command in ("GET", "HEAD"):
                if path == "/api/project":
                    self._json(200, state.project())
                elif path == "/api/reference":
                    self._json(200, state.reference())
                elif path == "/api/ports":
                    self._json(200, state.serial.inventory())
                elif path == "/api/telemetry":
                    args = parse_qs(query, keep_blank_values=True, max_num_fields=4)
                    if (set(args) - {"after", "limit"} or any(len(v) != 1 for v in args.values())
                            or any(not re.fullmatch(r"\d{1,16}", v[0]) for v in args.values())):
                        raise APIError(400, "invalid_cursor", "遥测游标格式错误。")
                    after, limit = int(args.get("after", ["0"])[0]), int(args.get("limit", ["128"])[0])
                    if not 1 <= limit <= 256:
                        raise APIError(400, "invalid_limit", "每次读取数量需要在 1 到 256 之间。")
                    self._json(200, state.serial.tail(after, limit))
                elif path.startswith("/api/"):
                    raise APIError(404, "not_found", "接口不存在。")
                else:
                    self._static(path)
            elif self.command == "POST":
                body = self._body()
                if path == "/api/serial/connect":
                    if set(body) - {"port", "baud"}:
                        raise APIError(400, "unknown_field", "连接请求包含未知字段。")
                    self._json(200, state.serial.connect(body.get("port"), body.get("baud", 115200)))
                elif path == "/api/serial/disconnect":
                    if body:
                        raise APIError(400, "unknown_field", "断开请求需要空 JSON 对象。")
                    self._json(200, state.serial.disconnect())
                else:
                    raise APIError(404, "not_found", "接口不存在。")
        except APIError as exc:
            self._json(exc.status, {"error": {"code": exc.code, "message": exc.message}})
        except (UnicodeError, ValueError) as exc:
            if locals().get("path") == "/api/telemetry":
                self._json(400, {"error": {"code": "invalid_query", "message": "查询参数格式错误。"}})
            else:
                self.log_error("Data validation failed: %s", exc)
                self._json(503, {"error": {"code": "data_unavailable", "message": "数据校验失败，请查看服务器日志。"}})
        except (BrokenPipeError, ConnectionResetError, socket.timeout):
            pass
        except Exception as exc:
            self.log_error("API failed: %s", exc)
            self._json(503, {"error": {"code": "data_unavailable", "message": "本地数据读取失败，请查看服务器日志。"}})

    do_GET = _dispatch
    do_HEAD = _dispatch
    do_POST = _dispatch


def serve(port: int) -> int:
    try:
        server = LocalHTTPServer(port, AppState())
    except OSError as exc:
        print("Local server bind failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"event": "server_ready", "url": "http://127.0.0.1:" + str(server.server_port),
                      "serial_opened": False}, ensure_ascii=False), flush=True)
    try:
        server.serve_forever(poll_interval=.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--log-prefix", type=Path,
                        help="Create PREFIX.stdout.log and PREFIX.stderr.log as UTF-8 BOM files")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    with ExitStack() as logs:
        if args.log_prefix:
            prefix = args.log_prefix.resolve()
            try:
                stdout = logs.enter_context(prefix.with_name(prefix.name + ".stdout.log").open(
                    "x", encoding="utf-8-sig", buffering=1))
                stderr = logs.enter_context(prefix.with_name(prefix.name + ".stderr.log").open(
                    "x", encoding="utf-8-sig", buffering=1))
            except OSError as exc:
                print("Log creation failed: " + str(exc), file=sys.stderr)
                return 2
            logs.enter_context(redirect_stdout(stdout))
            logs.enter_context(redirect_stderr(stderr))
        return serve(args.port)


if __name__ == "__main__":
    raise SystemExit(main())
