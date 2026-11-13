"""Prepare/build or capture the independent PG200 clock diagnostic."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def prepare() -> Path:
    out=ROOT/'build/pacerv_shared_system/pds'/('clock-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'-full')
    out.mkdir(parents=True,exist_ok=False)
    sources=[HERE/'pg200_clock_probe.v',ROOT/'src/ctrl/uart_tx.v']
    pins={'board_clk27':('D18','3.3','LVCMOS33'),'resetn':('C22','3.3','LVCMOS33'),
          'uart_tx':('AB26','3.3','LVCMOS33'),'ref_clk_p':('N3','1.5','SSTL15D_I'),
          'ref_clk_n':('N2','1.5','SSTL15D_I')}
    lines=['create_clock -name {board_clk27} [get_ports {board_clk27}] -period {37.037} -waveform {0.000 18.519}',
           'create_clock -name {ref_clk} [get_ports {ref_clk_p}] -period {8.000} -waveform {0.000 4.000}',
           'set_clock_groups -asynchronous -group [get_clocks {board_clk27}] -group [get_clocks {ref_clk}]']
    for name,(pin,voltage,standard) in pins.items():
        props={'PAP_IO_LOC':pin,'PAP_IO_VCCIO':voltage,'PAP_IO_STANDARD':standard,
               'PAP_IO_DIRECTION':'OUTPUT' if name=='uart_tx' else 'INPUT','PAP_IO_NONE':'TRUE'}
        if name=='uart_tx': props.update(PAP_IO_DRIVE='8',PAP_IO_SLEW='SLOW')
        lines += [f'define_attribute {{p:{name}}} {{{key}}} {{{value}}}' for key,value in props.items()]
    constraint=out/'clock_probe.fdc';constraint.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    records=[];tcl=[]
    for source in sources:
        path=source.relative_to(ROOT);target=out/'inputs'/path
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        records.append({'path':path.as_posix(),'bytes':target.stat().st_size,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
        tcl.append(f'add_design "{target.as_posix()}"')
    # The diagnostic's generated constraints are frozen inside this run.
    frozen=out/'inputs/clock_probe.fdc';shutil.copy2(constraint,frozen)
    records.append({'path':'clock_probe.fdc','bytes':frozen.stat().st_size,'sha256':hashlib.sha256(frozen.read_bytes()).hexdigest()})
    tcl += [f'add_constraint "{frozen.as_posix()}"','set_arch -family Logos2 -device PG2L200H -speedgrade -6 -package FBB676',
            'compile -system_verilog -top_module pg200_clock_probe','synthesize -ads -selected_syn_tool_opt 2',
            'dev_map','pnr -gplace_seed 1','report_timing','gen_bit_stream','exit']
    (out/'build.tcl').write_text('\n'.join(tcl)+'\n',encoding='utf-8')
    manifest={'scope':'PG200 independent 27 MHz UART and differential-reference measurement; no CPU/DDR traffic',
              'target':'PG2L200H-6FBB676','project_name':'pacerv_pg200_clock_probe','stage':'full','files':records}
    (out/'INPUTS.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print('CLOCK_PROBE_PREPARED '+str(out),flush=True)
    return out


def capture(bitstream:Path,output:Path,account:Path,seconds:float) -> None:
    sys.path.insert(0,str(ROOT.parent/'tool/fpga_lab'))
    from fpga_lab_server.platform import PlatformClient
    from remote_capture import unpack_serial
    client=PlatformClient();device=None;opened=False;attempted=False;raw=bytearray()
    output.mkdir(parents=True,exist_ok=False)
    result={'scope':'independent 27 MHz UART / N3,N2 reference measurement',
            'bitstream':str(bitstream.resolve()),'bitstream_sha256':hashlib.sha256(bitstream.read_bytes()).hexdigest(),
            'programmed':False,'released':False,'bytes':0}
    try:
        client.relogin_from_account(account)
        if client.current_device(): raise RuntimeError('Existing reservation retained')
        attempted=True
        reservation=client.reserve(minutes=10,card_type='with_camera')
        current=client.current_device() or {}
        device=current.get('device_id') or reservation.get('device_id') or reservation.get('deviceId')
        if not device: raise RuntimeError('Reservation has no device id')
        result['device_id']=device
        client.burn_and_wait(int(device),bitstream);result['programmed']=True
        client.serial_open(int(device),baud=115200);opened=True
        deadline=time.monotonic()+seconds
        with (output/'capture.jsonl').open('w',encoding='utf-8') as log:
            while time.monotonic()<deadline:
                packet=unpack_serial(client.serial_read(int(device),length=512))
                if packet:
                    raw.extend(packet);log.write(json.dumps({'hex':packet.hex()})+'\n');log.flush()
                else: time.sleep(.15)
    finally:
        try:
            if opened: client.serial_close(int(device))
        finally:
            try:
                if device is None and attempted:
                    device=(client.current_device() or {}).get('device_id')
                if device is not None:
                    client.release(int(device));result['released']=True
            finally:
                client.close()
                result['bytes']=len(raw)
                counts=[int(x,16) for x in re.findall(rb'PG200_REF E=([0-9A-F]{8}) R=1\r?\n',raw)]
                result['transition_counts_10ms']=counts
                result['reference_hz_estimates']=[x*12800 for x in counts]
                result['uart_records_received']=len(counts)
                (output/'capture.bin').write_bytes(raw)
                (output/'capture.txt').write_text(raw.decode('ascii',errors='replace'),encoding='utf-8')
                (output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run-pds',action='store_true')
    ap.add_argument('--capture',type=Path)
    ap.add_argument('--output',type=Path)
    ap.add_argument('--account',type=Path)
    ap.add_argument('--seconds',type=float,default=15)
    args=ap.parse_args()
    if args.capture:
        if not args.output or not args.account: ap.error('--capture needs --output and --account')
        capture(args.capture.resolve(strict=True),args.output,args.account,args.seconds)
    else:
        out=prepare()
        if args.run_pds:
            sys.path.insert(0,str(HERE.parent))
            from prepare_pds import run
            run(out,15)
