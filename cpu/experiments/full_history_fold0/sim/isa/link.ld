OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0, LENGTH = 64K }
SECTIONS {
    .text : { *(.text.init) *(.text .text.*) } > RAM
    .rodata : { *(.rodata .rodata.*) } > RAM
    .data : { *(.data .data.*) } > RAM
    .bss (NOLOAD) : { *(.bss .bss.*) *(COMMON) } > RAM
    ASSERT(. <= 0x10000, "ISA test exceeds RAM")
}
