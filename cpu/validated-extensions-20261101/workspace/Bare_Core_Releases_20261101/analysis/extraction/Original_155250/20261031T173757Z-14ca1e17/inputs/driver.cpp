#include "Vbare_extraction_miter.h"
#include "verilated.h"
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#if MITER_NATIVE
#include "native_timing_tick_v2.h"
#else
static vluint64_t sim_time = 0;
double sc_time_stamp() { return static_cast<double>(sim_time); }
#endif

static uint64_t append_word(uint64_t digest, uint32_t value) {
    for (unsigned byte = 0; byte < 4; ++byte) {
        digest ^= (value >> (byte * 8)) & 255U;
        digest *= 1099511628211ULL;
    }
    return digest;
}

int main(int argc, char **argv) {
    try {
        if (argc != 4) throw std::runtime_error("Expected result JSON, cycle limit and injected-fault edge");
        for (int index = 2; index < 4; ++index) {
            std::string text(argv[index]);
            if (text.empty() || text.find_first_not_of("0123456789") != std::string::npos)
                throw std::runtime_error("Invalid edge count");
        }
        const uint64_t limit = std::stoull(argv[2]);
        const uint64_t fault_edge = std::stoull(argv[3]);
        if (!limit || limit > 10000000ULL || fault_edge > limit)
            throw std::runtime_error("Observation edge count is out of range");
#if MITER_NATIVE
        VerilatedContext context;
        context.commandArgs(argc, argv);
        auto model = std::make_unique<Vbare_extraction_miter>(&context);
#else
        Verilated::commandArgs(argc, argv);
        auto model = std::make_unique<Vbare_extraction_miter>();
#endif
        model->clk = 0; model->rst_n = 1; model->serial_rx = 1;
        model->gpio_input = 0; model->inject_bus_fault = 0;
        model->eval(); model->rst_n = 0; model->eval();
        auto tick = [&]() {
#if MITER_NATIVE
            native_tick(context, *model);
#else
            sim_time += 5; model->clk = 1; model->eval();
            sim_time += 5; model->clk = 0; model->eval();
#endif
        };
        for (unsigned cycle = 0; cycle < 4; ++cycle) tick();
        model->rst_n = 1; model->eval();
        bool command_started = false, previous_tx = true, receiving = false;
        uint64_t command_start = 0, deadline = 0;
        int bit = -1;
        unsigned byte = 0;
        std::string uart;
        uint64_t reference_digest = 1469598103934665603ULL;
        uint64_t bare_digest = reference_digest;
        uint64_t retired_events = 0, writes = 0, i_requests = 0, i_responses = 0;
        uint64_t d_requests = 0, d_responses = 0, maintenance = 0;
        uint64_t list_entries = 0, matrix_entries = 0, state_entries = 0;
        uint64_t comparisons = 0;
        auto compare = [&](uint64_t cycle, const char *phase) {
            ++comparisons;
            if (model->mismatch) {
                std::cerr << "EXTRACTION_MISMATCH edge=" << cycle << " phase=" << phase
                          << " mask=0x" << std::hex << model->mismatch << std::dec << '\n';
                throw std::runtime_error("Bare DUT and independent reference port frames differ");
            }
        };
        for (uint64_t cycle = 1; cycle <= limit; ++cycle) {
            if (cycle == fault_edge) { model->inject_bus_fault = 1; model->eval(); }
            compare(cycle, "preedge");
            for (unsigned word = 0; word < MITER_FRAME_WORDS; ++word) {
                reference_digest = append_word(reference_digest, model->reference_frame[word]);
                bare_digest = append_word(bare_digest, model->bare_frame[word]);
            }
            retired_events += model->trace_valid;
            writes += model->trace_write;
            i_requests += model->i_request_fire; i_responses += model->i_response_fire;
            d_requests += model->d_request_fire; d_responses += model->d_response_fire;
            maintenance += model->maintenance_fire;
            if (model->trace_valid) {
                list_entries += model->trace_pc == 0x942U;
                matrix_entries += model->trace_pc == 0x2604U;
                state_entries += model->trace_pc == 0x2e18U;
            }
            tick();
            compare(cycle, "postedge_and_settled_low");
            if (model->trap_valid || model->maintenance_fault)
                throw std::runtime_error("Unexpected trap or maintenance fault in extraction benchmark");
            bool tx = model->serial_tx;
            if (!receiving && previous_tx && !tx) {
                receiving = true; deadline = cycle + 16; bit = -1; byte = 0;
            }
            if (receiving && cycle == deadline) {
                if (bit == -1) { if (tx) throw std::runtime_error("Invalid UART start bit"); }
                else if (bit < 8) byte |= unsigned(tx) << bit;
                else {
                    if (!tx) throw std::runtime_error("Invalid UART stop bit");
                    uart.push_back(char(byte)); receiving = false;
                }
                ++bit; deadline += 32;
            }
            previous_tx = tx;
            if (!command_started && model->status_code == 0xc0100000U) {
                command_started = true; command_start = cycle; model->serial_rx = 0; model->eval();
            } else if (command_started && cycle - command_start <= 288) {
                uint64_t position = cycle - command_start;
                if (position && position % 32 == 0) {
                    unsigned command_bit = unsigned(position / 32 - 1);
                    model->serial_rx = command_bit < 8 ? ((0x47U >> command_bit) & 1U) : 1U;
                    model->eval();
                }
            }
            if ((model->status_code & 0xffff0000U) == 0xdead0000U)
                throw std::runtime_error("Firmware status reports an execution failure");
            if (Verilated::gotFinish()) throw std::runtime_error("Unexpected simulation finish");
        }
        if (fault_edge) throw std::runtime_error("Injected fault was not detected");
        if (limit >= 2000000ULL && (!list_entries || !matrix_entries || !state_entries))
            throw std::runtime_error("The observation did not execute all three CoreMark kernel entries");
        if (reference_digest != bare_digest) throw std::runtime_error("Independent frame digests differ");
        std::ofstream uart_file("uart.log", std::ios::binary);
        uart_file.write(uart.data(), uart.size()); uart_file.close();
        std::ofstream result(argv[1]);
        result << "{\n  \"status\": \"PASS\",\n  \"cpu_edges\": " << limit
               << ",\n  \"port_frame_comparisons\": " << comparisons
               << ",\n  \"frame_bits\": " << MITER_FRAME_BITS
               << ",\n  \"reference_frame_fnv1a64\": \"" << std::hex << std::setw(16) << std::setfill('0') << reference_digest
               << "\",\n  \"bare_frame_fnv1a64\": \"" << std::setw(16) << bare_digest << std::dec
               << "\",\n  \"cycle_count\": " << model->cycle_count
               << ",\n  \"retired_count\": " << model->retired_count
               << ",\n  \"retired_events\": " << retired_events << ",\n  \"register_writes\": " << writes
               << ",\n  \"i_requests\": " << i_requests << ",\n  \"i_responses\": " << i_responses
               << ",\n  \"d_requests\": " << d_requests << ",\n  \"d_responses\": " << d_responses
               << ",\n  \"maintenance_completions\": " << maintenance
               << ",\n  \"kernel_entry_retirements\": {\"core_bench_list\": " << list_entries
               << ", \"core_bench_matrix\": " << matrix_entries << ", \"core_bench_state\": " << state_entries
               << "},\n  \"full_coremark_run\": false,\n  \"hardware_measurement\": false\n}\n";
        result.close(); if (!result) throw std::runtime_error("Extraction receipt write failed");
        model->final();
        std::cout << "EXTRACTION_PASS edges=" << limit << " comparisons=" << comparisons
                  << " retired=" << model->retired_count << " kernels=" << list_entries << ',' << matrix_entries << ',' << state_entries
                  << " digest=" << std::hex << reference_digest << std::dec << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "EXTRACTION_FAIL " << error.what() << '\n'; return 1;
    }
}
