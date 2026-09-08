"""Offline checks for stream_load.py helpers (no platform access)."""
import stream_load as sl


def test_build_upload_payload_shape():
    app = bytes(range(256)) * 2 + b"X" * 100  # 612 bytes
    p = sl.build_upload_payload(app)
    assert len(p) == 1 + 4 + len(app)
    assert p[0:1] == b"R"
    assert p[1:5] == len(app).to_bytes(4, "little")
    assert p[5:] == app


def test_expected_acks_matches_measured_anchors():
    # 实测锚点（用户探针）：33380B -> 131；10936B -> 43
    assert sl.expected_acks(33380) == 131
    assert sl.expected_acks(10936) == 43
    assert sl.expected_acks(256) == 2       # 1 满块 K + 1 结束 K
    assert sl.expected_acks(255) == 1       # 0 满块 + 1 结束 K


def test_count_acks_over_hex():
    assert sl.count_acks("4B4B4B") == 3
    assert sl.count_acks("4b") == 1
    assert sl.count_acks("00") == 0


def test_classify_markers():
    assert sl.classify("RUN ... OK") == "PASS"
    assert sl.classify("HELLO RV32 FROM 0x1000") == "PASS"
    assert sl.classify("ERR rx") == "RX_ERR"
    assert sl.classify("check FAIL") == "CHECKSUM_FAIL"
    assert sl.classify("nothing") == "NO_MARKER"