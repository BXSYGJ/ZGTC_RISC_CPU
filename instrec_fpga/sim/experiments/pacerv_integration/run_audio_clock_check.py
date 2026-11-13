"""Check physical 48 kHz I2S capture at original and selected core clocks."""
from __future__ import annotations

import concurrent.futures
import datetime as dt
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
VERILATOR = "/home/bx/.local/src/verilator-5.040/bin/verilator"


def linux(path: Path) -> str:
    value = path.resolve().as_posix()
    return "/mnt/" + value[0].lower() + value[2:]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def execute(command: list[str], log: Path, timeout: int) -> dict:
    started = time.monotonic()
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW)
    log.write_bytes(result.stdout)
    stderr = log.with_suffix(log.suffix + '.stderr')
    stderr.write_bytes(result.stderr)
    return {"command": command, "exit_status": result.returncode,
            "seconds": time.monotonic() - started, "log": str(log),
            "log_sha256": sha(log), "stderr_log": str(stderr), "stderr_sha256": sha(stderr)}


def main() -> int:
    out = ROOT / "build/pacerv_shared_system/audio_clock" / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    sources = [ROOT / "src/audio" / name for name in
               ("i2s_slave_rx.v", "audio_cdc_fifo.v", "audio_sink.v")]
    original_tb = ROOT / "sim/tb_audio_chain.sv"
    top = ROOT / "src/ctrl/instrec_top.v"
    monitored = [*sources, original_tb, top, ROOT / "ipcore/ddr3_test/ddr3_test.idf",
                 ROOT / "constraints/ddr3_100h.fdc"]
    inputs = {str(p): sha(p) for p in monitored}
    text = original_tb.read_text(encoding="utf-8")
    # Keep bit zero stable until its sampling edge; change SD at the first
    # padding falling edge, while retaining the original 32-bit slot length.
    stimulus = "            sd = 1'b1;\n            repeat (15) @(negedge bck);"
    if text.count(stimulus) != 1:
        raise RuntimeError("Expected one serial padding sequence")
    text = text.replace(stimulus,
        "            @(negedge bck); sd = 1'b1;\n            repeat (14) @(negedge bck);")
    text = text.replace("if (real_cnt*10 >= 4096*9)",
        "if (real_cnt == 132096 && inj_cnt == 0 && overflow_cnt == 0 && err_cnt == 0)")
    text = text.replace('$display("RESULT: PASS audio_chain (>=90%% real frames)");',
        '$display("AUDIO_CLOCK_PASS real=132096 injection=0 overflow=0 errors=0 ordered_samples=1");')
    text = text.replace('$display("RESULT: FAIL audio_chain (real=%0d of 4096)", real_cnt);',
        '$fatal(1, "audio window real=%0d injection=%0d overflow=%0d errors=%0d", real_cnt, inj_cnt, overflow_cnt, err_cnt);')
    observer = [
        "    reg stream_seen = 0;", "    reg [15:0] previous_left = 0;",
        "    always @(posedge clk125) begin",
        "        if (!rst_n) stream_seen <= 0;",
        "        else if (fifo_rd_valid) begin",
        "            if (stream_seen && fifo_rd_data[31:16] !== previous_left + 16'd1)",
        '                $fatal(1, "audio sample sequence gap previous=%h current=%h", previous_left, fifo_rd_data);',
        "            if (fifo_rd_data[15:0] !== (fifo_rd_data[31:16] ^ 16'h8000))",
        '                $fatal(1, "audio stereo sample mismatch");',
        "            previous_left <= fifo_rd_data[31:16]; stream_seen <= 1;",
        "        end", "    end", "",
    ]
    text = text.replace("    // short-mode diagnostics:", "\n".join(observer) + "    // short-mode diagnostics:")
    if 'AUDIO_CLOCK_PASS' not in text or 'audio sample sequence gap' not in text:
        raise RuntimeError("Audio observer insertion failed")
    probe = ["wsl.exe", "-d", "Ubuntu-22.04", "--cd", linux(ROOT), "--exec"]

    def case(hz: int) -> dict:
        work = out / str(hz)
        work.mkdir()
        source = work / "tb_audio_chain.sv"
        local = text.replace("always #4.0     clk125", f"always #{5e8 / hz:.9f}     clk125")
        local = local.replace("audio_sink u_sink (", "audio_sink #(" +
            f".INJECT_GAP_CYCLES(14'd{round(hz/48000)}), " +
            f".WR_TIMEOUT_CYCLES(23'd{round(4194304*hz/125000000)})) u_sink (")
        source.write_text(local, encoding="utf-8")
        compile_command = probe + [VERILATOR, "--binary", "--timing", "-Wno-fatal",
            "--top-module", "tb_audio_chain", "-j", "2", "--Mdir", linux(work / "obj"),
            linux(source), *(linux(p) for p in sources)]
        compilation = execute(compile_command, work / "compile.log", 240)
        report = {"clock_hz": hz, "ddr_done_delay_cycles": 512, "compile": compilation,
                  "tb_sha256": sha(source), "passed": False}
        if compilation["exit_status"] == 0:
            run = execute(probe + [linux(work / "obj/Vtb_audio_chain"), "+FULL", "+DLY=512"],
                          work / "simulation.log", 1800)
            report["simulation"] = run
            output = (work / "simulation.log").read_text(encoding="utf-8", errors="replace")
            report["literal_results"] = [line for line in output.splitlines()
                                         if line.startswith(("WIN ", "AUDIO_CLOCK_PASS"))]
            report["passed"] = run["exit_status"] == 0 and "AUDIO_CLOCK_PASS" in output
        (work / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print("AUDIO_CLOCK_CASE clock_hz=" + str(hz) + " passed=" + str(report["passed"]), flush=True)
        return report

    print("AUDIO_CLOCK_PREPARED " + str(out), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        reports = list(pool.map(case, (125000000, 109375000)))
    unchanged = all(sha(Path(name)) == expected for name, expected in inputs.items())
    report = {"scope": "Physical-rate I2S, CDC FIFO and production audio sink; behavioural DDR completion",
              "audio_sample_rate_hz": 48000, "window_frames": 132096, "windows_per_case": 2,
              "inputs_sha256": inputs, "live_inputs_unchanged": unchanged,
              "cases": reports, "passed": unchanged and all(r["passed"] for r in reports)}
    (out / "RESULT.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("AUDIO_CLOCK_" + ("PASS" if report["passed"] else "FAIL") + " " + str(out), flush=True)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
