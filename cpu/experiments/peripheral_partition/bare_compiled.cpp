#include "Vrv32_bare_sim.h"
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
        if (argc != 5) throw std::runtime_error("Expected output path, result path, result address and cycle limit");
        const std::string address_text(argv[3]);
        const std::string limit_text(argv[4]);
        if (address_text.empty() || address_text.find_first_not_of("0123456789abcdefABCDEF") != std::string::npos ||
            limit_text.empty() || limit_text.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("Invalid address or cycle limit syntax");
        const uint64_t result_address = std::stoull(address_text, nullptr, 16);
        const uint64_t limit = std::stoull(limit_text);
        if (result_address % 8 || result_address + 4128 > 65536 || limit == 0 || limit > 10000000000ULL)
            throw std::runtime_error("Out of range arguments");
        std::ofstream output(argv[1], std::ios::binary);
        std::ofstream result(argv[2]);
        if (!output || !result) throw std::runtime_error("Cannot open result files");
        Verilated::commandArgs(argc, argv);
        const auto model = std::make_unique<Vrv32_bare_sim>();
        model->clk = 0;
        model->rst_n = 1;
        model->read_word = result_address / 4;
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
        auto read = [&](unsigned offset) -> uint32_t {
            model->read_word = result_address / 4 + offset;
            model->eval();
            return model->memory_word;
        };
        for (uint64_t cycle = 1; cycle <= limit; ++cycle) {
            tick();
            if (model->trap_valid || model->maintenance_fault || model->mmio_request)
                throw std::runtime_error("Unexpected bare CPU trap, maintenance failure or MMIO request");
            if (model->memory_word == 0xc0100001U) {
                const uint32_t clock = read(1);
                const uint32_t cycles_low = read(2);
                const uint64_t cycles = (static_cast<uint64_t>(read(3)) << 32) | cycles_low;
                const uint32_t retired_low = read(4);
                const uint64_t retired = (static_cast<uint64_t>(read(5)) << 32) | retired_low;
                const uint32_t output_size = read(6);
                if (read(7) || output_size == 0 || output_size > 4096)
                    throw std::runtime_error("Invalid RAM report length or overflow");
                for (unsigned byte_index = 0; byte_index < output_size; ++byte_index)
                    output.put(static_cast<char>((read(8 + byte_index / 4) >> (8 * (byte_index % 4))) & 255));
                result << "{\"clock_hz\":" << clock << ",\"cycles\":" << cycles
                       << ",\"retired\":" << retired << ",\"testbench_cycles\":" << cycle
                       << ",\"output_bytes\":" << output_size << "}\n";
                output.flush(); result.flush();
                if (!output || !result) throw std::runtime_error("Result write failed");
                model->final();
                std::cout << "PASS bare compiled RAM output cycles=" << cycle << " bytes=" << output_size << std::endl;
                return 0;
            }
            if (cycle % 100000000ULL == 0) std::cerr << "Bare RTL progress cycles=" << cycle << std::endl;
            if (Verilated::gotFinish()) throw std::runtime_error("Premature RTL finish");
        }
        throw std::runtime_error("Bare compiled cycle limit reached");
    } catch (const std::exception& error) {
        std::cerr << "FAIL " << error.what() << std::endl;
        return 1;
    }
}
