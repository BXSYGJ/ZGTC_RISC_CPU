#include <stdint.h>

#define MMIO(off) (*(volatile uint32_t *)(0x80000000u + (off)))
#define WORDS 256u
#define DDR ((volatile uint32_t *)0x40000000u)
#define OBS ((volatile uint32_t *)0x41010000u)

static void putc_uart(char c) {
    while (!(MMIO(0x10) & 1u)) { }
    MMIO(0x0c) = (uint32_t)(unsigned char)c;
}
static void puts_uart(const char *s) { while (*s) putc_uart(*s++); }
static void hex32(uint32_t v) {
    for (int i=7; i>=0; --i) {
        uint32_t n=(v >> (i*4)) & 15u;
        putc_uart((char)(n < 10 ? '0'+n : 'A'+n-10));
    }
}
static uint32_t crc_word(uint32_t crc, uint32_t word) {
    for (unsigned b=0;b<4;++b) {
        crc ^= (word >> (b*8)) & 255u;
        for (unsigned k=0;k<8;++k) crc=(crc>>1) ^ (0xedb88320u & (0u-(crc&1u)));
    }
    return crc;
}
static uint32_t pattern(unsigned i) { return 0x5a39c671u ^ (i * 0x10204081u); }
static unsigned isa_test(void) {
    uint32_t r=0;
    __asm__ volatile("li %0, 5\n\tc.addi %0, 7" : "=&r"(r));
    if (r != 12) return 1;
    int32_t a=-12345,b=67,m=0,q=0,rem=0;
    __asm__ volatile("mul %0,%3,%4\n\tdiv %1,%3,%4\n\trem %2,%3,%4"
                     : "=&r"(m),"=&r"(q),"=&r"(rem) : "r"(a),"r"(b));
    if (m != -827115 || q != -184 || rem != -17) return 2;
    uint32_t hi=0,ua=0xfedcba98u,ub=0x12345678u;
    __asm__ volatile("mulhu %0,%1,%2" : "=&r"(hi) : "r"(ua),"r"(ub));
    if (hi != 0x121fa00au) return 3;
    __asm__ volatile("divu %0,%1,zero" : "=&r"(r) : "r"(ub));
    return r == 0xffffffffu ? 0 : 4;
}
int main(void) {
    unsigned seq=0;
    for (;;) {
        unsigned errors=isa_test();
        puts_uart("PACERV_SHARED BEGIN seq="); hex32(seq++); puts_uart(" RV32IMC 125MHz physical-DDR3\r\n");
        uint32_t begin=MMIO(0x18);
        while (!(MMIO(0x04)&32u)) {
            if ((MMIO(0x04)&64u) || (MMIO(0x18)-begin > 125000000u)) {
                puts_uart("PACERV_SHARED FAIL DDR_INIT_OR_BOOT_TEST\r\n");
                for (volatile unsigned wait=0;wait<1000000u;++wait) { }
                begin=MMIO(0x18);
            }
        }
        MMIO(0x24)=3u;
        uint32_t expected=0xffffffffu, observed=0xffffffffu;
        for (unsigned i=0;i<WORDS;++i) DDR[i]=pattern(i);
        volatile uint8_t *bytes=(volatile uint8_t *)DDR;
        volatile uint16_t *halves=(volatile uint16_t *)DDR;
        bytes[1]=0xa5u;
        halves[1]=0xc33cu;
        __asm__ volatile("fence iorw,iorw" ::: "memory");
        for (unsigned i=0;i<WORDS;++i) {
            uint32_t exp=(i==0) ? ((pattern(0)&255u)|0xc33ca500u) : pattern(i);
            uint32_t got=DDR[i];
            errors += got!=exp;
            expected=crc_word(expected,exp);
            observed=crc_word(observed,got);
        }
        begin=MMIO(0x18);
        while (!(MMIO(0x04)&2u) && !(MMIO(0x04)&4u)) {
            if (MMIO(0x18)-begin > 12500000u) { ++errors; break; }
        }
        errors += !!(MMIO(0x04)&4u);
        for (unsigned i=0;i<1024;++i) errors += OBS[i]!=(0x5a5a00ffu ^ i);
        errors += expected!=observed;
        puts_uart("ISA=RV32IMC MASK=SB_SH CRC="); hex32(observed ^ 0xffffffffu);
        puts_uart(" EXPECT="); hex32(expected ^ 0xffffffffu);
        puts_uart(" ERR="); hex32(errors); puts_uart("\r\n");
        puts_uart(errors ? "PACERV_SHARED FAIL\r\n" : "PACERV_SHARED PASS\r\n");
        MMIO(0x14)=errors ? 0xe1u : 0x5au;
        for (volatile unsigned wait=0;wait<1000000u;++wait) { }
    }
}
