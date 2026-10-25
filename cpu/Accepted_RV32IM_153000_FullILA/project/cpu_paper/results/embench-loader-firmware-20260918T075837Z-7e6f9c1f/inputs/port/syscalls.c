#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#define REG(a) (*(volatile uint32_t *)(a))
extern char __heap_start, __stack_top;
static char *brk;
void *_sbrk(ptrdiff_t increment) {
    if (!brk) brk = &__heap_start;
    char *old = brk;
    if (increment < 0 || (uintptr_t)increment > (uintptr_t)(&__stack_top - 16384) - (uintptr_t)brk) {
        errno = ENOMEM;
        return (void *)-1;
    }
    brk += increment;
    return old;
}
__attribute__((noreturn)) void _exit(int code) {
    (void)code; REG(0x10000000u) = 0xeb0000fdu; for (;;) {}
}
__attribute__((noreturn)) void __assert_func(const char *file, int line, const char *func, const char *expr) {
    (void)file; (void)line; (void)func; (void)expr;
    REG(0x10000000u) = 0xeb0000fcu; for (;;) {}
}
