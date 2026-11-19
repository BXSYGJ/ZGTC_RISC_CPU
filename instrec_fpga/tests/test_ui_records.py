"""Exercise the production firmware ring, browsing and bookmark behavior."""
from pathlib import Path
import os
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[1]
GCC = Path('H:/GG/msys64/ucrt64/bin/gcc.exe')


@pytest.mark.skipif(not GCC.exists(), reason='native GCC unavailable')
def test_session_records(tmp_path):
    source = tmp_path / 'records.c'
    source.write_text(r'''
#include <assert.h>
#include "ui_records.h"
int main(void) {
    ui_records r = {0};
    uint32_t lo, hi, key = 0, i;
    ui_record_row(&r,0,&lo,&hi); assert(!hi && !lo);
    ui_record_keys(&r,0x10000,0); assert(!r.count);
    ui_record_add(&r,0x64000000,0,3,125,1);
    ui_record_row(&r,0,&lo,&hi);
    assert(lo == 0x02050001 && hi == (0x80000000u | 3u<<26 | 0x100u<<14));
    for(i=2;i<=70;i++) ui_record_add(&r,i,0,i&7,i*3,i);
    assert(r.count==64 && ui_record_at(&r,0)->sequence==70);
    assert(ui_record_at(&r,63)->sequence==7);
    ui_record_keys(&r,1,key); key=1; assert(r.page && r.selected==0);
    ui_record_keys(&r,0x101,key); key=0x101; assert(r.selected==1);
    ui_record_keys(&r,0x10101,key); key=0x10101;
    assert(ui_record_at(&r,1)->bookmark==1);
    ui_record_add(&r,71,0,0,213,71);
    assert(r.selected==2 && ui_record_at(&r,2)->sequence==69);
    assert(ui_record_at(&r,2)->bookmark==1);
    ui_record_keys(&r,0x10010101,key); key=0x10010101;
    assert(r.selected==0);
    for(i=72;i<150;i++) ui_record_add(&r,i,0,0,i*3,i);
    assert(r.selected==63 && ui_record_at(&r,63)->sequence==86);
    assert(!ui_record_at(&r,63)->bookmark);
    ui_record_keys(&r,key+0x10,key);
    assert(!r.count && !r.selected);
    ui_record_add(&r,0x12345678,0xabcdef01,7,3601,150);
    assert(ui_record_at(&r,0)->hi==0xabcdef01 && !ui_record_at(&r,0)->bookmark);
    ui_record_row(&r,0,&lo,&hi); assert((lo>>16)==0x6001);
    return 0;
}
''', encoding='ascii')
    exe = tmp_path / 'records.exe'
    env = dict(os.environ)
    env['PATH'] = str(GCC.parent) + os.pathsep + env.get('PATH', '')
    subprocess.run([str(GCC), '-Wall', '-Wextra', '-Werror', '-I',
                    str(ROOT / 'sw/rv32'), str(source), '-o', str(exe)],
                   check=True, capture_output=True, text=True, env=env)
    subprocess.run([str(exe)], check=True, capture_output=True, text=True, env=env)
