/* InstRec hardware remains the audio/Mel/NPU producer. FreeRTOS supervises
 * complete inference windows, passes immutable results through a queue, and
 * gives UART output a single task owner. No classifier runs on the CPU.
 */
#include "FreeRTOS.h"
#include "task.h"
#include "queue.h"
#include "hal.h"

#ifndef RTOS_TEST
#define RTOS_TEST 0
#endif

enum { RESULT_INFERENCE = 1, RESULT_TIMEOUT = 2, RESULT_HEARTBEAT = 3 };
typedef struct {
    uint32_t kind, sequence, tick, top1, last_class, last_pct, cycles;
} Result;

static StaticTask_t xControlTCB, xResultTCB, xHeartbeatTCB, xIdleTCB;
static StackType_t xControlStack[256], xResultStack[320], xHeartbeatStack[192];
static StackType_t xIdleStack[configMINIMAL_STACK_SIZE];
static StaticQueue_t xResultQueueStorage;
static uint8_t ucResultQueueBytes[8 * sizeof(Result)];
static QueueHandle_t xResultQueue;
volatile uint32_t ulApplicationResults, ulApplicationTimeouts;
volatile uint32_t ulApplicationQueueReceived;

void vApplicationGetIdleTaskMemory(StaticTask_t **tcb, StackType_t **stack,
                                  configSTACK_DEPTH_TYPE *depth) {
    *tcb = &xIdleTCB; *stack = xIdleStack; *depth = configMINIMAL_STACK_SIZE;
}

void vApplicationStackOverflowHook(TaskHandle_t task, char *name) {
    (void)task; (void)name;
    vApplicationFatal(0x20u, 0u);
}

void vApplicationAssert(unsigned line) { vApplicationFatal(0x21u, line); }

static void vSubmit(const Result *result) {
    if (xQueueSend(xResultQueue, result, portMAX_DELAY) != pdPASS)
        vApplicationFatal(0x22u, result->kind);
}

static void vRecognitionControl(void *argument) {
    uint32_t sequence = 0;
    (void)argument;
    /* Boot performs the DDR check before the scheduler. The normal window
     * producer and NPU native M1 owner retain their existing arbitration. */
    NPU_CTRL = 2u;
    NPU_CTRL = 1u;
    for (;;) {
        uint32_t status = SYS_STATUS;
        if ((status & ST_NPU_TIMEOUT) != 0u) {
            Result result = { RESULT_TIMEOUT, ++sequence, xTaskGetTickCount(),
                              0u, 0u, 0u, NPU_CYCLES };
            NPU_CTRL = 2u;
            vSubmit(&result);
            NPU_CTRL = 1u;
        } else if ((status & (ST_NPU_DONE | ST_PROBS | ST_NPU_BUSY)) ==
                   (ST_NPU_DONE | ST_PROBS)) {
            uint32_t probability = SYS_PROBS;
            Result result = { RESULT_INFERENCE, ++sequence, xTaskGetTickCount(),
                              (status >> 8) & 15u, probability & 15u,
                              (probability >> 8) & 255u, NPU_CYCLES };
            /* Copy every field before clearing: later hardware updates cannot
             * alter the message already handed to the consumer. */
            NPU_CTRL = 2u;
            vSubmit(&result);
            NPU_CTRL = 1u;
        }
        vTaskDelay(pdMS_TO_TICKS(1));
    }
}

static void vResultPublisher(void *argument) {
    Result result;
    (void)argument;
    for (;;) {
        configASSERT(xQueueReceive(xResultQueue, &result, portMAX_DELAY) == pdPASS);
        ++ulApplicationQueueReceived;
        if (result.kind == RESULT_INFERENCE) {
            vUartText("RTOS NPU top1="); vUartDecimal(result.top1);
            vUartText(" last_class="); vUartDecimal(result.last_class);
            vUartText(" last_p="); vUartDecimal(result.last_pct);
            vUartText(" c="); vUartDecimal(result.cycles);
            vUartText(" seq="); vUartDecimal(result.sequence);
            vUartText(" tick="); vUartDecimal(result.tick); vUartText("\r\n");
            ++ulApplicationResults;
            LED_REG = 0x80u | ((result.top1 & 7u) << 4);
        } else if (result.kind == RESULT_TIMEOUT) {
            vUartText("RTOS NPU TIMEOUT seq="); vUartDecimal(result.sequence);
            vUartText(" tick="); vUartDecimal(result.tick); vUartText("\r\n");
            ++ulApplicationTimeouts;
        } else {
            vUartText("RTOS HEARTBEAT tick="); vUartDecimal(result.tick);
            vUartText(" results="); vUartDecimal(ulApplicationResults);
            vUartText("\r\n");
        }
    }
}

static void vHeartbeat(void *argument) {
    TickType_t last = xTaskGetTickCount();
    (void)argument;
    for (;;) {
        Result result = { RESULT_HEARTBEAT, 0u, 0u, 0u, 0u, 0u, 0u };
        xTaskDelayUntil(&last, pdMS_TO_TICKS(100));
        result.tick = xTaskGetTickCount();
        vSubmit(&result);
    }
}

static void vBootChecks(void) {
    volatile uint32_t *words = (volatile uint32_t *)0x400ff000u;
    uint32_t i, misa;
    __asm__ volatile("csrr %0,misa" : "=r"(misa));
    if (SYS_ID != 0x52564331u || (misa & 0x1104u) != 0x1104u)
        vApplicationFatal(0x30u, misa);
    vUartText("RTOS IMC OK\r\n");
    while ((SYS_STATUS & (ST_DDR_OK | ST_DDR_ERR)) == 0u) { }
    if ((SYS_STATUS & ST_DDR_ERR) != 0u) vApplicationFatal(0x31u, DDR_STS);
    for (i = 0; i < 16u; ++i) words[i] = 0x13579bdfu ^ (i * 0x10204081u);
    for (i = 0; i < 16u; ++i)
        if (words[i] != (0x13579bdfu ^ (i * 0x10204081u)))
            vApplicationFatal(0x32u, i);
    if (MMIO(0x41300000u) != 0x5a5a00ffu) vApplicationFatal(0x33u, 0u);
    vUartText("RTOS DDR OK\r\n");
}

#if RTOS_TEST
extern volatile uint32_t ulPortTickInterrupts, ulPortYieldTraps;
volatile uint32_t ulRegisterProbeA, ulRegisterProbeB, ulRegisterProbeFailure;
static StaticTask_t xProbeATCB, xProbeBTCB, xMonitorTCB;
static StackType_t xProbeAStack[192], xProbeBStack[192], xMonitorStack[256];
static StaticQueue_t xEmptyQueueStorage;
static uint8_t ucEmptyQueueBytes[sizeof(uint32_t)];
static QueueHandle_t xEmptyQueue;
extern void vRegisterProbe(volatile uint32_t *counter, volatile uint32_t *failure,
                           uint32_t seed) __attribute__((noreturn));
static void vProbeA(void *argument) {
    (void)argument;
    vRegisterProbe(&ulRegisterProbeA, &ulRegisterProbeFailure, 0x1357u);
}
static void vProbeB(void *argument) {
    (void)argument;
    vRegisterProbe(&ulRegisterProbeB, &ulRegisterProbeFailure, 0x2468u);
}
void vCriticalSelfTest(void);
static void vTestMonitor(void *argument) {
    uint32_t dummy;
    TickType_t start = (vCriticalSelfTest(), xTaskGetTickCount());
    (void)argument;
    if (xQueueReceive(xEmptyQueue, &dummy, 2u) != errQUEUE_EMPTY ||
        xTaskGetTickCount() - start < 2u) vApplicationFatal(0x40u, 0u);
    if (xTaskGetTickCount() < 16u) vTaskDelay(16u - xTaskGetTickCount());
    if (ulApplicationResults < 2u || ulApplicationTimeouts < 1u)
        vApplicationFatal(0x41u, ulApplicationResults);
    if (ulRegisterProbeA < 20u || ulRegisterProbeB < 20u || ulRegisterProbeFailure)
        vApplicationFatal(0x42u, ulRegisterProbeFailure);
    if (ulPortTickInterrupts < 16u || ulPortYieldTraps == 0u)
        vApplicationFatal(0x43u, ulPortTickInterrupts);
    vUartText("RTOS TEST PASS ticks="); vUartDecimal(ulPortTickInterrupts);
    vUartText(" queues="); vUartDecimal(ulApplicationQueueReceived);
    vUartText(" preempt="); vUartDecimal(ulRegisterProbeA);
    vUartText(","); vUartDecimal(ulRegisterProbeB); vUartText("\r\n");
    LED_REG = 0xa5u;
    for (;;) vTaskDelay(1000u);
}
#endif

int main(void) {
    vUartText("\r\nRTOS BOOT hz=125000000 tick=1000\r\n");
    vBootChecks();
    xResultQueue = xQueueCreateStatic(8u, sizeof(Result), ucResultQueueBytes,
                                     &xResultQueueStorage);
    configASSERT(xResultQueue != NULL);
    configASSERT(xTaskCreateStatic(vRecognitionControl, "recognition", 256, NULL,
                                   3, xControlStack, &xControlTCB) != NULL);
    configASSERT(xTaskCreateStatic(vResultPublisher, "result_uart", 320, NULL,
                                   2, xResultStack, &xResultTCB) != NULL);
    configASSERT(xTaskCreateStatic(vHeartbeat, "heartbeat", 192, NULL,
                                   1, xHeartbeatStack, &xHeartbeatTCB) != NULL);
#if RTOS_TEST
    xEmptyQueue = xQueueCreateStatic(1u, sizeof(uint32_t), ucEmptyQueueBytes,
                                    &xEmptyQueueStorage);
    configASSERT(xEmptyQueue != NULL);
    configASSERT(xTaskCreateStatic(vProbeA, "register_A", 192, NULL, 1,
                                   xProbeAStack, &xProbeATCB) != NULL);
    configASSERT(xTaskCreateStatic(vProbeB, "register_B", 192, NULL, 1,
                                   xProbeBStack, &xProbeBTCB) != NULL);
    configASSERT(xTaskCreateStatic(vTestMonitor, "test_monitor", 256, NULL, 4,
                                   xMonitorStack, &xMonitorTCB) != NULL);
#endif
    vTaskStartScheduler();
    vApplicationFatal(0x50u, 0u);
}
