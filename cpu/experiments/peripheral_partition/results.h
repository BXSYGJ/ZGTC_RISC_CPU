#ifndef RV32_BARE_RESULTS_H
#define RV32_BARE_RESULTS_H
#include "../../sw/platform.h"
#define RESULT_OUTPUT_CAPACITY 4096u
struct benchmark_result {
    u32 state;
    u32 clock_hz;
    unsigned long long cycles;
    unsigned long long retired;
    u32 output_length;
    u32 output_overflow;
    unsigned char output[RESULT_OUTPUT_CAPACITY];
};
extern volatile struct benchmark_result benchmark_result;
#endif
