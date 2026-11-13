import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

FILE=Path(__file__).resolve().parents[1]/"remote_capture.py"
SPEC=importlib.util.spec_from_file_location("remote_capture",FILE)
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

def run_text(sequence=0, crc="0359210D", expected="0359210D", errors="00000000"):
    return (f"PACERV_SHARED BEGIN seq={sequence:08X} RV32IMC 125MHz physical-DDR3\r\n"
            f"ISA=RV32IMC MASK=SB_SH CRC={crc} EXPECT={expected} ERR={errors}\r\n"
            "PACERV_SHARED PASS\r\n").encode("ascii")

class FakeClient:
    def __init__(self,fail="",existing=False):
        self.events=[]; self.fail=fail; self.held=existing
        raw=run_text(7)+run_text(8)
        self.payloads=[{"hex":raw[:81].hex(),"data":"ignored"},
                       {"hex":raw[81:187].hex()}, {"hex":raw[187:].hex()}]
    def current_device(self):
        return {"device_id":61,"device_name":"test","board_model":"PG2L200H"} if self.held else None
    def reserve(self,**kw):
        self.events.append("reserve"); self.held=True
        if self.fail=="reserve": raise TimeoutError()
        return {"device_id":61}
    def burn_and_wait(self,*args):
        self.events.append("burn")
        if self.fail=="burn": raise RuntimeError()
    def serial_open(self,*args,**kw): self.events.append("open")
    def serial_send(self,*args,**kw): self.events.append("send")
    def serial_read(self,*args,**kw):
        self.events.append("read")
        if self.fail=="read": raise RuntimeError()
        return self.payloads.pop(0) if self.payloads else {}
    def serial_close(self,*args):
        self.events.append("close")
        if self.fail=="close": raise RuntimeError()
    def release(self,*args): self.events.append("release"); self.held=False

class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name); self.sbit=self.root/"test.sbit"
        self.sbit.write_bytes(b"fixture")
    def tearDown(self): self.temp.cleanup()
    def test_hex_is_authoritative_and_pass_can_span_packets(self):
        client=FakeClient()
        result=MODULE.capture(client,self.sbit,self.root/"out",seconds=1)
        self.assertTrue(result["matched"] and result["released"])
        self.assertEqual((self.root/"out"/"capture.bin").read_bytes(),run_text(7)+run_text(8))
        self.assertEqual(result["complete_runs"],2)
        self.assertEqual(result["runs"][1]["crc"],"0359210D")
        self.assertEqual(result["errors"],[])
        self.assertEqual(client.events[-2:],["close","release"])
    def test_cleanup_after_program_read_and_close_errors(self):
        for fault in ("burn","read","close","reserve"):
            with self.subTest(fault=fault):
                client=FakeClient(fail=fault)
                with self.assertRaises((RuntimeError,TimeoutError)):
                    MODULE.capture(client,self.sbit,self.root/fault,seconds=1)
                self.assertFalse(client.held)
                result=json.loads((self.root/fault/"result.json").read_text())
                self.assertTrue(result["released"])
    def test_existing_reservation_is_untouched(self):
        client=FakeClient(existing=True)
        with self.assertRaises(RuntimeError): MODULE.capture(client,self.sbit,self.root/"existing")
        self.assertEqual(client.events,[])
        self.assertTrue(client.held)
    def test_timeout_is_a_failed_measurement_with_raw_evidence(self):
        client=FakeClient()
        result=MODULE.capture(client,self.sbit,self.root/"timeout",seconds=0)
        self.assertFalse(result["matched"])
        self.assertEqual(result["bytes"],0)
        self.assertTrue(result["released"])

class RecordTests(unittest.TestCase):
    def test_late_tail_is_ignored_then_two_complete_runs_qualify(self):
        data=b"0359210D ERR=00000000\r\nPACERV_SHARED PASS\r\n"+run_text(17)+run_text(18)
        result=MODULE.analyze_capture(data)
        self.assertTrue(result["matched"])
        self.assertEqual(result["complete_runs"],2)
    def test_truncated_begin_crc_or_pass_does_not_qualify(self):
        for data in (b"PACERV_SHARED PASS\r\n",run_text(1),run_text(1)+run_text(2)[:-1],
                     run_text(1)+run_text(2)[:40],run_text(1)[15:]+run_text(2)):
            with self.subTest(data=data): self.assertFalse(MODULE.analyze_capture(data)["matched"])
    def test_wrong_crc_and_nonzero_errors_fail(self):
        for sample,kind in ((run_text(1,crc="DEADBEEF"),"crc_mismatch"),
                            (run_text(1,errors="00000001"),"nonzero_error_count")):
            result=MODULE.analyze_capture(sample+run_text(2)+run_text(3))
            self.assertFalse(result["matched"])
            self.assertIn(kind,[row["kind"] for row in result["errors"]])
    def test_begins_cannot_supply_another_runs_crc(self):
        first=run_text(1).split(b"PACERV_SHARED PASS")[0]
        second=run_text(2).split(b"ISA=")[0]+b"PACERV_SHARED PASS\r\n"
        result=MODULE.analyze_capture(first+second)
        self.assertFalse(result["matched"])
        self.assertIn("missing_crc_line",[row["kind"] for row in result["errors"]])
    def test_duplicate_or_skipped_sequence_fails(self):
        for sequence in (1,3):
            result=MODULE.analyze_capture(run_text(1)+run_text(sequence))
            self.assertFalse(result["matched"])
            self.assertIn("sequence_discontinuity",[row["kind"] for row in result["errors"]])
    def test_sequence_wrap_and_single_pass_option(self):
        self.assertTrue(MODULE.analyze_capture(run_text(0xffffffff)+run_text(0))["matched"])
        self.assertTrue(MODULE.analyze_capture(run_text(20),passes=1)["matched"])
    def test_explicit_failure_is_retained_even_before_good_runs(self):
        result=MODULE.analyze_capture(b"PACERV_SHARED FAIL DDR_INIT_OR_BOOT_TEST\r\n"+run_text(1)+run_text(2))
        self.assertFalse(result["matched"])
        self.assertEqual(result["errors"][0]["kind"],"firmware_fail")

if __name__=="__main__": unittest.main()
