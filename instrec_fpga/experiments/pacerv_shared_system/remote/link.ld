ENTRY(_start)
MEMORY {
  ROM (rx) : ORIGIN = 0x00000000, LENGTH = 8K
  RAM (rwx) : ORIGIN = 0x20000000, LENGTH = 8K
}
SECTIONS {
  .text : { KEEP(*(.text.init)) *(.text*) *(.rodata*) . = ALIGN(4); } > ROM
  .data : { _data_start = .; *(.sdata*) *(.data*) . = ALIGN(4); _data_end = .; } > RAM AT > ROM
  _data_load = LOADADDR(.data);
  .bss (NOLOAD) : { _bss_start = .; *(.sbss*) *(.bss*) *(COMMON) . = ALIGN(4); _bss_end = .; } > RAM
  _stack_top = ORIGIN(RAM) + LENGTH(RAM);
  /DISCARD/ : { *(.comment*) *(.riscv.attributes*) *(.eh_frame*) }
}
