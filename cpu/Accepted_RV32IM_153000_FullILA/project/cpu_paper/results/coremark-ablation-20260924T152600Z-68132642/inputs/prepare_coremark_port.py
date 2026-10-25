"""Create an isolated, attributed CoreMark port without modifying original inputs."""
from pathlib import Path
import json
import hashlib

ROOT = Path(__file__).resolve().parents[1]
CPU = ROOT.parent / "cpu"
TARGET = ROOT / "ports/coremark"


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Unexpected source shape: " + old[:80])
    return text.replace(old, new, 1)


def main():
    TARGET.mkdir(exist_ok=False)
    provenance = {}
    def source(path):
        raw = path.read_bytes()
        provenance[str(path.relative_to(ROOT.parent))] = hashlib.sha256(raw).hexdigest()
        return raw.decode("utf-8-sig").replace("\r\n", "\n")
    port = source(CPU / "sw/coremark/core_portme.c")
    port = replace_once(port, '#include "../platform.h"', '#include "platform.h"')
    begin = port.index("static void snapshot_cache")
    end = port.index("CORE_TICKS get_time", begin)
    port = port[:begin] + '''/* One hardware snapshot supplies every counter in a common interval. */
static void snapshot_all(unsigned long long *cycles, unsigned long long *retired, u32 *cache) {
    PERF_SNAPSHOT = 1;
    u32 cycle_low = PERF_CYCLES_LOW, cycle_high = PERF_CYCLES_HIGH;
    u32 retired_low = PERF_RETIRED_LOW, retired_high = PERF_RETIRED_HIGH;
    *cycles = ((unsigned long long)cycle_high << 32) | cycle_low;
    *retired = ((unsigned long long)retired_high << 32) | retired_low;
    cache[0] = PERF_I_HITS;
    cache[1] = PERF_I_MISSES;
    cache[2] = PERF_D_HITS;
    cache[3] = PERF_D_MISSES;
    cache[4] = PERF_WRITEBACKS;
}
void start_time(void) { snapshot_all(&start_cycles, &start_retired, start_cache); }
void stop_time(void) { snapshot_all(&stop_cycles, &stop_retired, stop_cache); }
''' + port[end:]
    port = replace_once(port, '    portable->portable_id = 1;', '    STATUS_CODE = 0xc0100002u;\n    portable->portable_id = 1;')
    (TARGET / "core_portme.c").write_text(port, encoding="utf-8")
    for name in ("core_portme.h", "ee_printf.c"):
        text = source(CPU / "sw/coremark" / name)
        if name == "ee_printf.c":
            text = replace_once(text, '#include "../platform.h"', '#include "platform.h"')
            text = replace_once(text, '__asm__ volatile ("csrr %0, mcycle" : "=r"(started));', 'started = TIME_LOW;')
            text = replace_once(text, '__asm__ volatile ("csrr %0, mcycle" : "=r"(current));', 'current = TIME_LOW;')
        (TARGET / name).write_text(text, encoding="utf-8")
    (TARGET / "platform.h").write_text(source(CPU / "sw/platform.h"), encoding="utf-8")
    sim = source(ROOT / "ports/embench/sim_main.cpp")
    sim = replace_once(sim, "        bool previous_tx = true, receiving = false;", "        bool command_started = false;\n        uint64_t command_start = 0;\n        bool previous_tx = true, receiving = false;")
    sim = replace_once(sim, "model->status_code == 0xeb000000U", "model->status_code == 0xc0100002U")
    sim = replace_once(sim, "model->status_code == 0xeb000001U", "model->status_code == 0xc0100001U")
    sim = replace_once(sim, "PASS RTL Embench smoke", "PASS RTL CoreMark smoke")
    sim = replace_once(sim, "            previous_tx = tx;", '''            previous_tx = tx;
            if (!command_started && model->status_code == 0xc0100000U) {
                command_started = true; command_start = cycle;
                model->serial_rx = 0; model->eval();
            } else if (command_started && cycle - command_start <= 288) {
                uint64_t position = cycle - command_start;
                if (position != 0 && position % 32 == 0) {
                    unsigned command_bit = unsigned(position / 32 - 1);
                    model->serial_rx = command_bit < 8 ? ((0x47U >> command_bit) & 1U) : 1U;
                    model->eval();
                }
            }''')
    sim = replace_once(sim, '(model->status_code & 0xffffff00U) == 0xeb000000U && (model->status_code & 0xffU) >= 0xf0U', '(model->status_code & 0xffff0000U) == 0xdead0000U')
    (TARGET / "sim_main.cpp").write_text(sim, encoding="utf-8")
    (TARGET / "README.md").write_text("# External CoreMark port\n\nDerived from cpu/sw/coremark and cpu/sw/platform.h. CoreMark algorithms and license remain in the pinned dependencies/coremark checkout. See provenance.json and scripts/prepare_coremark_port.py for exact source identity and transformations. Protocol v4 specifies atomic cycle/retirement boundaries. The simulation harness derives from ports/embench/sim_main.cpp and adds the existing UART G handshake and CoreMark status markers.\n", encoding="utf-8")
    (TARGET / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(TARGET)


if __name__ == "__main__":
    main()
