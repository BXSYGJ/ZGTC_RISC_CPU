"""Execute the firmware's actual integer animation/normalization on the host."""
from pathlib import Path
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
GCC = Path('H:/GG/msys64/ucrt64/bin/gcc.exe')


@pytest.mark.skipif(not GCC.exists(), reason='native Windows GCC unavailable')
def test_cpu_transition_and_history_proportions(tmp_path):
    source = tmp_path / 'transition.c'
    source.write_text(r'''
#include <assert.h>
#include "ui_transition.h"
int main(void) {
    ui_transition s = {{0}, {0}, {0}};
    uint8_t input[8] = {100,0,0,0,0,0,0,0}, output[8], previous = 0;
    unsigned i, step, sum;
    ui_retarget(&s, input);
    for (step=0; step<=25; ++step) {
        ui_step(&s, step, output);
        assert(output[0] == step*4 && output[0] >= previous);
        previous = output[0];
    }
    input[0]=0; input[4]=100;
    ui_retarget(&s,input);
    ui_step(&s,10,output);
    assert(output[0]==60 && output[4]==40);
    input[4]=0; input[7]=100;
    ui_retarget(&s,input);
    ui_step(&s,0,output);
    assert(output[0]==60 && output[4]==40 && output[7]==0);
    ui_step(&s,25,output);
    assert(output[0]==0 && output[4]==0 && output[7]==100);
    ui_step(&s,999,output);
    assert(output[7]==100);
    for (i=0;i<8;++i) input[i]=(uint8_t)(i+1);
    ui_proportions(input,output);
    for (sum=0,i=0;i<8;++i) sum+=output[i];
    assert(sum==100 && output[7]>output[0]);
    for (i=0;i<8;++i) input[i]=0;
    ui_proportions(input,output);
    for (i=0;i<8;++i) assert(output[i]==0);
    input[7]=99; ui_proportions(input,output);
    assert(output[7]==100);
    return 0;
}
''', encoding='ascii')
    exe = tmp_path / 'transition.exe'
    env = dict(os.environ)
    env['PATH'] = str(GCC.parent) + os.pathsep + env.get('PATH', '')
    subprocess.run([str(GCC), '-Wall', '-Wextra', '-Werror', '-I',
                    str(ROOT / 'sw/rv32'), str(source), '-o', str(exe)],
                   check=True, capture_output=True, text=True, env=env)
    subprocess.run([str(exe)], check=True, capture_output=True, text=True, env=env)
