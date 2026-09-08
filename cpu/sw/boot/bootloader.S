# Flash bootloader for the RV32 SoC on PG2L200H (MES2L676-200HP).
#
# Resides in the first 4 KiB of BRAM and is baked into the bitstream once.
# On reset the CPU starts here (reset vector 0x0). Order of operations:
#   1. look for a valid image in the user SPI flash (U9)
#   2. if found, copy it to BRAM at 0x1000 and launch it
#   3. otherwise fall into UART recovery mode (115200 8N1)
#
# Flash image layout (all integers little-endian):
#   0x00  4 bytes  magic 'R','F','C','P'
#   0x04  4 bytes  payload length in bytes
#   0x08  ...      payload, loaded to BRAM 0x1000
#
# UART recovery commands:
#   W <u32 length> <image bytes ...>  write image to flash, then boot it
#   R <u32 length> <image bytes ...>  load image straight to RAM and run it
#   B                                 boot from flash
#   E                                 erase flash sector 0
#
# MMIO: UART_DATA 0x10000100, UART_STATUS 0x10000104,
#       SPI_CTRL 0x10000500, SPI_TX 0x10000504, SPI_RX 0x10000508, SPI_STAT 0x1000050c

_start:
    li      sp, 0x0FE0              # stack inside the bootloader region
    li      s1, 0x10000000          # MMIO base
    la      a0, banner
    call    uart_puts
    call    boot_from_flash         # returns only when no valid image exists
    j       recovery

# ---------------------------------------------------------------- uart ----
# uart_putc(a0)
uart_putc:
1:  lw      t0, 0x104(s1)           # UART_STATUS
    andi    t0, t0, 1               # tx_fifo_ready
    beqz    t0, 1b
    sw      a0, 0x100(s1)           # UART_DATA
    ret

# uart_getc() -> a0
uart_getc:
1:  lw      t0, 0x104(s1)
    andi    t0, t0, 4               # rx_fifo_valid
    beqz    t0, 1b
    lw      a0, 0x100(s1)
    andi    a0, a0, 0xff
    ret

# uart_puts(a0 = address of nul-terminated string)
uart_puts:
    addi    sp, sp, -16
    sw      ra, 12(sp)
    sw      s2, 8(sp)
    mv      s2, a0
1:  lbu     a0, 0(s2)
    beqz    a0, 2f
    call    uart_putc
    addi    s2, s2, 1
    j       1b
2:  lw      s2, 8(sp)
    lw      ra, 12(sp)
    addi    sp, sp, 16
    ret

# get_u32() -> a0 (four bytes from UART, least significant first)
get_u32:
    addi    sp, sp, -8
    sw      ra, 4(sp)
    call    uart_getc
    mv      t2, a0
    call    uart_getc
    mv      t3, a0
    call    uart_getc
    mv      t4, a0
    call    uart_getc
    mv      t5, a0
    slli    t3, t3, 8
    slli    t4, t4, 16
    slli    t5, t5, 24
    or      a0, t2, t3
    or      a0, a0, t4
    or      a0, a0, t5
    lw      ra, 4(sp)
    addi    sp, sp, 8
    ret

# uart_recv_to_ram(a0 = dst, a1 = count)
uart_recv_to_ram:
    addi    sp, sp, -16
    sw      ra, 12(sp)
    sw      s2, 8(sp)
    sw      s3, 4(sp)
    mv      s2, a0
    mv      s3, a1
1:  beqz    s3, 2f
    call    uart_getc
    sb      a0, 0(s2)
    addi    s2, s2, 1
    addi    s3, s3, -1
    j       1b
2:  lw      s3, 4(sp)
    lw      s2, 8(sp)
    lw      ra, 12(sp)
    addi    sp, sp, 16
    ret

# ----------------------------------------------------------------- spi ----
spi_select:
    li      t0, 1
    sw      t0, 0x500(s1)           # SPI_CTRL: 1 = selected
    ret

spi_deselect:
    sw      x0, 0x500(s1)
    ret

# spi_xfer(a0 = byte out) -> a0 (byte in)
spi_xfer:
    sw      a0, 0x504(s1)           # SPI_TX starts an 8-bit shift
1:  lw      t0, 0x50c(s1)           # SPI_STAT
    andi    t0, t0, 1               # busy
    bnez    t0, 1b
    lw      a0, 0x508(s1)           # SPI_RX
    andi    a0, a0, 0xff
    ret

# --------------------------------------------------------------- flash ----
flash_wait_ready:
    addi    sp, sp, -8
    sw      ra, 4(sp)
    call    spi_select
    li      a0, 0x05                # Read Status Register-1
    call    spi_xfer
1:  li      a0, 0xff
    call    spi_xfer
    andi    t0, a0, 1               # WIP
    bnez    t0, 1b
    call    spi_deselect
    lw      ra, 4(sp)
    addi    sp, sp, 8
    ret

flash_wren:
    addi    sp, sp, -8
    sw      ra, 4(sp)
    call    spi_select
    li      a0, 0x06                # Write Enable
    call    spi_xfer
    call    spi_deselect
    lw      ra, 4(sp)
    addi    sp, sp, 8
    ret

flash_erase_sector0:
    addi    sp, sp, -8
    sw      ra, 4(sp)
    call    flash_wren
    call    spi_select
    li      a0, 0x20                # Sector Erase (4 KiB)
    call    spi_xfer
    li      a0, 0
    call    spi_xfer
    li      a0, 0
    call    spi_xfer
    li      a0, 0
    call    spi_xfer
    call    spi_deselect
    call    flash_wait_ready
    lw      ra, 4(sp)
    addi    sp, sp, 8
    ret

# flash_read(a0 = flash address, a1 = dst, a2 = count)
flash_read:
    addi    sp, sp, -16
    sw      ra, 12(sp)
    sw      s2, 8(sp)
    sw      s3, 4(sp)
    sw      s4, 0(sp)
    mv      s2, a0
    mv      s3, a1
    mv      s4, a2
    call    spi_select
    li      a0, 0x03                # Read Data
    call    spi_xfer
    srli    a0, s2, 16
    andi    a0, a0, 0xff
    call    spi_xfer
    srli    a0, s2, 8
    andi    a0, a0, 0xff
    call    spi_xfer
    mv      a0, s2
    andi    a0, a0, 0xff
    call    spi_xfer
1:  beqz    s4, 2f
    li      a0, 0xff
    call    spi_xfer
    sb      a0, 0(s3)
    addi    s3, s3, 1
    addi    s4, s4, -1
    j       1b
2:  call    spi_deselect
    lw      s4, 0(sp)
    lw      s3, 4(sp)
    lw      s2, 8(sp)
    lw      ra, 12(sp)
    addi    sp, sp, 16
    ret

# flash_page_program(a0 = flash address, a1 = src, a2 = count <= 256, page aligned)
flash_page_program:
    addi    sp, sp, -20
    sw      ra, 16(sp)
    sw      s2, 12(sp)
    sw      s3, 8(sp)
    sw      s4, 4(sp)
    mv      s2, a0
    mv      s3, a1
    mv      s4, a2
    call    flash_wren
    call    spi_select
    li      a0, 0x02                # Page Program
    call    spi_xfer
    srli    a0, s2, 16
    andi    a0, a0, 0xff
    call    spi_xfer
    srli    a0, s2, 8
    andi    a0, a0, 0xff
    call    spi_xfer
    mv      a0, s2
    andi    a0, a0, 0xff
    call    spi_xfer
1:  beqz    s4, 2f
    lbu     a0, 0(s3)
    call    spi_xfer
    addi    s3, s3, 1
    addi    s4, s4, -1
    j       1b
2:  call    spi_deselect
    call    flash_wait_ready
    lw      s4, 4(sp)
    lw      s3, 8(sp)
    lw      s2, 12(sp)
    lw      ra, 16(sp)
    addi    sp, sp, 20
    ret

# ---------------------------------------------------------------- boot ----
# boot_from_flash: returns if no valid image is present, otherwise never returns
boot_from_flash:
    addi    sp, sp, -16
    sw      ra, 12(sp)
    sw      s5, 8(sp)
    sw      s6, 4(sp)
    li      a0, 0                   # flash address 0
    la      a1, header
    li      a2, 8
    call    flash_read
    la      t1, header
    lw      s5, 0(t1)               # magic
    lw      s6, 4(t1)               # payload length
    li      t0, 0x50434652          # 'RFCP' as a little-endian word
    bne     s5, t0, boot_from_flash_invalid
    beqz    s6, boot_from_flash_invalid
    li      t0, 0xF000              # payload must fit below the 64 KiB BRAM top
    bgeu    s6, t0, boot_from_flash_invalid
    li      a0, 8                   # payload starts right after the header
    li      a1, 0x1000              # APP_BASE
    mv      a2, s6
    call    flash_read
    call    launch
boot_from_flash_invalid:
    lw      s6, 4(sp)
    lw      s5, 8(sp)
    lw      ra, 12(sp)
    addi    sp, sp, 16
    ret

# launch: flush caches and jump to the application
launch:
    fence.i                         # write back d-cache and invalidate i-cache
    li      t0, 0x1000              # APP_BASE
    jr      t0

# ------------------------------------------------------------ recovery ----
recovery:
    la      a0, recovery_msg
    call    uart_puts
recovery_loop:
    call    uart_getc
    mv      t0, a0
    li      t1, 'W'
    beq     t0, t1, cmd_write_flash
    li      t1, 'R'
    beq     t0, t1, cmd_run_ram
    li      t1, 'B'
    beq     t0, t1, cmd_boot_flash
    li      t1, 'E'
    beq     t0, t1, cmd_erase
    j       recovery_loop

# R: stream an image into RAM and run it (no flash write)
cmd_run_ram:
    call    get_u32
    mv      s7, a0
    li      t0, 0xF000
    bgeu    s7, t0, recovery_loop
    li      a0, 0x1000
    mv      a1, s7
    call    uart_recv_to_ram
    la      a0, ok_msg
    call    uart_puts
    call    launch

# W: stream an image into RAM, flash it, then boot from flash
cmd_write_flash:
    call    get_u32
    mv      s7, a0
    li      t0, 0xF000
    bgeu    s7, t0, recovery_loop
    li      a0, 0x1000              # stage the image in RAM first
    mv      a1, s7
    call    uart_recv_to_ram
    call    flash_erase_sector0
    li      s8, 0                   # flash offset
    li      s9, 0x1000              # source pointer
    mv      s10, s7                 # bytes remaining
program_loop:
    beqz    s10, program_done
    li      t0, 256
    andi    t1, s8, 0xff
    sub     t0, t0, t1              # bytes left inside the current page
    mv      t2, s10
    bgeu    t2, t0, program_keep    # remaining >= page space -> use page space
    mv      t0, t2
program_keep:
    mv      a0, s8
    mv      a1, s9
    mv      a2, t0
    addi    sp, sp, -16
    sw      s8, 0(sp)
    sw      s9, 4(sp)
    sw      s10, 8(sp)
    call    flash_page_program
    lw      s8, 0(sp)
    lw      s9, 4(sp)
    lw      s10, 8(sp)
    addi    sp, sp, 16
    add     s8, s8, t0
    add     s9, s9, t0
    sub     s10, s10, t0
    j       program_loop
program_done:
    la      a0, ok_msg
    call    uart_puts
    call    boot_from_flash         # launch what we just programmed
    j       recovery

cmd_boot_flash:
    call    boot_from_flash
    j       recovery

cmd_erase:
    call    flash_erase_sector0
    la      a0, ok_msg
    call    uart_puts
    j       recovery

# ---------------------------------------------------------------- data ----
banner:
    .asciz  "ZBOOT\r\n"
recovery_msg:
    .asciz  "REC W/R/B/E\r\n"
ok_msg:
    .asciz  "OK\r\n"
    .align  4
header:
    .word   0
    .word   0
