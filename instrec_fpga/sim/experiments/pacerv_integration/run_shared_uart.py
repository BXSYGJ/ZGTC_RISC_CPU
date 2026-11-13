"""Test production UART priority and serialized bytes with four simultaneous sources."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

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
    commands=[[shutil.which('iverilog'),'-g2012','-i','-s','tb_shared_uart','-o',str(out/'test.vvp'),*map(str,sources)],
              [shutil.which('vvp'),str(out/'test.vvp')]]
    report={'inputs':[{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sources],
            'scope':'production top UART arbitration and real serializer; other IP unelaborated',
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
