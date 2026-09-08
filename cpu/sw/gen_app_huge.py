#!/usr/bin/env python3
"""生成 >17KB 的大文件测试固件源 app_huge.c。

用确定性 xorshift32 伪随机序列生成 ``static const unsigned int big_table[N]``，
N 默认为 8192（数据约 32KB，加上代码约 33KB），并计算这些常量的和 mod 2^32
作为期望校验和，把 N 与期望校验和正确写进生成的 C 源，使板端求和自检自洽。

运行：
    python gen_app_huge.py [N] [seed]

生成的 C 源结构复刻 app_big.c 的 MMIO/UART 输出与 main 求和逻辑，
唯一区别是数组长度 N 与期望校验和。
"""
import os
import sys

N = int(sys.argv[1]) if len(sys.argv) > 1 else 8192
SEED = int(sys.argv[2], 0) if len(sys.argv) > 2 else 0x12345678

MASK = 0xFFFFFFFF


def xorshift32(x):
    """32 位 xorshift，返回 [0, 2^32) 内的下一个值（纯确定性）。"""
    x &= MASK
    x ^= (x << 13) & MASK
    x &= MASK
    x ^= x >> 17
    x ^= (x << 5) & MASK
    x &= MASK
    return x


def gen_table(n, seed):
    if seed == 0:
        # xorshift32 在 0 状态会卡死，换成任意非零常量即可
        seed = 0x9E3779B1
    tbl = []
    x = seed
    for _ in range(n):
        x = xorshift32(x)
        tbl.append(x)
    return tbl


def build_source(n, expect_sum, values):
    """生成与 app_big.c 同构的 C 源。"""
    lines = []
    lines.append("static const unsigned int big_table[%d] = {" % n)
    per_line = 4
    for i in range(0, n, per_line):
        chunk = values[i:i + per_line]
        row = ",".join("0x%08xu" % v for v in chunk)
        lines.append(row + ",")
    lines.append("};")
    header = (
        "#define MMIO_BASE 0x10000000u\n"
        "#define REG32(a) (*(volatile unsigned int *)(MMIO_BASE + (a)))\n"
        "#define UART_DATA   REG32(0x100u)\n"
        "#define UART_STATUS REG32(0x104u)\n"
        "#define GPIO_OUTPUT REG32(0x200u)\n"
        "#define TX_READY 0x1u\n"
        "static void putc(char c) { while ((UART_STATUS & TX_READY) == 0u) { } UART_DATA = (unsigned int)(unsigned char)c; }\n"
        "static void puts(const char *text) { while (*text != 0) putc(*text++); }\n"
        "static void nl(void) { putc((char)10); }\n"
        "static void puthex(unsigned int v)\n"
        "{\n"
        "    static const char h[16] = { '0','1','2','3','4','5','6','7','8','9','a','b','c','d','e','f' };\n"
        "    char b[9];\n"
        "    int i;\n"
        "    for (i = 7; i >= 0; i--) { b[i] = h[v & 15u]; v >>= 4; }\n"
        "    b[8] = 0;\n"
        "    puts(b);\n"
        "}\n"
        "void trap_handler(void) { for (;;) { } }\n"
        "int main(void)\n"
        "{\n"
        "    volatile const unsigned int *t = big_table;\n"
        "    volatile unsigned int sink = 0u;\n"
        "    unsigned int sum = 0u;\n"
        "    unsigned int i, d;\n"
        "    for (i = 0u; i < %du; i++) sum = (sum + t[i]) & 0xffffffffu;\n"
        "    GPIO_OUTPUT = (unsigned char)(sum >> 8);\n"
        "    for (;;) {\n"
        "        puts(\"BIG %d\"); nl();\n"
        "        puthex(sum); nl();\n"
        "        if (sum == 0x%08xu) puts(\"OK\"); else puts(\"FAIL\");\n"
        "        nl();\n"
        "        for (d = 0u; d < 3000000u; d++) sink = (sink + d) & 0xffffffffu;\n"
        "    }\n"
        "}\n" % (n, n, expect_sum)
    )
    body = "\n".join(lines)
    return body + "\n" + header


def main():
    values = gen_table(N, SEED)
    total = 0
    for v in values:
        total = (total + v) & MASK
    expect = total
    src = build_source(N, expect, values)
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_huge.c")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    size_hint = N * 4
    print("N=%d seed=0x%08x expect_sum=0x%08x data_bytes=%d -> %s"
          % (N, SEED & MASK, expect, size_hint, out_path), flush=True)


if __name__ == "__main__":
    main()