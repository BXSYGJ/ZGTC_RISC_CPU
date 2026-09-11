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
        std::ofstream loop_trace(std::string(argv[1]) + ".loop.csv", std::ios::binary);
        if (!loop_trace) throw std::runtime_error("Cannot open loop timing trace");
        loop_trace << "schema,1,sampling,pre_positive_edge_after_negative_edge,target_pc,1300\n";
        loop_trace << "cycle,query,update,fetch_pc,predicted_pc,update_pc,target,taken,conditional,prior_prediction,valid,tag0,count0,trip0,confidence0,overflow0,direction0,tag1,count1,trip1,confidence1,overflow1,direction1\n";
        uint64_t loop_records = 0;
        uint64_t loop_queries = 0;
        uint64_t loop_captures = 0;
        bool loop_capture_pending = false;
        uint32_t loop_capture_expected = 0;
        uint32_t loop_capture_pc = 0;
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
            if (loop_capture_pending) {
                if (model->rv32_soc__DOT__core__DOT__fetch_prediction != loop_capture_expected ||
                    model->rv32_soc__DOT__core__DOT__fetch_address != loop_capture_pc)
                    throw std::runtime_error("Observed loop query differs from actual registered capture");
                ++loop_captures;
            }
            const bool loop_query = (!model->rv32_soc__DOT__core__DOT__fetch_active || model->rv32_soc__DOT__core__DOT__fetch_complete) &&
                !model->rv32_soc__DOT__core__DOT__mem_flush && !model->rv32_soc__DOT__core__DOT__ex_redirect &&
                !model->rv32_soc__DOT__core__DOT__frontend_barrier && model->rv32_soc__DOT__core__DOT__next_pc == 0x514U;
            const bool loop_update = model->rv32_soc__DOT__core__DOT__mem_fire && model->rv32_soc__DOT__core__DOT__mem_branch &&
                !model->rv32_soc__DOT__core__DOT__mem_fault;
            const uint32_t loop_prediction = model->rv32_soc__DOT__core__DOT__prediction_hit && model->rv32_soc__DOT__core__DOT__predicted_taken ?
                model->rv32_soc__DOT__core__DOT__predicted_target : model->rv32_soc__DOT__core__DOT__next_pc + 4U;
            loop_capture_pending = loop_query;
            loop_capture_expected = loop_prediction;
            loop_capture_pc = model->rv32_soc__DOT__core__DOT__next_pc;
            if (loop_query || loop_update) {
                loop_trace << model->cycle_count << ',' << loop_query << ',' << loop_update << ','
                    << model->rv32_soc__DOT__core__DOT__next_pc << ',' << loop_prediction << ','
                    << model->rv32_soc__DOT__core__DOT__mem_pc << ',' << model->rv32_soc__DOT__core__DOT__mem_target << ','
                    << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__mem_taken) << ','
                    << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__mem_conditional) << ','
                    << model->rv32_soc__DOT__core__DOT__mem_prediction << ','
                    << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__predictor__DOT__loop_valid);
                for (unsigned loop_slot = 0; loop_slot < 2; ++loop_slot) {
                    loop_trace << ',' << model->rv32_soc__DOT__core__DOT__predictor__DOT__loop_tags[loop_slot]
                        << ',' << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__predictor__DOT__loop_count[loop_slot])
                        << ',' << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__predictor__DOT__loop_trip[loop_slot])
                        << ',' << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__predictor__DOT__loop_confidence[loop_slot])
                        << ',' << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__predictor__DOT__loop_overflow[loop_slot])
                        << ',' << static_cast<unsigned>(model->rv32_soc__DOT__core__DOT__predictor__DOT__loop_direction[loop_slot]);
                }
                loop_trace << '\n';
                ++loop_records;
                loop_queries += loop_query;
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
                if (loop_queries == 0 || loop_captures != loop_queries || loop_capture_pending)
                    throw std::runtime_error("Incomplete loop query capture checks");
                loop_trace << "END," << loop_records << ',' << loop_queries << ',' << loop_captures << '\n';
                loop_trace.flush();
                if (!loop_trace) throw std::runtime_error("Loop timing trace write failed");
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
