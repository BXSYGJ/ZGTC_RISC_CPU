"""Freeze and compile a RAM loader plus relocated pinned Embench (WSL)."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
from uuid import uuid4
import zlib
import run_embench as h

UPSTREAM = h.ROOT/'results/fpga-lab-inspection-20260918-155258/upstream'
REVISION = '08dbfa1b930f87981fe213367f3c25a4e4f4134a'

def hex_image(binary, address=0):
    if address+len(binary)>65536: raise ValueError('Image exceeds RAM')
    padded=bytes(address)+binary+bytes(65536-address-len(binary))
    return ''.join(f'{int.from_bytes(padded[i:i+4],"little"):08x}\n' for i in range(0,65536,4))

def main():
    lock=json.loads((h.ROOT/'third_party/SOURCES_LOCK.json').read_text(encoding='utf-8-sig'))
    names=['crc32','instrumentation-dummy']+[n for n in lock['embench_workloads'] if n!='crc32']
    run=h.ROOT/'results'/('embench-loader-firmware-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    record=dict(status='running',protocol='v26',configured_clock_hz=153000000,workloads=names,results=[],
        warmup_heat=1,global_scale_factor=1,stack_reservation_bytes=16384,application_address=4096,
        upstream_revision=REVISION,hardware_parameters=h.PARAMS,official_embench_score=False)
    def save(): h.write_json(run/'manifest.json',record)
    save(); print('RUN '+str(run),flush=True)
    try:
        h.source_snapshot(run)
        h.snapshot(h.ROOT/'ports/embench_board/boardsupport.c',run/'inputs/port/boardsupport.c')
        h.snapshot(h.ROOT/'ports/embench_loader/bootloader.c',run/'inputs/loader/bootloader.c')
        for name in ('boot_start.S','boot_link.ld','bootloader.c'):
            h.snapshot(UPSTREAM/'cpu/sw/boot'/name,run/'inputs/upstream'/name)
        for name in ('boot_start.S','boot_link.ld'):
            h.snapshot(UPSTREAM/'cpu/sw/boot'/name,run/'inputs/loader'/name)
        for original in UPSTREAM.glob('LICENSE*'): h.snapshot(original,run/'inputs/upstream'/original.name)
        h.snapshot(h.ROOT/'protocol_v26.md',run/'inputs/protocol_v26.md')
        h.snapshot(__file__,run/'inputs/build_embench_loader.py')
        linker=run/'inputs/port/link_soc.ld'; original=linker.read_text()
        token='ORIGIN = 0, LENGTH = 64K'
        if original.count(token)!=1: raise ValueError('Unexpected linker')
        linker.write_text(original.replace(token,'ORIGIN = 0x1000, LENGTH = 60K'))
        hashes={p.relative_to(run/'inputs').as_posix():h.sha(p) for p in (run/'inputs').rglob('*') if p.is_file()}
        h.write_json(run/'source-hashes.json',hashes)
        record['source_manifest_sha256']=h.sha(run/'source-hashes.json')
        gcc=str(h.TOOL)+'gcc'
        record['compiler_version']=subprocess.check_output([gcc,'--version'],text=True).splitlines()[0]
        record['compiler_sha256']=h.sha(gcc)
        record['libraries']={}
        for name in ('libc.a','libm.a','libgcc.a'):
            path=subprocess.check_output([gcc,'-march=rv32im','-mabi=ilp32','-print-file-name='+name],text=True).strip()
            record['libraries'][name]=dict(path=path,sha256=h.sha(path))
        work=run/'workloads/uart-loader'; work.mkdir(parents=True)
        source=run/'inputs/loader'; elf=work/'firmware.elf'; binary=work/'firmware.bin'
        flags=['-march=rv32im','-mabi=ilp32','-msmall-data-limit=0','-O2','-ffreestanding','-fno-builtin','-Wall','-Wextra','-Werror','-nostdlib','-nostartfiles','-Wl,--no-relax','-Wl,-Map=firmware.map']
        if h.command([gcc,*flags,'-T',source/'boot_link.ld','-o',elf,source/'boot_start.S',source/'bootloader.c','-lgcc'],work,'firmware-build'):
            raise ValueError('Loader build failed')
        for suffix,args in [('objcopy',['-O','binary',elf,binary]),('objdump',['-d',elf]),('size',[elf])]:
            if h.command([str(h.TOOL)+suffix,*args],work,suffix): raise ValueError('Loader inspection failed')
        raw=binary.read_bytes()
        if len(raw)>3840: raise ValueError('Loader stack reservation violated')
        (work/'firmware.hex').write_text(hex_image(raw),encoding='ascii')
        record['results'].append(dict(workload='uart-loader',category='loader',status='built',firmware_sha256=h.sha(work/'firmware.hex'),
            binary_sha256=h.sha(binary),elf_sha256=h.sha(elf),binary_bytes=len(raw),flags=flags))
        base_flags=h.FLAGS[:]
        for name in names:
            h.FLAGS=base_flags+['-DWORKLOAD_NAME="'+name+'"','-DCONSOLE_DELAY_CYCLES=2700000u']
            row=h.build_workload(run,name,SimpleNamespace(warmup=1,scale=1))
            if row['status']=='built':
                work=run/'workloads'/name; raw=(work/'firmware.bin').read_bytes()
                if len(raw)>45056: raise ValueError('Application crosses stack reservation')
                (work/'firmware.hex').write_text(hex_image(raw,4096),encoding='ascii')
                row.update(firmware_sha256=h.sha(work/'firmware.hex'),binary_sha256=h.sha(work/'firmware.bin'),
                    binary_bytes=len(raw),ram_crc32=f'{zlib.crc32(raw):08x}',load_address=4096,flags=h.FLAGS[:],
                    measurement_kind='build_only_relocated_uart_application',configured_clock_hz=153000000)
            record['results'].append(row); h.write_json(run/'workloads'/name/'result.json',row); save()
            print(name+': '+row['status'],flush=True)
        for relative,digest in hashes.items():
            if h.sha(run/'inputs'/relative)!=digest: raise ValueError('Frozen source changed')
        record['status']='built' if all(r['status']=='built' for r in record['results']) else 'build_failed'
    except Exception as error: record.update(status='failed',error=str(error)); raise
    finally: save()
    print(run,flush=True)

if __name__=='__main__': main()
