OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {
    ROM (rx) : ORIGIN = 0x00000000, LENGTH = 16K
    RAM (rw) : ORIGIN = 0x20000000, LENGTH = 16K
}
SECTIONS {
    .text : { KEEP(*(.text.start)) *(.text .text.*) } > ROM
    .rodata : { *(.rodata .rodata.*) *(.srodata .srodata.*) . = ALIGN(4); } > ROM
    .data : {
        . = ALIGN(4);
        __data_start = .;
        *(.data .data.*) *(.sdata .sdata.*)
        . = ALIGN(4);
        __data_end = .;
    } > RAM AT > ROM
    __data_load_start = LOADADDR(.data);
    .bss (NOLOAD) : {
        . = ALIGN(16);
        __bss_start = .;
        *(.bss .bss.*) *(.sbss .sbss.*) *(COMMON)
        . = ALIGN(16);
        __bss_end = .;
    } > RAM
    __stack_top = ORIGIN(RAM) + LENGTH(RAM);
    __global_pointer$ = __data_start + 0x400;
    ASSERT(__bss_end <= __stack_top - 1024, "RTOS static storage overlaps boot stack")
    /DISCARD/ : { *(.comment) *(.riscv.attributes) }
}
