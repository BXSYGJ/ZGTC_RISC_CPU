"""Execute relocated CoreMark through the frozen bootloader and modeled UART."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from uuid import uuid4
import run_embench as h
import check_embench_loader_rtl as loader
from create_redirect_optimization import replace_once
from run_redirect_optimization import instrument


def main():
    p=argparse.ArgumentParser()
    p.add_argument('firmware',type=Path)
    p.add_argument('--variants',type=Path,default=h.ROOT/'variants/redirect-optimization-v27-r1')
    p.add_argument('--modes',nargs='+',default=['priming_off','priming_on','early_issue'])
    args=p.parse_args(); firmware=args.firmware.resolve(); variants=args.variants.resolve()
    fm=json.loads((firmware/'manifest.json').read_text()); vm=json.loads((variants/'manifest.json').read_text())
    from run_selected_clock import CLOCKS
    clock=fm.get('configured_clock_hz')
    if clock not in CLOCKS: raise ValueError('Unsupported firmware clock')
    if fm['status']!='built_not_executed' or fm.get('application_address')!=4096 or fm['protocol']!='v27':
        raise ValueError('Frozen relocated CoreMark firmware required')
    if fm['variant_manifest_sha256']!=h.sha(variants/'manifest.json'): raise ValueError('Variant set differs from build gates')
    if any(m not in vm['variants'] for m in args.modes): raise ValueError('Unknown variant')
    boot=h.ROOT/'results'/fm['loader_firmware_run']; bm=json.loads((boot/'manifest.json').read_text())
    if bm.get('status')!='built' or bm.get('configured_clock_hz')!=clock:
        raise ValueError('Bootloader status or declared clock differs')
    br=next(r for r in bm['results'] if r['workload']=='uart-loader')
    if h.sha(boot/'workloads/uart-loader/firmware.hex')!=br['firmware_sha256']: raise ValueError('Loader changed')
    for name,digest in json.loads((firmware/'source-hashes.json').read_text()).items():
        if h.sha(firmware/'inputs'/name)!=digest: raise ValueError('Firmware source changed')
    run=h.ROOT/'results'/('coremark-loader-rtl-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]); run.mkdir(exist_ok=False)
    record=dict(protocol='v27',status='running',firmware=str(firmware),firmware_manifest_sha256=h.sha(firmware/'manifest.json'),
                variant_manifest_sha256=h.sha(variants/'manifest.json'),loader_sha256=br['firmware_sha256'],
                iterations=fm['iterations'],configured_clock_hz=clock,
                console_delay_cycles=fm['console_delay_cycles'],models={},results=[])
    def save(): h.write_json(run/'manifest.json',record)
    for source in (Path(__file__),h.ROOT/'scripts/run_redirect_optimization.py',Path(loader.__file__),Path(h.__file__)):
        h.snapshot(source,run/'tools'/source.name)
    h.snapshot(firmware/'inputs/check_coremark.py',run/'tools/check_coremark.py')
    spec=importlib.util.spec_from_file_location('frozen_loader_checker',run/'tools/check_coremark.py')
    checker=importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    save(); print('RUN '+str(run),flush=True)
    try:
        loader.DRIVE=replace_once(loader.DRIVE,r'" send G\n"',
                                 '"ZGTC COREMARK READY send G; clock='+str(clock)+r' Hz\n"')
        for mode in args.modes:
            model=run/'models'/mode
            for name,digest in vm['variants'][mode]['hashes'].items():
                if name.startswith('rtl/'):
                    if h.sha(variants/mode/name)!=digest: raise ValueError('RTL changed')
                    h.snapshot(variants/mode/name,model/'inputs'/name)
            h.snapshot(firmware/'inputs/port/sim_main.cpp',model/'inputs/port/sim_main.cpp')
            h.snapshot(h.PORT/'rv32_observed_soc.sv',model/'inputs/port/rv32_observed_soc.sv')
            path=model/'inputs/port/sim_main.cpp'; code=path.read_text()
            code=replace_once(code,'        bool command_started = false;\n        uint64_t command_start = 0;\n','')
            begin=code.index('            if (!command_started && model->status_code == 0xc0100000U) {')
            end=code.index('            if (model->trap_valid || model->maintenance_fault)',begin)
            code=code[:begin]+code[end:]; path.write_text(code,encoding='utf-8')
            instrument(model)
            hashes={str(p.relative_to(model/'inputs')):h.sha(p) for p in (model/'inputs').rglob('*') if p.is_file()}
            h.write_json(model/'source-hashes.json',hashes)
            executable=h.build_simulator(model)
            record['models'][mode]=dict(executable_sha256=h.sha(executable),source_manifest_sha256=h.sha(model/'source-hashes.json')); save()
            for info in fm['firmware']:
                label=info['configuration']; work=run/'runs'/mode/label; work.mkdir(parents=True)
                original=firmware/'firmware'/label/'firmware.bin'
                if h.sha(original)!=info['binary_sha256']: raise ValueError('CoreMark application changed')
                h.snapshot(original,work/'application.bin'); h.snapshot(boot/'workloads/uart-loader/firmware.hex',work/'firmware.hex')
                row=dict(variant=mode,configuration=label,status='running',binary_sha256=info['binary_sha256'],evidence=str(work))
                record['results'].append(row); save(); print('SIM '+mode+' '+label,flush=True)
                code=h.command([executable,work/'uart.log','10000000000',work/'application.bin'],work,'simulation',7200)
                uart=(work/'uart.log').read_text(); log=(work/'simulation.log').read_text()
                crc=re.search(r'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n',uart)
                if code or not crc or crc[1]!=info['ram_crc32'] or int(crc[2],16)!=info['binary_bytes']:
                    row['status']='failed'; raise ValueError('Loader transfer or simulation failed')
                parsed=checker.parse_result(uart,allow_short=fm['iterations']<6000,expected_config=0x0e8e96fd,expected_clock_hz=clock)
                observer=re.search(r'^OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)$',log,re.M)
                if not observer or tuple(map(int,observer.groups()[:2]))!=(parsed['cycles'],parsed['retired']):
                    row['status']='failed'; raise ValueError('Counter boundary mismatch')
                if parsed['iterations']!=fm['iterations'] or parsed['validation_run']!=info['validation_run']:
                    row['status']='failed'; raise ValueError('CoreMark configuration mismatch')
                row.update(status='passed',cycles=parsed['cycles'],retired_instructions=parsed['retired'],
                           cpi=parsed['cycles']/parsed['retired'],ram_crc32=crc[1],minimum_sp=int(observer[3]),
                           uart_sha256=h.sha(work/'uart.log'),simulation_log_sha256=h.sha(work/'simulation.log'))
                save(); print(json.dumps(row),flush=True)
            for name,digest in hashes.items():
                if h.sha(model/'inputs'/name)!=digest: raise ValueError('Model input changed')
        record['status']='passed'
    except Exception as error:
        record.update(status='failed',error=str(error)); raise
    finally: save()
    print('DONE '+str(run),flush=True)


if __name__=='__main__': main()
