import importlib.util
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import audit_fetch_ila as physical
from audit_fetch_scope_firmware import audit_firmware
from build_scope_firmware import BASE, NAME
from audit_fetch_inputs import ROOT, digest, require, load

SPEC = importlib.util.spec_from_file_location("fetch_scope_decoder", ROOT / "scripts/scope_decode.py")
decoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(decoder)
OVERRIDES = dict(CLOCK_HZ=3200, BAUD=100, clock_period_ns=10, uart_injected_bit_cycles=15938,
                 key_pulse_cycles=45333, timeout_counter_jumps=[4294967296, 295032704])


def validate_support():
    bench = (ROOT / "sim/scope_tb.sv").read_text(encoding="utf-8")
    require(bench == (BASE / "sim/scope_tb.sv").read_text(encoding="utf-8"), "Base scope bench differs")
    previous = (BASE / "scripts/scope_decode.py").read_text(encoding="utf-8")
    anchor = "(27000000, 151200000, 154285714, 157500000)"
    require(previous.count(anchor) == 1, "Scope decoder clock anchor differs")
    cli_anchor = "choices=(27000000, 157500000)"
    require(previous.count(cli_anchor) == 1, "Scope decoder CLI clock anchor differs")
    expected = previous.replace(anchor, "(27000000, 151200000, 153000000, 154285714, 157500000)").replace(cli_anchor, "choices=(27000000, 153000000, 157500000)")
    require((ROOT / "scripts/scope_decode.py").read_text(encoding="utf-8") == expected, "Scope decoder changed beyond clock whitelist")
    return {name: digest(ROOT / name) for name in ("sim/scope_tb.sv", "scripts/scope_decode.py")}


def generate_bench(parameters, bench=None):
    if bench is None:
        bench = (ROOT / "sim/scope_tb.sv").read_text(encoding="utf-8")
    def replace_unique(before, after, count=1):
        nonlocal bench
        require(bench.count(before) == count, "Scope bench anchor changed: " + before)
        bench = bench.replace(before, after)
    instantiation = "rv32_soc #(.CLOCK_HZ(3200),.BAUD(100)," + ",".join(f".{key}({value})" for key, value in parameters.items()) + ") soc(.*);"
    replace_unique("rv32_soc #(.CLOCK_HZ(3200),.BAUD(100)) soc(.*);", instantiation)
    replace_unique("send_byte(8'h55,2813);", "send_byte(8'h55,15938);")
    replace_unique("repeat(8000)", "repeat(45333)", count=3)
    wait_line = "        wait(timeout_count==1);"
    injected = ["        @(negedge clk); soc.core.machine.mcycle=soc.core.machine.mcycle+64'd4294967296;",
                "        repeat(10000) @(negedge clk);",
                '        if(timeout_count!=0) $fatal(1,"Scope timeout before full 30-second interval");',
                "        @(negedge clk); soc.core.machine.mcycle=soc.core.machine.mcycle+64'd295032704;", wait_line]
    replace_unique(wait_line, "\n".join(injected))
    progress = "        cycles=cycles+1;"
    replace_unique(progress, progress + '\n        if(cycles%10000==0) $display("SCOPE_PROGRESS cycles=%0d status=%08x pc=%08x mcycle=%0d dumps=%0d timeout=%0d empty=%0d",cycles,status_code,trace_pc,soc.core.machine.mcycle,dumps,timeout_count,empty_count);')
    flush = "                if(observed==10) begin"
    replace_unique(flush, flush + "\n                    $fflush(uart_file);")
    return bench


def run(command, output, timeout=600):
    with output.open("w", encoding="utf-8") as log:
        try:
            completed = subprocess.run(list(map(str, command)), stdout=log, stderr=subprocess.STDOUT, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            log.write("\nHOST_TIMEOUT_SECONDS=" + str(timeout) + "\n")
            log.flush()
            raise
    require(completed.returncode == 0, "Current scope command failed: " + str(output))
    return output.read_text(encoding="utf-8")


def validate_output(log_text, uart):
    terminal = re.findall(r"^PASS scope cycles=(\d+) dumps=2 timeout=1 empty=1$", log_text, re.M)
    require(len(terminal) == 1 and not re.search(r"(?:FATAL|FAIL|HOST_TIMEOUT_SECONDS)", log_text), "Scope terminal assertion missing or failure reported")
    captures = decoder.parse_captures(uart, expected_clock_hz=153000000)
    require(len(captures) == 2 and {capture["trigger_mask"] for capture in captures} == {1, 2}, "Both input channels required")
    for capture in captures:
        require(capture["period_cycles"] == 1224 and capture["late_samples"] == 0, "Scope sampling period or late count failed")
        if capture["trigger_mask"] == 2:
            require(decoder.decode_triggered_uart(capture, 9600) == 0x55, "Actual current-clock UART waveform mismatch")
        else:
            require([level for timestamp, level in decoder.transitions(capture, 0)] == [0, 1, 0], "Actual KEY pulse pattern mismatch")
    return int(terminal[0]), captures


def main():
    bound = physical.binding()
    support = validate_support()
    audit_firmware()
    source = physical.SOURCE
    snapshot = load(source / "source-snapshot.json")
    metadata = load(ROOT / "build" / (NAME + ".build.json"))
    firmware = ROOT / "build" / (NAME + ".hex")
    parameters = bound["hardware_parameters"]
    bench = generate_bench(parameters)
    output = ROOT / "build/scope-current" / (datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
    output.mkdir(parents=True, exist_ok=False)
    for relative in snapshot["Files"]:
        if relative.startswith("rtl/"):
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / "source" / relative, destination)
    testbench = output / "scope_tb.sv"
    testbench.write_text(bench, encoding="utf-8")
    shutil.copyfile(firmware, output / "firmware.hex")
    sources = sorted((output / "rtl").glob("*.sv")) + [testbench]
    inputs = {item.relative_to(output).as_posix(): digest(item) for item in sources}
    commands = [["iverilog", "-g2012", "-Wall", "-s", "scope_tb", "-o", str(output / "scope.vvp"), *map(str, sources)],
                ["vvp", "-i", str(output / "scope.vvp"), "+firmware=" + str(output / "firmware.hex"), "+uart=" + str(output / "scope.uart")]]
    record = dict(scope="current full-CPU application RTL simulation; not board or physical timing proof", source_snapshot=snapshot,
                  firmware_metadata=metadata, firmware_sha256=digest(firmware), physical_parameters=dict(parameters, CLOCK_HZ=153000000, UART_BAUD=115200),
                  host_timeout_seconds=1800, simulation_overrides=OVERRIDES, input_hashes=inputs, support_hashes=support,
                  runner_sha256=digest(Path(__file__)), commands=commands, started_utc=datetime.now(timezone.utc).isoformat(),
                  passed=False, hardware_validated=False)
    manifest = output / "manifest.json"
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("CURRENT_SCOPE_RUN=" + output.as_posix(), flush=True)
    run(commands[0], output / "compile.log", 90)
    log_text = run(commands[1], output / "execute.log", 1800)
    cycles, captures = validate_output(log_text, (output / "scope.uart").read_text(encoding="utf-8"))
    for index, capture in enumerate(captures):
        (output / f"capture-{index}.svg").write_text(decoder.waveform_svg(capture), encoding="utf-8")
    for relative, expected in inputs.items():
        require(digest(output / relative) == expected, "Scope simulation input changed")
    audit_firmware(output / "firmware.hex")
    require(validate_support() == support and record["runner_sha256"] == digest(Path(__file__)), "Scope runner or support changed during simulation")
    record.update(passed=True, completed_utc=datetime.now(timezone.utc).isoformat(), cycles=cycles,
                  captures=[{key: value for key, value in capture.items() if key != "records"} for capture in captures],
                  outputs_sha256={name: digest(output / name) for name in ("scope.uart", "execute.log", "compile.log", "scope.vvp", "capture-0.svg", "capture-1.svg")})
    manifest.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print("PASS current 153 MHz scope: UART55, KEY pattern, EMPTY and bounded 64-bit timeout; simulation only", flush=True)


if __name__ == "__main__":
    main()
