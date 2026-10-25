"""Independently review completed CoreMark UART-loader RTL observations.

This creates new CSV/JSON evidence, never a hardware or timing qualification.
Run manifests must be terminal; individual completed rows of a live run are
insufficient. A firmware build's repetitions field is not an execution count.
"""
import argparse
import csv
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import re
from uuid import uuid4
import zlib
import run_embench as h
from embench_board_evidence import read
from redirect_loader_binding import (contained, local_path, safe_name, inventory,
    require, compile_parameters, model_command, command_argument)


def bind(run, variants, variant, firmware):
    run=contained(run,'results'); variants=contained(variants,'variants')
    firmware=contained(firmware,'results'); safe_name(variant)
    rm=read(run/'manifest.json'); vm=read(variants/'manifest.json'); fm=read(firmware/'manifest.json')
    require(rm.get('protocol')=='v27' and rm.get('status')=='passed','Completed v27 loader run required')
    require(vm.get('protocol')=='v27' and variant in vm['variants'],'Unknown v27 variant')
    require(fm.get('protocol')=='v27' and fm.get('status')=='built_not_executed' and
            fm.get('application_address')==4096,'Frozen relocated firmware required')
    require(rm['variant_manifest_sha256']==fm['variant_manifest_sha256']==h.sha(variants/'manifest.json'),
            'RTL manifest differs')
    require(rm['firmware_manifest_sha256']==h.sha(firmware/'manifest.json') and
            local_path(rm['firmware'])==firmware,'Firmware manifest differs')
    require(rm['iterations']==fm['iterations']==6000 and
            rm['console_delay_cycles']==fm['console_delay_cycles']==2700000,
            'Full-run iterations or console pacing differs')
    from run_selected_clock import CLOCKS
    clock=fm.get('configured_clock_hz')
    require(clock in CLOCKS and rm.get('configured_clock_hz',153000000)==clock and fm.get('measured_clock_hz') is None and
            fm['hardware_parameters']==h.PARAMS and fm['stack_reservation_bytes']==16384,
            'Firmware clock, hardware parameters or stack differs')
    inventory(variants/variant,vm['variants'][variant]['hashes'])
    inventory(firmware/'inputs',read(firmware/'source-hashes.json'))
    boot=contained(h.ROOT/'results'/fm['loader_firmware_run'],'results'); bm=read(boot/'manifest.json')
    require(bm.get('protocol')=='v26' and bm.get('status')=='built','Frozen bootloader required')
    require(bm.get('configured_clock_hz')==clock,'Bootloader declared clock differs')
    br=next(r for r in bm['results'] if r['workload']=='uart-loader')
    require(rm['loader_sha256']==br['firmware_sha256']==h.sha(boot/'workloads/uart-loader/firmware.hex'),
            'Bootloader identity differs')
    require(variant in rm['models'],'Requested model missing')
    model=run/'models'/variant; mi=rm['models'][variant]
    require(h.sha(model/'source-hashes.json')==mi['source_manifest_sha256'],'Model inventory changed')
    sources=read(model/'source-hashes.json'); inventory(model/'inputs',sources)
    expected={n:d for n,d in vm['variants'][variant]['hashes'].items() if n.startswith('rtl/')}
    require({n:d for n,d in sources.items() if n.startswith('rtl/')}==expected,'Model RTL differs')
    executable=model/'simulator/objects/Vrv32_observed_soc'
    require(h.sha(executable)==mi['executable_sha256'],'Model executable changed')
    command=read(model/'simulator/compile.command.json')
    parameters=compile_parameters(command['argv']); model_command(model,command)
    compile_log=(model/'simulator/compile.log').read_text(encoding='utf-8')
    warnings=re.findall(r'^%Warning[^\n]*',compile_log,re.M)
    unexpected=[w for w in warnings if not (w.startswith('%Warning-WIDTH:') and 'rv32_burst_ram.sv:' in w and 'Operator NEQ' in w)]
    require(not unexpected and read(model/'simulator/warnings.json')==dict(warnings=warnings,unexpected=unexpected),
            'Unreviewed model warnings')
    checker=run/'tools/check_coremark.py'
    require(h.sha(checker)==h.sha(firmware/'inputs/check_coremark.py'),'Frozen checker identity differs')
    spec=importlib.util.spec_from_file_location('bound_coremark_checker',checker)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    inputs={r['configuration']:r for r in fm['firmware']}
    require(set(inputs)=={'V0','V1'} and len(fm['firmware'])==2,'Firmware configuration coverage differs')
    rows=[r for r in rm['results'] if r['variant']==variant]
    require(len(rows)==2 and {r['configuration'] for r in rows}=={'V0','V1'},'Missing or duplicate V0/V1 observation')
    result=[]
    for row in rows:
        label=row['configuration']; info=inputs[label]; work=run/'runs'/variant/label
        require(row['status']=='passed' and local_path(row['evidence'])==work,'Failed or mislabeled observation')
        invocation=read(work/'simulation.command.json')
        expected_argv=[executable,work/'uart.log','10000000000',work/'application.bin']
        require([command_argument(a) for a in invocation['argv']]==[command_argument(a) for a in expected_argv]
                and local_path(invocation['cwd'])==work and invocation['timeout_seconds']==7200,
                'Simulation invocation differs')
        require(row['binary_sha256']==info['binary_sha256']==h.sha(work/'application.bin')==
                h.sha(firmware/'firmware'/label/'firmware.bin'),'Application identity differs')
        require(h.sha(work/'firmware.hex')==rm['loader_sha256'],'Loaded bootloader differs')
        for name,key in (('uart.log','uart_sha256'),('simulation.log','simulation_log_sha256')):
            require(h.sha(work/name)==row[key],'Raw observation changed: '+name)
        binary=(work/'application.bin').read_bytes()
        require(info['load_address']==4096 and len(binary)==info['binary_bytes'] and
                format(zlib.crc32(binary),'08x')==info['ram_crc32']==row['ram_crc32'],'Application size/CRC differs')
        uart=(work/'uart.log').read_text(encoding='ascii')
        crcs=re.findall(r'^BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})$',uart,re.M)
        require(crcs==[(info['ram_crc32'],format(len(binary),'08x'))],'UART transfer CRC/size differs')
        parsed=module.parse_result(uart,allow_short=False,expected_config=0x0e8e96fd,expected_clock_hz=clock)
        require(parsed['iterations']==6000 and parsed['validation_run']==info['validation_run']==(label=='V1'),
                'Benchmark configuration differs')
        log=(work/'simulation.log').read_text(encoding='utf-8')
        require('TIMEOUT' not in log and 'PASS RTL CoreMark smoke ' in log,'Simulation completion missing')
        observations=re.findall(r'^OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)$',log,re.M)
        require(len(observations)==1,'Independent counter observation missing/ambiguous')
        cycles,retired,sp=map(int,observations[0])
        require((cycles,retired)==(parsed['cycles'],parsed['retired'])==
                (row['cycles'],row['retired_instructions']),'UART/observer/counter disagreement')
        require(row['cpi']==cycles/retired and row['minimum_sp']==sp,'CPI or stack observation differs')
        require(49152<=sp<=65536,'Observed stack exceeds reserved region')
        result.append(dict(variant=variant,configuration=label,iterations=6000,observations=1,
            correctness=True,cycles=cycles,retired_instructions=retired,cpi=cycles/retired,
            configured_clock_hz=clock,measured_clock_hz=None,
            configured_clock_seconds=parsed['seconds'],reportable_duration=parsed['reportable_duration'],
            hardware_score=None,minimum_sp=sp,binary_sha256=row['binary_sha256'],ram_crc32=row['ram_crc32'],
            uart_sha256=row['uart_sha256'],simulation_log_sha256=row['simulation_log_sha256'],evidence=str(work)))
    receipt=dict(run=str(run),manifest_sha256=h.sha(run/'manifest.json'),variant=variant,
        variant_manifest_sha256=h.sha(variants/'manifest.json'),firmware_manifest_sha256=h.sha(firmware/'manifest.json'),
        firmware_source_inventory_sha256=h.sha(firmware/'source-hashes.json'),
        model_source_manifest_sha256=mi['source_manifest_sha256'],executable_sha256=mi['executable_sha256'],
        compile_command_sha256=h.sha(model/'simulator/compile.command.json'),
        checker_sha256=h.sha(checker),parameters=parameters)
    return dict(receipt=receipt,observations=result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True); p.add_argument('--variants',type=Path,required=True)
    p.add_argument('--variant',required=True); p.add_argument('--firmware',type=Path,required=True)
    args=p.parse_args(); result=bind(args.run,args.variants,args.variant,args.firmware)
    run=h.ROOT/'results'/('coremark-loader-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    tools=('review_coremark_loader_evidence.py','redirect_loader_binding.py','embench_board_evidence.py','run_embench.py')
    for name in tools: h.snapshot(h.ROOT/'scripts'/name,run/'tools'/name)
    h.write_json(run/'results.json',result['observations'])
    with (run/'results.csv').open('w',encoding='utf-8-sig',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=list(result['observations'][0])); writer.writeheader(); writer.writerows(result['observations'])
    h.write_json(run/'review.json',dict(status='full_coremark_loader_evidence_verified',protocol='v27',
        scope='One RTL observation per configuration. No hardware score, measured frequency, timing qualification or final repetition claim.',
        receipt=result['receipt'],source_hashes={n:h.sha(run/'tools'/n) for n in tools},
        results_sha256=h.sha(run/'results.json'),csv_sha256=h.sha(run/'results.csv')))
    print(run,flush=True)


if __name__=='__main__': main()
