/* Machine-mode RV32IMC port for the frozen PaceRV H3 execution core.
 * The 144-byte context has x1..x31 at their architectural index * 4,
 * mepc at 128, mstatus at 132, critical depth at 136, and a pad at 140.
 * Only machine timer and machine ECALL traps enter the scheduler.
 */
#include "FreeRTOS.h"
#include "task.h"
#include "hal.h"

volatile uint32_t ulPortCriticalNesting;
volatile uint32_t ulPortTickInterrupts;
volatile uint32_t ulPortYieldTraps;
static uint64_t ullNextTick;
uint32_t xPortISRStack[256] __attribute__((aligned(16)));
extern void xPortStartFirstTask(void) __attribute__((noreturn));
extern void vPortTrapEntry(void);

static void vTaskReturned(void) { vApplicationFatal(0x10u, 0u); }

StackType_t *pxPortInitialiseStack(StackType_t *top, TaskFunction_t entry, void *argument) {
    uintptr_t aligned = ((uintptr_t)(top + 1)) & ~(uintptr_t)15u;
    StackType_t *frame = (StackType_t *)(aligned - 144u);
    uint32_t gp;
    unsigned i;
    __asm__ volatile("mv %0,gp" : "=r"(gp));
    for (i = 0; i < 36u; ++i) frame[i] = 0u;
    frame[1] = (StackType_t)(uintptr_t)vTaskReturned;
    frame[2] = (StackType_t)aligned;
    frame[3] = gp;
    frame[10] = (StackType_t)(uintptr_t)argument;
    frame[32] = (StackType_t)(uintptr_t)entry;
    frame[33] = 0x1880u; /* MPP=M, MPIE=1; mret enables interrupts. */
    return frame;
}

BaseType_t xPortStartScheduler(void) {
    __asm__ volatile("csrci mstatus,8" ::: "memory");
    __asm__ volatile("csrw mtvec,%0" :: "r"(vPortTrapEntry) : "memory");
    ulPortCriticalNesting = 0u;
    ullNextTick = ullMachineTime() + configCPU_CLOCK_HZ / configTICK_RATE_HZ;
    vMachineCompare(ullNextTick);
    __asm__ volatile("li t0,128\ncsrs mie,t0" ::: "t0", "memory");
    xPortStartFirstTask();
}

void vPortEndScheduler(void) { vApplicationFatal(0x11u, 0u); }

void vPortEnterCritical(void) {
    portDISABLE_INTERRUPTS();
    ++ulPortCriticalNesting;
    portMEMORY_BARRIER();
}

void vPortExitCritical(void) {
    configASSERT(ulPortCriticalNesting != 0u);
    --ulPortCriticalNesting;
    if (ulPortCriticalNesting == 0u) portENABLE_INTERRUPTS();
}

uint32_t ulPortSetInterruptMask(void) {
    uint32_t previous;
    __asm__ volatile("csrrci %0,mstatus,8" : "=r"(previous) :: "memory");
    return previous;
}

void vPortClearInterruptMask(uint32_t previous) {
    if ((previous & 8u) != 0u) portENABLE_INTERRUPTS();
}

void vPortYieldFromISR(BaseType_t required) {
    /* The trap prologue has already saved the interrupted task. */
    if (required != pdFALSE) vTaskSwitchContext();
}

void vPortTrapDispatch(uint32_t *frame) {
    uint32_t cause;
    __asm__ volatile("csrr %0,mcause" : "=r"(cause));
    if (cause == 0x80000007u) {
        ullNextTick += configCPU_CLOCK_HZ / configTICK_RATE_HZ;
        vMachineCompare(ullNextTick);
        ++ulPortTickInterrupts;
        if (xTaskIncrementTick() != pdFALSE) vTaskSwitchContext();
    } else if (cause == 11u) {
        frame[32] += 4u; /* ECALL is always 32 bits, including RV32C code. */
        ++ulPortYieldTraps;
        vTaskSwitchContext();
    } else {
        vApplicationFatal(cause, frame[32]);
    }
}
