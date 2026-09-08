"""Unit tests for the serial WS bridge: payload splitting, pacing, RX draining,
and chunked TX streaming. No real platform access (PlatformClient is faked)."""
from __future__ import annotations

import re
import time

import pytest
from fastapi.testclient import TestClient

import fpga_lab_server.app as app_mod
from fpga_lab_server.app import (_split_serial_payload, _tx_pace_s, SERIAL_READ_LEN,
                                 TX_CHUNK_BYTES, create_app)


class FakeSerialClient:
    def __init__(self):
        self.token = "tok"
        self.expires_at = None
        self.user = {}
        self.rx_frames = []      # queued serial_read payloads
        self.sent = []           # list of (data, mode)
        self.read_lengths = []

    def is_authenticated(self):
        return True

    def current_device(self):
        return {"device_id": "123", "device_name": "box123"}

    def serial_open(self, device_id, **kw):
        return {"state": {"config": {"baudRate": kw.get("baud", 115200)}}}

    def serial_read(self, device_id, length=64):
        self.read_lengths.append(length)
        if self.rx_frames:
            return self.rx_frames.pop(0)
        return {"requestedBytes": length, "bytesRead": 0, "hasData": False,
                "data": "", "hex": "", "timestamp": time.time()}

    def serial_send(self, device_id, data, mode="text"):
        self.sent.append((data, mode))
        if mode == "hex":
            n = len(re.sub(r"[^0-9a-fA-F]", "", data)) // 2
        else:
            n = len(data.encode("utf-8"))
        return {"bytesSent": n}

    def serial_close(self, device_id):
        return {}


@pytest.fixture()
def bridge(monkeypatch):
    fake = FakeSerialClient()
    monkeypatch.setattr(app_mod.state, "client", fake)
    monkeypatch.setattr(app_mod.state, "_serial_active", False)
    return fake


def _collect_until(ws, pred, limit=200):
    """Receive frames until pred(state) is truthy; returns accumulated state."""
    for _ in range(limit):
        m = ws.receive_json()
        if pred(m):
            return m
    raise AssertionError("condition not reached within frame limit")


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------
def test_split_hex_aligned_to_bytes():
    chunks = _split_serial_payload("00 11 22 33", "hex", 2)
    assert chunks == [("0011", 2), ("2233", 2)]


def test_split_hex_odd_drops_trailing_nibble():
    chunks = _split_serial_payload("A5B", "hex", 1024)
    assert chunks == [("A5", 1)]


def test_split_text_utf8_byte_count():
    chunks = _split_serial_payload("abc", "text", 2)
    assert [s for s, _ in chunks] == ["ab", "c"]
    assert [n for _, n in chunks] == [2, 1]


def test_tx_pace_matches_baud():
    # 115200 baud, 8N1 -> 10 bits/byte
    assert abs(_tx_pace_s(11520, 115200) - 1.0) < 1e-9
    assert _tx_pace_s(1024, 115200) > 0.08


# ---------------------------------------------------------------------------
# WS bridge via TestClient
# ---------------------------------------------------------------------------
def test_small_tx_still_acks(bridge):
    app = create_app()
    with TestClient(app).websocket_connect("/ws/serial?baud=115200") as ws:
        st = ws.receive_json()
        assert st["type"] == "status" and st["state"] == "connected"
        ws.send_json({"type": "tx", "mode": "hex", "data": "A5"})
        ack = _collect_until(ws, lambda m: m.get("type") == "ack")
        assert ack["bytesSent"] == 1
        assert bridge.sent == [("A5", "hex")]


def test_rx_drain_bursts_no_loss(bridge):
    n = 5
    for i in range(n):
        bridge.rx_frames.append({
            "requestedBytes": SERIAL_READ_LEN, "bytesRead": 4, "hasData": True,
            "data": f"ch{i}", "hex": f"6368{i}", "timestamp": time.time()})
    app = create_app()
    with TestClient(app).websocket_connect("/ws/serial?baud=115200") as ws:
        assert ws.receive_json()["state"] == "connected"
        got = 0
        while got < n:
            m = ws.receive_json()
            if m.get("type") == "rx":
                got += 1
        assert got == n
    assert any(v >= SERIAL_READ_LEN for v in bridge.read_lengths)


def test_large_tx_streams_in_chunks(bridge):
    total = 5000  # bytes
    app = create_app()
    with TestClient(app).websocket_connect("/ws/serial?baud=115200") as ws:
        assert ws.receive_json()["state"] == "connected"
        ws.send_json({"type": "tx", "mode": "hex", "data": "00" * total})

        expected_chunks = -(-total // TX_CHUNK_BYTES)
        progress = 0
        final = None
        while not (progress == expected_chunks and final is not None):
            m = ws.receive_json()
            t = m.get("type")
            if t == "tx_progress":
                progress += 1
            elif t == "ack":
                final = m
        assert final["bytesSent"] == total
        assert final["chunks"] == expected_chunks

    assert len(bridge.sent) == expected_chunks
    byte_lens = [len(re.sub(r"[^0-9a-fA-F]", "", d)) // 2 for d, _ in bridge.sent]
    assert sum(byte_lens) == total
    assert max(byte_lens) <= TX_CHUNK_BYTES


def test_zero_delivery_aborts_with_error(bridge):
    class NoDeliver(FakeSerialClient):
        def serial_send(self, device_id, data, mode="text"):
            self.sent.append((data, mode))
            return {"bytesSent": 0}

    app_mod.state.client = NoDeliver()
    app = create_app()
    with TestClient(app).websocket_connect("/ws/serial?baud=115200") as ws:
        assert ws.receive_json()["state"] == "connected"
        ws.send_json({"type": "tx", "mode": "hex", "data": "00" * 4096})
        err = _collect_until(ws, lambda m: m.get("type") == "error")
        assert "zero bytes delivered" in err["reason"]