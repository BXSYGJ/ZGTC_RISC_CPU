#include "Vrv32_soc.h"
#include "verilated.h"
#include <cstdint>
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
