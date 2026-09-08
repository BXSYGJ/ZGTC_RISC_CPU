"""FastAPI app for the fpga_lab bridge.

Exposes stable REST + WS over the platform's auto-assign model: the account holds ONE
current device at a time (request-by-type auto-assigns a with_camera PG2L200H box).
Routes mirror that: reserve (by type), current, release, burn bitstream, serial WS bridge.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import re
import time
import threading
from pathlib import Path

from fastapi import (FastAPI, HTTPException, UploadFile, File, WebSocket,
                     WebSocketDisconnect)
from pydantic import BaseModel

from fpga_lab_server.paths import ACCOUNT_FILE, BASE
from fpga_lab_server.platform import PlatformClient, PlatformError

APP_VERSION = "0.2.0"

# --- serial bridge tuning (2026-09-07: RX loss + TX truncation fixes) ---
SERIAL_READ_LEN = 512       # platform cap: serial read length must be 1..512 bytes
                            # (4096 made every read raise -> no RX at all);
                            # 64 B/0.7 s lost ~99% of 115200 RX
SERIAL_IDLE_POLL_S = 0.10   # poll interval only while the RX buffer is empty (idle)
SERIAL_ERR_BACKOFF_S = 0.2  # backoff when a serial read raises (keeps drain loop alive)
TX_CHUNK_BYTES = 1024       # stream send in ~1 KiB chunks (platform drops >~16 KiB posts)

DIAG_MIN_GAP_S = 1.0        # throttle diagnostic frames from an all-zero/bad box


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------
class LabState:
    def __init__(self, account_file: Path = ACCOUNT_FILE):
        self.account_file = account_file
        self.client = PlatformClient()
        self._lock = threading.Lock()          # httpx sync client is not thread-safe
        self._serial_active = False

    def ensure_auth(self):
        with self._lock:
            if not self.client.is_authenticated():
                self.client.relogin_from_account(self.account_file)

    def current(self) -> dict | None:
        self.ensure_auth()
        with self._lock:
            return self.client.current_device()

    def reserve(self, minutes: int) -> dict:
        self.ensure_auth()
        with self._lock:
            try:
                self.client.release_current()
            except Exception:
                pass
            return self.client.reserve(minutes=minutes, card_type="with_camera")

    def release(self) -> dict:
        self.ensure_auth()
        with self._lock:
            prev = self.client.current_device()
            self.client.release_current()
            return {"released": True, "previous_device": (prev or {}).get("device_name")}

    def devices(self) -> list[dict]:
        self.ensure_auth()
        with self._lock:
            return self.client.device_catalog()

    def burn(self, filename: str, data: bytes) -> dict:
        self.ensure_auth()
        cur = self.current()
        if not cur:
            raise PlatformError("no device reserved; POST /api/v1/devices/reserve first", 409)
        did = cur["device_id"]
        sha = hashlib.sha256(data).hexdigest().upper()
        tmp = Path(__file__).resolve().parents[1] / "sessions" / ("upload_" + filename)
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        try:
            with self._lock:
                prog = self.client.burn_and_wait(did, tmp)
            return {
                "box_id": did, "device_name": cur.get("device_name"),
                "file_name": filename, "sha256": sha, "uploaded_at": time.time(),
                "programming": "success",
                "detail": "firmware download complete, device awake",
                "progress": prog, "raw": cur,
            }
        finally:
            tmp.unlink(missing_ok=True)

    def serial_open_for_current(self, **kw) -> tuple[int, dict]:
        cur = self.current()
        if not cur:
            raise PlatformError("no device reserved", 409)
        did = cur["device_id"]
        with self._lock:
            st = self.client.serial_open(did, **kw)
        return did, st


state = LabState()


def _err(e: Exception) -> HTTPException:
    if isinstance(e, PlatformError):
        code = {401: 401, 409: 409}.get(e.status, 502)
        return HTTPException(code, str(e))
    return HTTPException(500, str(e))


def _norm_devices(ds: list[dict]) -> list[dict]:
    return [{
        "id": d.get("id"), "name": d.get("name"), "device": d.get("board_model"),
        "device_number": d.get("device_number"),
        "status": "free" if d.get("status") == "online" else d.get("status", "unknown"),
        "hardware_profile": d.get("hardware_profile"),
        "capabilities": (d.get("device_capabilities") or {}),
        "raw": d,
    } for d in ds]


# ---------------------------------------------------------------------------
# REST models / routes
# ---------------------------------------------------------------------------
class ReserveIn(BaseModel):
    minutes: int = 10


def _rest_routes(app: FastAPI):
    @app.get("/api/v1/health")
    def health():
        try:
            state.ensure_auth()
            auth = state.client.is_authenticated()
        except Exception:
            auth = False
        return {"status": "ok", "api": "fpga-lab-bridge", "version": APP_VERSION,
                "session": {"authenticated": auth,
                            "expires_at": state.client.expires_at,
                            "mode": (state.client.user or {}).get("role")},
                "uptime_s": round(time.time() - app.state.boot_ts, 1)}

    @app.get("/api/v1/devices")
    def devices():
        try:
            return {"boxes": _norm_devices(state.devices()), "fetched_at": time.time()}
        except Exception as e:
            raise _err(e)

    @app.get("/api/v1/current")
    def current():
        try:
            cur = state.current()
            if not cur:
                return {"current": None}
            return {"current": {k: cur.get(k) for k in (
                "device_id", "device_number", "device_name", "name", "board_model",
                "status", "duration_minutes", "planned_end_time", "start_time",
                "session_id")}, "raw": cur}
        except Exception as e:
            raise _err(e)

    @app.post("/api/v1/devices/reserve")
    def reserve(body: ReserveIn):
        try:
            minutes = max(5, min(int(body.minutes), 60))
            d = state.reserve(minutes)
            return {"status": "reserved", "box_id": d.get("deviceId"),
                    "device_name": d.get("deviceName"),
                    "reserved_until": d.get("plannedEndTime"),
                    "duration": d.get("duration"), "session_id": d.get("sessionId"),
                    "ttl_seconds": minutes * 60, "raw": d}
        except Exception as e:
            raise _err(e)

    @app.post("/api/v1/devices/release")
    def release():
        try:
            return state.release()
        except Exception as e:
            raise _err(e)

    @app.post("/api/v1/bitstream")
    async def bitstream(file: UploadFile = File(...)):
        try:
            data = await file.read()
            if not data:
                raise PlatformError("empty upload", 400)
            return state.burn(file.filename or "upload.sbit", data)
        except Exception as e:
            raise _err(e)


# ---------------------------------------------------------------------------
# Serial WS bridge
# ---------------------------------------------------------------------------
def _split_serial_payload(data: str, mode: str, max_bytes: int):
    """Split a serial payload into byte-aligned chunks.

    Returns a list of ``(chunk_string, byte_count)``. ``hex`` mode strips
    whitespace and splits on even hex-digit boundaries; ``text`` splits on
    character boundaries (byte count measured after UTF-8 encoding).
    """
    if mode == "hex":
        hx = re.sub(r"[^0-9a-fA-F]", "", data)
        if len(hx) % 2:
            hx = hx[:-1]
        step = max_bytes * 2
        return [(hx[i:i + step], len(hx[i:i + step]) // 2)
                for i in range(0, len(hx), step)]
    out = []
    for i in range(0, len(data), max_bytes):
        s = data[i:i + max_bytes]
        out.append((s, len(s.encode("utf-8"))))
    return out


def _tx_pace_s(nbytes: int, baud: int) -> float:
    """Minimum on-the-wire time for nbytes at 8N1 (10 bits/byte)."""
    return nbytes * 10.0 / max(baud, 1)


def _wire_serial_ws(app: FastAPI):
    @app.websocket("/ws/serial")
    async def serial_ws(ws: WebSocket, baud: int = 115200, data_bits: int = 8,
                        stop_bits: int = 1, parity: str = "none", flow: int = 0):
        await ws.accept()
        if state._serial_active:
            await ws.send_json({"type": "status", "state": "error",
                                "reason": "a serial session is already active"})
            await ws.close(code=1008)
            return
        try:
            did, st = state.serial_open_for_current(
                baud=baud, data_bits=data_bits, stop_bits=stop_bits,
                parity=parity, flow_control=flow)
        except Exception as e:
            await ws.send_json({"type": "status", "state": "error",
                                "reason": f"open failed: {e}"})
            await ws.close(code=1008)
            return

        state._serial_active = True

        # --- sync bridge helpers (httpx client is not async/thread-safe) ---
        def read_once():
            with state._lock:
                return state.client.serial_read(did, length=SERIAL_READ_LEN)

        def send_once(chunk: str, mode: str):
            with state._lock:
                return state.client.serial_send(did, chunk, mode=mode)

        rx_q: asyncio.Queue = asyncio.Queue()
        tx_q: asyncio.Queue = asyncio.Queue()
        send_lock = asyncio.Lock()
        tasks: list[asyncio.Task] = []

        async def safe_send(obj: dict):
            async with send_lock:
                await ws.send_json(obj)

        # RX: drain as fast as data appears (burst), idle-poll only when empty.
        # This replaces the old 64 B / 0.7 s loop that dropped ~99% of 115200 RX.
        async def rx_drain():
            last_diag = 0.0
            while True:
                try:
                    rd = await asyncio.to_thread(read_once)
                except Exception:
                    await asyncio.sleep(SERIAL_ERR_BACKOFF_S)
                    continue
                if rd.get("bytesRead") or rd.get("hasData"):
                    if rd.get("data") or rd.get("hex"):
                        await rx_q.put({"type": "rx", "rd": rd})
                    continue  # burst: drain immediately, do not idle this cycle
                if rd.get("allZeroPayload") and rd.get("diagnostic"):
                    now = time.monotonic()
                    if now - last_diag >= DIAG_MIN_GAP_S:
                        last_diag = now
                        await rx_q.put({"type": "diag", "message": rd.get("diagnostic")})
                await asyncio.sleep(SERIAL_IDLE_POLL_S)

        async def rx_forwarder():
            while True:
                m = await rx_q.get()
                if m.get("type") == "diag":
                    await safe_send({"type": "diagnostic", "message": m.get("message")})
                    continue
                rd = m["rd"]
                text = rd.get("data", "")
                await safe_send({
                    "type": "rx", "ts": rd.get("timestamp"),
                    "data_b64": base64.b64encode(text.encode("utf-8")).decode(),
                    "data_text": text, "hex": rd.get("hex"),
                    "bytesRead": rd.get("bytesRead")})

        # TX: stream large payloads in ~1 KiB chunks paced to the baud rate,
        # verifying each chunk's bytesSent. Small payloads still ack as before.
        async def tx_sender():
            while True:
                msg = await tx_q.get()
                mode = msg.get("mode", "text")
                data = msg.get("data", "")
                chunks = _split_serial_payload(data, mode, TX_CHUNK_BYTES)
                if not chunks:
                    await safe_send({"type": "ack", "bytesSent": 0, "chunks": 0})
                    continue
                total = 0
                t0 = time.time()
                ok = True
                for idx, (chunk, nb) in enumerate(chunks):
                    try:
                        out = await asyncio.to_thread(send_once, chunk, mode)
                    except Exception as e:
                        await safe_send({"type": "error",
                                         "reason": f"send chunk {idx + 1}/{len(chunks)} failed: {e}"})
                        ok = False
                        break
                    sent = out.get("bytesSent") or 0
                    total += sent
                    if len(chunks) > 1:
                        await safe_send({
                            "type": "tx_progress", "index": idx + 1, "total": len(chunks),
                            "bytesSent": sent, "totalSent": total})
                    if sent == 0 and nb > 0:
                        await safe_send({
                            "type": "error",
                            "reason": f"zero bytes delivered at chunk {idx + 1}/{len(chunks)}; aborting"})
                        ok = False
                        break
                    if idx < len(chunks) - 1:
                        await asyncio.sleep(_tx_pace_s(nb, baud))
                if ok:
                    await safe_send({"type": "ack", "bytesSent": total,
                                     "chunks": len(chunks),
                                     "elapsed_s": round(time.time() - t0, 3)})

        try:
            await ws.send_json({"type": "status", "state": "connected", "box_id": did,
                                "config": (st.get("state") or {}).get("config")})
            tasks.append(asyncio.create_task(rx_drain()))
            tasks.append(asyncio.create_task(rx_forwarder()))
            tasks.append(asyncio.create_task(tx_sender()))

            while True:
                msg = await ws.receive_json()
                t = msg.get("type")
                if t == "tx":
                    await tx_q.put(msg)
                elif t == "close":
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            try:
                await ws.send_json({"type": "status", "state": "error", "reason": str(e)})
            except Exception:
                pass
        finally:
            for tk in tasks:
                tk.cancel()
            try:
                with state._lock:
                    state.client.serial_close(did)
            except Exception:
                pass
            state._serial_active = False
            try:
                await ws.close()
            except Exception:
                pass


def create_app() -> FastAPI:
    app = FastAPI(title="fpga-lab-bridge", version=APP_VERSION)
    app.state.boot_ts = time.time()
    _rest_routes(app)
    _wire_serial_ws(app)
    return app


def main():
    import uvicorn
    cfg = {"host": "127.0.0.1", "port": 8600}
    cf = BASE / "config.local.yaml"
    if cf.exists():
        try:
            import yaml
            data = yaml.safe_load(cf.read_text(encoding="utf-8")) or {}
            cfg.update(data.get("server", {}))
        except Exception:
            pass
    uvicorn.run(create_app(), host=cfg["host"], port=int(cfg["port"]), log_level="info")


if __name__ == "__main__":
    main()
