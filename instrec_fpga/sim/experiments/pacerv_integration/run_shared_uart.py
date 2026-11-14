"""Test production UART priority and serialized bytes with four simultaneous sources."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--label',default='current')
    args=parser.parse_args()
    if not args.label.replace('_','').replace('-','').isalnum():
        raise ValueError('Label must contain letters, digits, underscores or hyphens')
    out=ROOT/'build/pacerv_shared_system/uart'/args.label
    out.mkdir(parents=True,exist_ok=False)
    sources=[HERE/'tb_shared_uart.sv',ROOT/'src/ctrl/instrec_top.v',ROOT/'src/ctrl/uart_tx.v']
    idf=ROOT/'ipcore/ddr3_test/ddr3_test.idf'
    parameters={p.findtext('name'):p.findtext('value') for p in ET.parse(idf).findall('./param_list/param')}
    hz=round(float(parameters['ACTUAL_RATE'])*1e6/8)
    baud=round(hz/115200)
    actual=re.search(r'\buart_tx\s*#\(\.BAUD_DIV\((\d+)\)\)\s*u_uart_tx',sources[1].read_text(encoding='utf-8'))
    if not actual or int(actual[1])!=baud:
        raise RuntimeError('Production UART divisor differs from the actual DDR user clock')
    commands=[[shutil.which('iverilog'),'-g2012','-i','-s','tb_shared_uart',
               f'-Ptb_shared_uart.CLOCK_HALF_NS={5e8/hz:.12f}',
               f'-Ptb_shared_uart.SERIAL_BAUD_DIV={baud}',
               '-o',str(out/'test.vvp'),*map(str,sources)],
              [shutil.which('vvp'),str(out/'test.vvp')]]
    report={'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in [*sources,idf]],
            'scope':'production top UART arbitration and real serializer at actual system clock/divisor; other IP unelaborated',
            'system_clock_hz':hz,'baud_div':baud,'actual_baud':hz/baud,
            'commands':[],'passed':False}
    try:
        for command in commands:
            run=subprocess.run(command,cwd=ROOT,capture_output=True,timeout=30)
            text=(run.stdout+run.stderr).decode('utf-8',errors='replace')
            print(text,end='')
            report['commands'].append({'command':command,'cwd':str(ROOT),'exit_status':run.returncode,'output':text})
            if run.returncode: raise RuntimeError('Shared UART check failed')
        report['passed']='SHARED_UART_PASS' in text
        if not report['passed']: raise RuntimeError('Missing shared UART completion')
    finally:
        (out/'RESULT.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__': main()
