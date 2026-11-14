#ifndef INSTREC_PORTMACRO_H
#define INSTREC_PORTMACRO_H

#include <stdint.h>
#include <stddef.h>

#define portSTACK_TYPE uint32_t
#define portBASE_TYPE int32_t
typedef portSTACK_TYPE StackType_t;
typedef int32_t BaseType_t;
typedef uint32_t UBaseType_t;
typedef uint32_t TickType_t;
#define portMAX_DELAY UINT32_MAX
#define portTICK_TYPE_IS_ATOMIC 1
#define portSTACK_GROWTH (-1)
#define portBYTE_ALIGNMENT 16
#define portTICK_PERIOD_MS ((TickType_t)1000 / configTICK_RATE_HZ)
#define portCRITICAL_NESTING_IN_TCB 0
#define portDONT_DISCARD __attribute__((used))
#define portFORCE_INLINE inline __attribute__((always_inline))
#define portINLINE __inline
#define portNOP() __asm__ volatile("nop")
#define portMEMORY_BARRIER() __asm__ volatile("" ::: "memory")

void vPortEnterCritical(void);
void vPortExitCritical(void);
void vPortYield(void);
uint32_t ulPortSetInterruptMask(void);
void vPortClearInterruptMask(uint32_t previous);
void vPortYieldFromISR(BaseType_t required);

#define portYIELD() vPortYield()
#define portYIELD_WITHIN_API() portYIELD()
#define portDISABLE_INTERRUPTS() __asm__ volatile("csrci mstatus,8" ::: "memory")
#define portENABLE_INTERRUPTS() __asm__ volatile("csrsi mstatus,8" ::: "memory")
#define portENTER_CRITICAL() vPortEnterCritical()
#define portEXIT_CRITICAL() vPortExitCritical()
#define portSET_INTERRUPT_MASK_FROM_ISR() ulPortSetInterruptMask()
#define portCLEAR_INTERRUPT_MASK_FROM_ISR(previous) vPortClearInterruptMask(previous)
#define portEND_SWITCHING_ISR(required) vPortYieldFromISR(required)
#define portYIELD_FROM_ISR(required) portEND_SWITCHING_ISR(required)
#define portTASK_FUNCTION_PROTO(function, parameters) void function(void *parameters)
#define portTASK_FUNCTION(function, parameters) void function(void *parameters)
#define portASSERT_IF_INTERRUPT_PRIORITY_INVALID() do { } while (0)

#endif
