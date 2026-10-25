OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY { RAM (rwx) : ORIGIN = 0x1000, LENGTH = 60K }
SECTIONS {
    .text : { KEEP(*(.text.start)) *(.text .text.*) } > RAM
    .rodata : { *(.rodata .rodata.*) } > RAM
    .data : { *(.data .data.*) *(.sdata .sdata.*) } > RAM
    . = ALIGN(4);
    __bss_start = .;
    .bss (NOLOAD) : { *(.bss .bss.*) *(.sbss .sbss.*) *(COMMON) . = ALIGN(4); } > RAM
    __bss_end = .;
    __heap_start = .;
    __stack_top = ORIGIN(RAM) + LENGTH(RAM);
    __global_pointer$ = __bss_start + 0x800;
    ASSERT(__heap_start < __stack_top - 16384, "Firmware leaves insufficient stack space")
}
