#include "Vrv32_soc.h"
#include "verilated.h"
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>

static vluint64_t simulation_time = 0;
double sc_time_stamp() { return static_cast<double>(simulation_time); }

int main(int argc, char** argv) {
    try {
        if (argc != 3) throw std::runtime_error("Expected UART output path and positive cycle limit");
        const std::string limit_text(argv[2]);
        if (limit_text.empty() || limit_text.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("Cycle limit must contain decimal digits only");
        const uint64_t cycle_limit = std::stoull(limit_text);
        if (cycle_limit == 0 || cycle_limit > 1000000000000ULL)
            throw std::runtime_error("Cycle limit outside supported range");
        std::ofstream uart(argv[1], std::ios::binary);
        if (!uart) throw std::runtime_error("Cannot open UART output");
        uart << "ZGTC RTL_SIMULATION_ONLY\n";
        Verilated::commandArgs(argc, argv);
        const auto model = std::make_unique<Vrv32_soc>();
        model->clk = 0;
        model->rst_n = 1;
        model->serial_rx = 1;
        model->gpio_input = 0;
        model->eval();
        model->rst_n = 0;
        model->eval();
        const auto read_trace_pc = [](const char* name) -> uint32_t {
            const char* raw = std::getenv(name);
            if (!raw) throw std::runtime_error("Missing trace boundary environment variable");
            const std::string text(raw);
            if (text.empty() || text.size() > 8 || text.find_first_not_of("0123456789abcdefABCDEF") != std::string::npos)
                throw std::runtime_error("Trace boundary must contain one to eight hex digits");
            const unsigned long value = std::stoul(text, nullptr, 16);
            if (value > 0xffffffffUL || (value & 3UL) != 0) throw std::runtime_error("Trace boundary must be aligned RV32 address");
            return static_cast<uint32_t>(value);
        };
        const uint32_t trace_start_pc = read_trace_pc("ZGTC_TRACE_START_PC");
        const uint32_t trace_stop_pc = read_trace_pc("ZGTC_TRACE_STOP_PC");
        if (trace_start_pc == trace_stop_pc) throw std::runtime_error("Trace boundaries must be distinct");
        std::ofstream retirement_trace(std::string(argv[1]) + ".retire.bin", std::ios::binary);
        if (!retirement_trace) throw std::runtime_error("Cannot open retirement trace");
        bool trace_started = false;
        bool trace_finished = false;
        uint64_t trace_records = 0;
        uint64_t trace_start_cycle = 0;
        uint64_t trace_stop_cycle = 0;
        auto tick = [&]() {
            simulation_time += 5;
            model->clk = 1;
            model->eval();
            simulation_time += 5;
            model->clk = 0;
            model->eval();
        };
        for (unsigned reset_cycle = 0; reset_cycle < 4; ++reset_cycle) tick();
        model->rst_n = 1;
        model->eval();
        bool previous_tx = true;
        bool receive_active = false;
        bool command_started = false;
        uint64_t receive_deadline = 0;
        uint64_t command_start = 0;
        int receive_bit = -1;
        unsigned receive_byte = 0;
        for (uint64_t cycle = 1; cycle <= cycle_limit; ++cycle) {
            tick();
            if (model->trace_valid) {
                const uint32_t trace_pc = model->trace_pc;
                const uint32_t trace_instruction = model->trace_instruction;
                if (trace_pc == trace_start_pc) {
                    if (trace_started || (trace_instruction & 0xfffff07fU) != 0xb0002073U)
                        throw std::runtime_error("Duplicate or invalid trace start boundary");
                    trace_started = true;
                    trace_start_cycle = model->cycle_count;
                }
                if (trace_started && !trace_finished) {
                    char record[16];
                    const uint64_t timestamp = model->cycle_count;
                    for (unsigned byte_index = 0; byte_index < 8; ++byte_index)
                        record[byte_index] = static_cast<char>(timestamp >> (byte_index * 8));
                    for (unsigned byte_index = 0; byte_index < 4; ++byte_index) {
                        record[8 + byte_index] = static_cast<char>(trace_pc >> (byte_index * 8));
                        record[12 + byte_index] = static_cast<char>(trace_instruction >> (byte_index * 8));
                    }
                    retirement_trace.write(record, sizeof(record));
                    ++trace_records;
                }
                if (trace_pc == trace_stop_pc) {
                    if (!trace_started || trace_finished || (trace_instruction & 0xfffff07fU) != 0xb0002073U)
                        throw std::runtime_error("Missing start or invalid/duplicate stop boundary");
                    trace_finished = true;
                    trace_stop_cycle = model->cycle_count;
                }
            }
            const bool serial_tx = model->serial_tx;
            if (!receive_active && previous_tx && !serial_tx) {
                receive_active = true;
                receive_deadline = cycle + 16;
                receive_bit = -1;
                receive_byte = 0;
            }
            if (receive_active && cycle == receive_deadline) {
                if (receive_bit == -1) {
                    if (serial_tx) throw std::runtime_error("UART start bit invalid");
                } else if (receive_bit < 8) {
                    receive_byte |= static_cast<unsigned>(serial_tx) << receive_bit;
                } else {
                    if (!serial_tx) throw std::runtime_error("UART stop bit invalid");
                    uart.put(static_cast<char>(receive_byte));
                    std::cout.put(static_cast<char>(receive_byte));
                    if (receive_byte == 10) { uart.flush(); std::cout.flush(); }
                    receive_active = false;
                }
                ++receive_bit;
                receive_deadline += 32;
            }
            previous_tx = serial_tx;
            if (!command_started && model->status_code == 0xc0100000U) {
                command_started = true;
                command_start = cycle;
                model->serial_rx = 0;
                model->eval();
            } else if (command_started && cycle - command_start <= 288) {
                const uint64_t command_cycle = cycle - command_start;
                if (command_cycle != 0 && command_cycle % 32 == 0) {
                    const unsigned command_bit = static_cast<unsigned>(command_cycle / 32 - 1);
                    model->serial_rx = command_bit < 8 ? ((0x47U >> command_bit) & 1U) : 1U;
                    model->eval();
                }
            }
            if (model->trap_valid || model->maintenance_fault) {
                std::cerr << "Trap PC=" << std::hex << model->trace_pc
                          << " cause=" << model->trap_cause << std::dec << std::endl;
                throw std::runtime_error("Compiled CoreMark trap or maintenance fault");
            }
            if (model->status_code == 0xc0100001U) {
                if (!command_started || receive_active)
                    throw std::runtime_error("Incomplete CoreMark UART transaction");
                uart.flush();
                if (!uart) throw std::runtime_error("UART output write failed");
                if (!trace_started || !trace_finished || trace_records < 2 || trace_stop_cycle <= trace_start_cycle)
                    throw std::runtime_error("Incomplete retirement trace window");
                retirement_trace.flush();
                if (!retirement_trace) throw std::runtime_error("Retirement trace write failed");
                std::ofstream trace_summary(std::string(argv[1]) + ".retire.json");
                if (!trace_summary) throw std::runtime_error("Cannot open retirement trace summary");
                trace_summary << "{\n  \"schema\": 1,\n  \"record_bytes\": 16,\n  \"start_pc\": " << trace_start_pc
                              << ",\n  \"stop_pc\": " << trace_stop_pc << ",\n  \"records\": " << trace_records
                              << ",\n  \"start_cycle\": " << trace_start_cycle << ",\n  \"stop_cycle\": " << trace_stop_cycle
                              << ",\n  \"cycles\": " << trace_stop_cycle - trace_start_cycle << "\n}\n";
                trace_summary.flush();
                if (!trace_summary) throw std::runtime_error("Retirement trace summary write failed");
                model->final();
                std::cout << "PASS compiled RTL simulation cycles=" << cycle
                          << " retired=" << model->retired_count << std::endl;
                return 0;
            }
            if (cycle % 100000000ULL == 0)
                std::cerr << "Compiled RTL progress cycles=" << cycle << std::endl;
            if (Verilated::gotFinish()) throw std::runtime_error("Unexpected RTL finish");
        }
        throw std::runtime_error("Compiled CoreMark cycle limit exceeded");
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << std::endl;
        return 1;
    }
}
