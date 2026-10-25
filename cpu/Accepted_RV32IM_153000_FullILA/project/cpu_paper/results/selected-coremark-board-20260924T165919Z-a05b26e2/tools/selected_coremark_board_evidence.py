"""Bind selected-clock CPU, loader, firmware and raw CoreMark board frames."""
from pathlib import Path
import zlib
import run_embench as h
from embench_board_evidence import read
from redirect_loader_binding import contained, inventory, local_path, require
from review_selected_clock import validators as physical_validators
from review_selected_loader import validators as loader_validators
from review_coremark_loader_evidence import bind as full_rtl_binding
from run_redirect_native_batch import gate
from run_selected_clock import MODE
from coremark_uart_frame import extract_frame


def parse(raw, checker, firmware, clock, lut):
    frame, framing=extract_frame(raw.decode('ascii'))
    require(not any(ord(c)<32 and c not in '\r\n\t' for c in frame),'Control bytes in CoreMark frame')
    lines=[s for s in frame.splitlines() if s.startswith('Compiler flags   : ')]
    require(lines==['Compiler flags   : '+' '.join(firmware['flags'])],'UART compiler flags differ')
    result=checker.parse_result(frame,allow_short=False,lut_count=lut,
                               expected_config=0x0e8e96fd,expected_clock_hz=clock)
    require(result['iterations']==firmware['iterations']==6000 and
            result['validation_run']==firmware['validation_run'],'CoreMark mode/iterations differ')
    require(result['final_crc']==('18e1' if result['validation_run'] else 'a14c'),
            '6000-iteration final CRC differs from the qualified configuration')
    require(0<result['retired']<=result['cycles'],'Invalid single-issue counter relationship')
    return result,frame,framing


def bind_inputs(physical, variants, boot, smoke, firmware, screen, full_rtl,
                allow_pending=False):
    physical,boot,smoke,firmware,screen,full_rtl=(contained(Path(p),'results')
        for p in (physical,boot,smoke,firmware,screen,full_rtl))
    variants=contained(Path(variants),'variants')
    fm=read(firmware/'manifest.json'); clock=fm.get('configured_clock_hz')
    native = read(physical/'manifest.json')
    protocol = native.get('protocol')
    mode = MODE
    if protocol == 'v27':
        require(clock == 153000000 and native.get('variant') == 'accepted_valid_ram',
                'Unsupported 153 MHz area candidate')
        mode = 'accepted_valid_ram'
    check,_,_=physical_validators(clock, protocol)
    pm,timing=check(physical,variants,mode,boot)
    require(pm['placement_seed']==3,'Selected experiment requires seed 3')
    require(pm['report']['resources']['post_route_luts']<9502,'Selected image exceeds area limit')
    loader,_,_,_=loader_validators(clock, protocol)
    loader_receipt=loader([smoke],variants,mode,boot)
    screen_receipt=gate(dict(variants=str(variants),variant=mode,seed=3,coremark=str(screen)))
    cm=read(screen/'manifest.json')
    require(cm['configured_clock_hz']==clock,'Short-screen clock differs')
    require(fm.get('protocol')=='v27' and fm.get('status')=='built_not_executed' and
            fm.get('iterations')==6000 and fm.get('console_delay_cycles')==2700000 and
            fm.get('application_address')==4096 and fm.get('stack_reservation_bytes')==16384 and
            fm.get('hardware_parameters')==h.PARAMS,'Unexpected full CoreMark build scope')
    require(fm['variant_manifest_sha256']==h.sha(variants/'manifest.json') and
            fm['gates']==cm['gates'],'Full-build source/correctness gates differ')
    require((h.ROOT/'results'/fm['loader_firmware_run']).resolve()==boot,'Different RAM loader build')
    inventory(firmware/'inputs',read(firmware/'source-hashes.json'))
    locked=read(firmware/'inputs/COREMARK_LOCK.json')
    for name,digest in locked['sha256'].items():
        require(h.sha(firmware/'inputs/coremark'/name)==digest,'Pinned CoreMark source changed')
    entries={row['configuration']:row for row in fm['firmware']}
    require(set(entries)=={'V0','V1'} and len(fm['firmware'])==2,'Missing/duplicate CoreMark configurations')
    for label,info in entries.items():
        require(info['validation_run']==(label=='V1') and info['iterations']==6000 and
                info['load_address']==4096,'Firmware mode/address differs')
        require('-DCPU_CLOCK_HZ='+str(clock)+'u' in info['flags'] and
                '-DITERATIONS=6000' in info['flags'] and
                '-DCONSOLE_DELAY_CYCLES=2700000' in info['flags'],'Firmware clock/iterations/pacing differs')
        directory=firmware/'firmware'/label
        for name,key in (('firmware.bin','binary_sha256'),('firmware.hex','firmware_sha256'),('firmware.elf','elf_sha256')):
            require(h.sha(directory/name)==info[key],'Firmware artifact changed: '+name)
        raw=(directory/'firmware.bin').read_bytes()
        require(0<len(raw)<=45056 and len(raw)==info['binary_bytes'] and
                format(zlib.crc32(raw),'08x')==info['ram_crc32'],'RAM image size/CRC differs')
    rm=read(full_rtl/'manifest.json')
    pending=rm.get('status')=='running'
    if pending and allow_pending:
        require(rm['protocol']=='v27' and rm['iterations']==6000 and
                rm.get('configured_clock_hz')==clock and
                rm['firmware_manifest_sha256']==h.sha(firmware/'manifest.json') and
                rm['variant_manifest_sha256']==h.sha(variants/'manifest.json') and
                local_path(rm['firmware'])==firmware and
                all(r['status'] in ('running','passed') for r in rm['results']),
                'Pending full-length RTL scope differs or a row failed')
        full_receipt=dict(status='pending',run=str(full_rtl),manifest_sha256=h.sha(full_rtl/'manifest.json'))
    else:
        full_receipt=full_rtl_binding(full_rtl,variants,mode,firmware)
    receipt=dict(physical=str(physical),variants=str(variants),boot=str(boot),smoke=str(smoke),
        firmware=str(firmware),screen=str(screen),full_rtl=str(full_rtl),
        configured_clock_hz=clock,variant=mode,physical_manifest_sha256=h.sha(physical/'manifest.json'),
        variant_manifest_sha256=h.sha(variants/'manifest.json'),
        boot_manifest_sha256=h.sha(boot/'manifest.json'),smoke_manifest_sha256=h.sha(smoke/'manifest.json'),
        firmware_manifest_sha256=h.sha(firmware/'manifest.json'),screen_manifest_sha256=h.sha(screen/'manifest.json'),
        full_rtl_pending_at_preparation=pending,full_rtl_receipt=full_receipt,
        screen_receipt=screen_receipt,loader_receipt=loader_receipt,
        bitstream_sha256=pm['bitstream_sha256'],resources=pm['report']['resources'],
        timing=timing,instrumentation_profile=pm.get('instrumentation_profile','full'))
    return receipt,pm,fm
