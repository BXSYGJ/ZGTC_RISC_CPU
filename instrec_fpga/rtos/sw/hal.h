#ifndef INSTREC_RTOS_HAL_H
#define INSTREC_RTOS_HAL_H

#include <stdint.h>
#define MMIO(address) (*(volatile uint32_t *)(uintptr_t)(address))
#define SYS_ID      MMIO(0x80000000u)
#define SYS_STATUS  MMIO(0x80000004u)
#define SYS_PROBS   MMIO(0x80000008u)
#define UART_TX     MMIO(0x8000000cu)
#define UART_ST     MMIO(0x80000010u)
#define LED_REG     MMIO(0x80000014u)
#define DDR_STS     MMIO(0x80000020u)
#define NPU_CTRL    MMIO(0x80000024u)
#define NPU_CYCLES  MMIO(0x80000028u)
#define MTIME_LO    MMIO(0x80000030u)
#define MTIME_HI    MMIO(0x80000034u)
#define MTIMECMP_LO MMIO(0x80000038u)
#define MTIMECMP_HI MMIO(0x8000003cu)
#define ST_NPU_BUSY    (1u << 0)
#define ST_NPU_DONE    (1u << 1)
#define ST_NPU_TIMEOUT (1u << 2)
#define ST_PROBS       (1u << 3)
#define ST_DDR_OK      (1u << 5)
#define ST_DDR_ERR     (1u << 6)

uint64_t ullMachineTime(void);
void vMachineCompare(uint64_t value);
void vUartText(const char *text);
void vUartDecimal(uint32_t value);
void vUartHex(uint32_t value);
void vApplicationFatal(uint32_t code, uint32_t detail) __attribute__((noreturn));

#endif
