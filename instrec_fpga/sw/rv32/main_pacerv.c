/* PaceRV RV32IMC boot checks, followed by the existing audio-control program. */
#define main legacy_control_main
#include "main.c"
#undef main

#define APP_TEST_BASE 0x400ff000u
#define SHARED_SELFTEST_BASE 0x41300000u

static uint32_t crc_word(uint32_t crc, uint32_t word) {
    unsigned bit;
    for (bit = 0; bit < 32; ++bit) {
        uint32_t mix = (crc ^ word) & 1u;
        crc >>= 1;
        if (mix) crc ^= 0xedb88320u;
        word >>= 1;
    }
    return crc;
}

static uint32_t pacerv_isa_test(void) {
    uint32_t a = 0x80000003u, b = 7u, value;
    uint32_t misa;
    __asm__ volatile ("csrr %0, misa" : "=r"(misa));
    if ((misa & 0x1104u) != 0x1104u) return 1u;
    __asm__ volatile ("mul %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 0x80000015u) return 2u;
    __asm__ volatile ("mulh %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 0xfffffffcu) return 3u;
    __asm__ volatile ("mulhu %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 3u) return 4u;
    __asm__ volatile ("mulhsu %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 0xfffffffcu) return 5u;
    a = (uint32_t)-100;
    __asm__ volatile ("div %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != (uint32_t)-14) return 6u;
    __asm__ volatile ("rem %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != (uint32_t)-2) return 7u;
    a = 100u;
    __asm__ volatile ("divu %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 14u) return 8u;
    __asm__ volatile ("remu %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 2u) return 9u;
    b = 0u;
    __asm__ volatile ("div %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 0xffffffffu) return 10u;
    __asm__ volatile ("rem %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 100u) return 11u;
    a = 0x80000000u; b = 0xffffffffu;
    __asm__ volatile ("div %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 0x80000000u) return 12u;
    __asm__ volatile ("rem %0,%1,%2" : "=r"(value) : "r"(a), "r"(b));
    if (value != 0u) return 13u;
    __asm__ volatile (".option push\n.option rvc\nc.li %0,7\nc.addi %0,5\n.option pop"
                      : "=r"(value));
    if (value != 12u) return 14u;
    __asm__ volatile (".option push\n.balign 4\n.option rvc\nc.nop\n"
                      ".option norvc\naddi %0,zero,17\n.option rvc\nc.nop\n.option pop"
                      : "=r"(value));
    if (value != 17u) return 15u;
    __asm__ volatile ("fence.i" ::: "memory");
    return 0u;
}

static uint32_t pacerv_ddr_test(uint32_t *crc_out) {
    volatile uint32_t *words = (volatile uint32_t *)APP_TEST_BASE;
    volatile uint8_t *bytes = (volatile uint8_t *)APP_TEST_BASE;
    volatile uint16_t *halves = (volatile uint16_t *)APP_TEST_BASE;
    uint32_t i, expected_crc = 0xffffffffu, got_crc = 0xffffffffu;
    for (i = 0; i < 64u; ++i) words[i] = 0x13579bdfu ^ (i * 0x10204081u);
    for (i = 0; i < 64u; ++i) {
        uint32_t expected = 0x13579bdfu ^ (i * 0x10204081u);
        expected_crc = crc_word(expected_crc, expected);
        got_crc = crc_word(got_crc, words[i]);
        if (words[i] != expected) return 1u;
    }
    if (got_crc != expected_crc) return 2u;
    for (i = 0; i < 8u; ++i) words[i] = 0xa5a5a5a5u;
    for (i = 0; i < 32u; ++i) {
        bytes[i] = (uint8_t)(i * 7u + 3u);
        if (bytes[i] != (uint8_t)(i * 7u + 3u)) return 3u;
    }
    for (i = 0; i < 32u; ++i)
        if (bytes[i] != (uint8_t)(i * 7u + 3u)) return 4u;
    for (i = 0; i < 16u; ++i) halves[i] = (uint16_t)(0x8100u + i);
    for (i = 0; i < 16u; ++i)
        if (halves[i] != (uint16_t)(0x8100u + i)) return 5u;
    MMIO(0x400ffffcu) = 0xc001c0deu;
    if (MMIO(0x400ffffcu) != 0xc001c0deu) return 6u;
    /* The boot self-test owns the source; this is a read-only CPU alias. */
    if (MMIO(SHARED_SELFTEST_BASE) != 0x5a5a00ffu) return 7u;
    *crc_out = got_crc ^ 0xffffffffu;
    return 0u;
}

int main(void) {
    uint32_t rc, crc = 0;
    puts_("\r\nPACERV RV32IMC SHARED SYSTEM\r\n");
    rc = pacerv_isa_test();
    puts_(rc ? "PACERV IMC FAIL " : "PACERV IMC OK ");
    putdec(rc); puts_("\r\n");
    if (rc) for (;;) { }
    while ((SYS_STATUS & (ST_DDR_OK | ST_DDR_ERR)) == 0u) { }
    if (SYS_STATUS & ST_DDR_ERR) {
        puts_("PACERV DDR ERROR\r\n");
        for (;;) { }
    }
    rc = pacerv_ddr_test(&crc);
    puts_(rc ? "PACERV DDR FAIL " : "PACERV DDR OK ");
    putdec(rc); puts_(" CRC="); puthex(crc); puts_("\r\n");
    if (rc) for (;;) { }
    return legacy_control_main();
}
