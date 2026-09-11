#include "riscv_test.h"
RVTEST_RV32U
RVTEST_CODE_BEGIN
#if NEGATIVE_KIND == 1
    li TESTNUM, 99
    RVTEST_FAIL
#elif NEGATIVE_KIND == 2
    .word 0xffffffff
#else
994: j 994b
#endif
RVTEST_CODE_END
