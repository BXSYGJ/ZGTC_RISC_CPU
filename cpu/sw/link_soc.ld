OUTPUT_ARCH(riscv)
ENTRY(_start)
/* With flash boot the first 4 KB of BRAM hold the bootloader, so the
   application is linked at 0x1000 and loaded there at runtime. */
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
    ASSERT(__heap_start < __stack_top - 4096, "Firmware leaves insufficient stack space")
}
