OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0, LENGTH = 16K }
SECTIONS {
    .text : { *(.text .text.*) } > RAM
    .rodata : { *(.rodata .rodata.*) } > RAM
    .data : { *(.data .data.*) } > RAM
    .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) } > RAM
    ASSERT(. < 0x2000, "Self-test code overlaps its test data")
}
