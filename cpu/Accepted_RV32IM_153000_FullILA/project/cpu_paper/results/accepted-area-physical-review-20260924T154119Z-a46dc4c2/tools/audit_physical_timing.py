"""Audit both timing corners and explicitly disclose the accepted asynchronous I/O scope."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from uuid import uuid4
import run_embench as helper


def audit(run):
    timing_path = run / "implementation/report_timing/pds_soc_top.rtr"
    log_path = run / "implementation/run.log"
    timing = timing_path.read_text(encoding="utf-8-sig")
    log = log_path.read_text(encoding="utf-8-sig")
    clock = "clk|multiplied_clock.clock_source/pll/CLKOUT0_Inferred"
    sections = re.findall(r"^(Setup|Hold|Recovery|Removal|Minimum Pulse Width) Summary\((Slow|Fast) Corner\):\s*\n(.*?)(?=^=)",timing,re.M|re.S)
    if len(sections) != 10 or len({(kind,corner) for kind,corner,_ in sections}) != 10:
        raise ValueError("Expected five unique timing checks in each corner")
    checks = {}
    for kind,corner,body in sections:
        prefix = re.escape(clock)+r"\s+"
        if kind != "Minimum Pulse Width":
            prefix += re.escape(clock)+r"\s+"
        number = r"(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+(\d+)\s+(\d+)"
        found = re.findall(prefix+number,body)
        if len(found) != 1:
            raise ValueError("Missing unique CPU " + kind + " " + corner + " row")
        slack,total,fail,endpoints = found[0]
        all_rows = re.findall(number,body)
        checks[kind+"_"+corner] = {"cpu_slack_ns":float(slack),"cpu_total_slack_ns":float(total),
                                  "cpu_failing_endpoints":int(fail),"cpu_endpoints":int(endpoints),
                                  "all_clock_minimum_slack_ns":min(float(row[0]) for row in all_rows),
                                  "all_clock_failing_endpoints":sum(int(row[2]) for row in all_rows)}
    constraints = (run / "inputs/constraints/board.fdc").read_text(encoding="utf-8-sig")
    if "set_false_path -from [get_ports {rst_n key uart_rx}]" not in constraints:
        raise ValueError("Unexpected asynchronous input constraints")
    warnings = re.findall(r"^W: Timing-(408[67]): Port '([^']+)' is not constrained, it is treated as combinational (input|output)\.",log,re.M)
    expected = {("4086",name,"input") for name in ("rst_n","key","uart_rx")}
    expected |= {("4087",name,"output") for name in ["uart_tx"]+[f"led[{i}]" for i in range(8)]}
    if set(warnings) != expected:
        raise ValueError("Unexpected unconstrained-port inventory")
    uncovered = [line for line in log.splitlines() if re.search(r"unconstrained|unclocked|not constrained|no clock",line,re.I)
                 and not re.match(r"^W: Timing-408[67]: Port '",line)]
    if uncovered:
        raise ValueError("Additional uncovered timing diagnostics: " + str(uncovered))
    passed = all(row["cpu_endpoints"] > 0 and row["all_clock_minimum_slack_ns"] >= 0 and row["all_clock_failing_endpoints"] == 0 for row in checks.values())
    result = {"schema":1,"run":str(run),"checks":checks,"internal_multicorner_timing_passed":passed,
            "cpu_setup_wns_ns":min(checks["Setup_"+corner]["cpu_slack_ns"] for corner in ("Slow","Fast")),
            "cpu_hold_wns_ns":min(checks["Hold_"+corner]["cpu_slack_ns"] for corner in ("Slow","Fast")),
            "constraint_scope":"Accepted constraints unchanged. Reset, key and UART RX are asynchronous/false-pathed; LED and UART TX have no synchronous external timing specification. Closure covers reported internal/generated-clock and ILA clock timing, not externally timed GPIO/UART paths.",
            "unconstrained_port_diagnostics":sorted(set(warnings)),"hardware_validated":False,
            "timing_sha256":helper.sha(timing_path),"implementation_log_sha256":helper.sha(log_path),
            "board_constraint_sha256":helper.sha(run / "inputs/constraints/board.fdc"),
            "uart_constraint_sha256":helper.sha(run / "inputs/constraints/uart_remotelab.fdc")}
    manifest = json.loads((run / 'manifest.json').read_text(encoding='utf-8-sig'))
    if manifest.get('instrumentation_profile') == 'none':
        result['constraint_scope'] = result['constraint_scope'].replace(
            'reported internal/generated-clock and ILA clock timing',
            'reported internal/generated-clock timing with ILA omitted')
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("run",type=Path)
    args=parser.parse_args()
    run=args.run.resolve()
    if not run.is_relative_to((helper.ROOT / "results").resolve()):
        raise ValueError("Run must be within project results")
    result=audit(run)
    out=helper.ROOT / "results" / ("timing-audit-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-"+uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    helper.snapshot(Path(__file__),out / "runner.py")
    helper.write_json(out / "audit.json",result)
    print(json.dumps(result,indent=2)); print(out)


if __name__ == "__main__":
    main()
