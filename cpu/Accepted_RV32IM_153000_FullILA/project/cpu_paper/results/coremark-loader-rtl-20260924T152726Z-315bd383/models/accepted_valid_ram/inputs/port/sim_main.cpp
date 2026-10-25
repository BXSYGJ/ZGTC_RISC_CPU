#include "Vrv32_observed_soc.h"
#include "verilated.h"
#include <cstdint>
#include <vector>
#include <algorithm>
#include <iterator>
#include <map>
#include <fstream>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
static vluint64_t sim_time = 0;
double sc_time_stamp() { return static_cast<double>(sim_time); }
int main(int argc, char **argv) {
    try {
        if (argc != 4) throw std::runtime_error("Expected UART output and cycle limit");
        std::string limit(argv[2]);
        if (limit.empty() || limit.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("Invalid cycle limit");
        uint64_t max_cycles = std::stoull(limit);
        if (!max_cycles || max_cycles > 1000000000000ULL) throw std::runtime_error("Cycle limit out of range");
        std::ofstream uart(argv[1], std::ios::binary);
        if (!uart) throw std::runtime_error("Cannot open UART log");
        Verilated::commandArgs(argc, argv);
        auto model = std::make_unique<Vrv32_observed_soc>();
        model->clk = 0; model->rst_n = 1; model->serial_rx = 1; model->gpio_input = 0;
        model->eval(); model->rst_n = 0; model->eval();
        auto tick = [&]() {
            sim_time += 5; model->clk = 1; model->eval();
            sim_time += 5; model->clk = 0; model->eval();
        };
        for (int i = 0; i < 4; ++i) tick();
        model->rst_n = 1; model->eval();
        bool previous_tx = true, receiving = false;
        uint64_t deadline = 0;
        int bit = -1;
        unsigned byte = 0;
        
        std::ifstream application(argv[3], std::ios::binary);
        if (!application) throw std::runtime_error("Cannot read application");
        std::vector<unsigned char> payload((std::istreambuf_iterator<char>(application)), std::istreambuf_iterator<char>());
        if (payload.empty() || payload.size()>45056) throw std::runtime_error("Invalid application length");
        std::vector<unsigned char> outgoing;
        outgoing.push_back('R');
        for (unsigned shift=0;shift<32;shift+=8) outgoing.push_back((payload.size()>>shift)&255);
        size_t payload_sent=std::min<size_t>(256,payload.size());
        outgoing.insert(outgoing.end(),payload.begin(),payload.begin()+payload_sent);
        size_t wire_index=0;
        uint64_t wire_start=10000;
        unsigned k_count=0, consumed_k=0;
        bool sent_g=false;
        std::string observed_uart;

        uint32_t sequence = 0, sp = 0, minimum_sp = 65536;
        uint64_t first_cycles = 0, first_retired = 0, observed_cycles = 0, observed_retired = 0;
        uint64_t redirects[7] = {}, eligible[7] = {}, request_stalls = 0, response_waits = 0, barriers = 0;
        bool outstanding=false, stalled=false;
        uint32_t stalled_address=0;
        std::map<uint64_t,uint64_t> redirect_profile;
        for (uint64_t cycle = 1; cycle <= max_cycles; ++cycle) {
            
            if (wire_index < outgoing.size() && cycle >= wire_start) {
                auto elapsed=cycle-wire_start;
                if (elapsed < 320) {
                    unsigned bit_index=elapsed/32;
                    model->serial_rx=bit_index==0 ? 0 : bit_index<=8 ? ((outgoing[wire_index]>>(bit_index-1))&1) : 1;
                } else {
                    model->serial_rx=1; ++wire_index; wire_start=cycle+32;
                }
            } else model->serial_rx=1;
            if (wire_index==outgoing.size() && payload_sent<payload.size() && k_count>consumed_k) {
                consumed_k=k_count;
                size_t count=std::min<size_t>(256,payload.size()-payload_sent);
                outgoing.insert(outgoing.end(),payload.begin()+payload_sent,payload.begin()+payload_sent+count);
                payload_sent+=count; wire_start=cycle+32;
            }
            if (!sent_g && observed_uart.find("ZGTC COREMARK READY send G; clock=153000000 Hz\n")!=std::string::npos) {
                if (wire_index!=outgoing.size() || payload_sent!=payload.size()) throw std::runtime_error("Early application READY");
                outgoing.push_back('G'); wire_start=cycle+32; sent_g=true;
            }

            uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;
            if (stalled && (!model->profile_req_valid || model->profile_req_address!=stalled_address))
                throw std::runtime_error("Instruction request changed under backpressure");
            stalled=model->profile_req_valid && !model->profile_req_ready;
            stalled_address=model->profile_req_address;
            if (model->profile_rsp_valid && model->profile_rsp_ready) {
                if (!outstanding) throw std::runtime_error("Instruction response without accepted request");
                outstanding=false;
            }
            if (model->profile_req_valid && model->profile_req_ready) {
                if (outstanding) throw std::runtime_error("Multiple outstanding instruction requests");
                outstanding=true;
            }
            uint64_t profile_key=(uint64_t(model->profile_target)<<8) | (model->profile_state<<3) | model->redirect_kind;
            bool retiring = model->retire_event;
            bool redirect = model->redirect_event, can_prime = model->redirect_eligible;
            unsigned kind = model->redirect_kind;
            bool request_stall = model->fetch_request_stall, response_wait = model->fetch_response_wait, barrier = model->frontend_barrier;
            if (model->wb_write && model->wb_rd == 2) sp = model->wb_data;
            tick();
            if (model->cycle_count != before_cycles + 1 || model->retired_count != before_retired + unsigned(retiring))
                throw std::runtime_error("Cycle or retirement observer disagreement");
            if (model->status_code == 0xc0100002U) {
                if (sp < minimum_sp) minimum_sp = sp;
                if (sp < 65536 - 16384 || sp > 65536) {
                    std::cerr << "STACK_BOUND sp=" << sp << " minimum=49152 maximum=65536\n";
                    throw std::runtime_error("Stack pointer exceeded reserved 16384-byte stack");
                }
            }
            if (model->snapshot_sequence != sequence) {
                if (model->snapshot_sequence != sequence + 1 || sequence >= 2)
                    throw std::runtime_error("Unexpected performance snapshot count");
                if (model->snapshot_cycles != before_cycles || model->snapshot_retired != before_retired)
                    throw std::runtime_error("Atomic snapshots differ from independent pre-edge counters");
                sequence = model->snapshot_sequence;
                if (sequence == 1) { first_cycles = before_cycles; first_retired = before_retired; }
                else { observed_cycles = before_cycles - first_cycles; observed_retired = before_retired - first_retired; }
            }
            // Include the first snapshot edge and exclude the second snapshot edge.
            if (sequence == 1) {
                if (redirect) {
                    if (kind >= 7) throw std::runtime_error("Invalid redirect category");
                    ++redirect_profile[profile_key];
                    ++redirects[kind]; if (can_prime) ++eligible[kind];
                }
                request_stalls += unsigned(request_stall); response_waits += unsigned(response_wait); barriers += unsigned(barrier);
            }
            bool tx = model->serial_tx;
            if (!receiving && previous_tx && !tx) {
                receiving = true; deadline = cycle + 16; bit = -1; byte = 0;
            }
            if (receiving && cycle == deadline) {
                if (bit == -1) { if (tx) throw std::runtime_error("Invalid UART start"); }
                else if (bit < 8) byte |= unsigned(tx) << bit;
                else {
                    if (!tx) throw std::runtime_error("Invalid UART stop");
                    uart.put(char(byte)); std::cout.put(char(byte)); observed_uart.push_back(char(byte)); if (byte==75 && !sent_g) ++k_count;
                    if (byte == 10) { uart.flush(); std::cout.flush(); }
                    receiving = false;
                }
                ++bit; deadline += 32;
            }
            previous_tx = tx;
            if (model->trap_valid || model->maintenance_fault) {
                std::cerr << "Trap PC=0x" << std::hex << model->trace_pc << " cause=" << model->trap_cause << std::dec << '\n';
                throw std::runtime_error("RTL trap or maintenance fault");
            }
            if (model->status_code == 0xc0100001U) {
                if (sequence != 2 || !observed_cycles || !observed_retired)
                    throw std::runtime_error("Missing measured snapshot interval");
                if (receiving) throw std::runtime_error("Incomplete UART output");
                uart.flush();
                if (!uart) throw std::runtime_error("UART log write failed");
                model->final();
                std::cout << "PASS RTL CoreMark smoke total_cycles=" << cycle << " total_retired=" << model->retired_count << '\n';
                std::cout << "OBSERVER cycles=" << observed_cycles << " retired=" << observed_retired << " minimum_sp=" << minimum_sp << '\n';
                std::cout << "EVENTS redirects=";
                for (int i=0; i<7; ++i) std::cout << (i ? "," : "") << redirects[i];
                std::cout << " eligible=";
                for (int i=0; i<7; ++i) std::cout << (i ? "," : "") << eligible[i];
                std::cout << " request_stalls=" << request_stalls << " response_waits=" << response_waits << " barrier_cycles=" << barriers << '\n';
                std::ofstream profile("redirect-profile.csv");
                profile << "target,fetch_state,kind,count\n";
                for (const auto &entry:redirect_profile)
                    profile << (entry.first>>8) << ',' << ((entry.first>>3)&31) << ',' << (entry.first&7) << ',' << entry.second << '\n';
                if (!profile) throw std::runtime_error("Profile write failed");
                return 0;
            }
            if ((model->status_code & 0xffff0000U) == 0xdead0000U) {
                std::cerr << "status=0x" << std::hex << model->status_code << std::dec << '\n';
                throw std::runtime_error("Firmware verification, assert, or runtime failure");
            }
            if (cycle % 100000000ULL == 0) std::cerr << "progress cycles=" << cycle << '\n';
            if (Verilated::gotFinish()) throw std::runtime_error("Unexpected RTL finish");
        }
        throw std::runtime_error("RTL cycle limit exceeded");
    } catch (const std::exception &e) {
        std::cerr << "FAIL " << e.what() << '\n'; return 1;
    }
}
