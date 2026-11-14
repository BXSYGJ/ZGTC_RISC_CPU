#include "FreeRTOS.h"
#include "task.h"
#include "hal.h"

extern volatile uint32_t ulPortTickInterrupts, ulPortCriticalNesting;

static uint32_t ulMachineStatus(void) {
    uint32_t value;
    __asm__ volatile("csrr %0,mstatus" : "=r"(value));
    return value;
}

static uint32_t ulMachinePending(void) {
    uint32_t value;
    __asm__ volatile("csrr %0,mip" : "=r"(value));
    return value;
}

void vCriticalSelfTest(void) {
    const uint32_t period = configCPU_CLOCK_HZ / configTICK_RATE_HZ;
    TickType_t before, caught;
    uint32_t irq_before, irq_after, deferred, elapsed_ticks;
    uint64_t deadline, target, masked_now, catchup_limit, caught_now;
    configASSERT((ulMachineStatus() & 8u) != 0u);
    configASSERT(ulPortCriticalNesting == 0u);
    taskENTER_CRITICAL();
    taskENTER_CRITICAL();
    before = xTaskGetTickCount();
    irq_before = ulPortTickInterrupts;
    if (ulPortCriticalNesting != 2u || (ulMachineStatus() & 8u) != 0u)
        vApplicationFatal(0x44u, ulPortCriticalNesting);
    /* The timer's current absolute deadline anchors the expected tick count.
     * Cross three deadlines while nested, rather than delaying by host time. */
    deadline = ((uint64_t)MTIMECMP_HI << 32) | MTIMECMP_LO;
    target = deadline + 2u * period + period / 4u;
    do { masked_now = ullMachineTime(); } while (masked_now < target);
    deferred = 1u + (uint32_t)(masked_now - deadline) / period;
    if (deferred < 2u || xTaskGetTickCount() != before ||
        ulPortTickInterrupts != irq_before)
        vApplicationFatal(0x45u, xTaskGetTickCount() - before);
    if ((ulMachinePending() & 128u) == 0u)
        vApplicationFatal(0x46u, ulMachinePending());
    taskEXIT_CRITICAL();
    if (ulPortCriticalNesting != 1u || (ulMachineStatus() & 8u) != 0u ||
        xTaskGetTickCount() != before || ulPortTickInterrupts != irq_before ||
        (ulMachinePending() & 128u) == 0u)
        vApplicationFatal(0x47u, ulPortCriticalNesting);
    taskEXIT_CRITICAL();
    /* The priority-four monitor remains the running task while deferred ticks
     * arrive. All elapsed deadlines must be processed after the outer exit. */
    catchup_limit = masked_now + period;
    while (xTaskGetTickCount() - before < deferred) {
        if (ullMachineTime() > catchup_limit)
            vApplicationFatal(0x48u, xTaskGetTickCount() - before);
    }
    if (ulPortCriticalNesting != 0u || (ulMachineStatus() & 8u) == 0u)
        vApplicationFatal(0x4au, ulPortCriticalNesting);
    taskENTER_CRITICAL();
    caught = xTaskGetTickCount();
    irq_after = ulPortTickInterrupts;
    caught_now = ullMachineTime();
    elapsed_ticks = 1u + (uint32_t)(caught_now - deadline) / period;
    if (caught - before != elapsed_ticks || irq_after - irq_before != elapsed_ticks ||
        elapsed_ticks < deferred || (ulMachinePending() & 128u) != 0u)
        vApplicationFatal(0x49u, caught - before);
    taskEXIT_CRITICAL();
    vUartText("RTOS CRITICAL PASS deferred="); vUartDecimal(deferred);
    vUartText(" caught="); vUartDecimal(caught - before);
    vUartText(" depth=2 mie=0 pending=1\r\n");
}

