"""Cold-programmed selected-clock CoreMark V0/V1 matrix via the native RAM loader.

Hardware execution can explicitly overlap an already running full RTL test.
Independent final qualification always requires the completed RTL evidence.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import time
from uuid import uuid4

import run_embench as h
from selected_coremark_board_evidence import bind_inputs, parse
from fpga_lab_auth import connect_native
from fpga_lab_gateway import select_healthy_gateway
from fpga_lab_native import public_device, PLATFORM_SOURCE
from run_embench_native import receive_bytes, response_body
from fpga_serial_reads import read_serial
from fpga_capture_policy import SerialCaptureError, parse_capture


def transport_parse(raw, checker, info, clock, lut):
    # Never retry or suppress CRC, compiler, duration or counter disagreements.
    return parse_capture(parse,raw,checker,info,clock,lut)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('physical','variants','boot','smoke','firmware','screen','full-rtl'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--allow-pending-full-rtl',action='store_true')
    parser.add_argument('--serial-read-length',type=int,choices=(16,64,512),default=512)
    parser.add_argument('--serial-read-retries',type=int,choices=range(4),default=0)
    parser.add_argument('--serial-poll-interval',type=float,choices=(0.05,0.1),default=0.05)
    parser.add_argument('--capture-attempts',type=int,choices=(1,2,3),default=1)
    args=parser.parse_args()
    receipt,pm,fm=bind_inputs(args.physical,args.variants,args.boot,args.smoke,
                            args.firmware,args.screen,args.full_rtl,args.allow_pending_full_rtl)
    physical=Path(receipt['physical']); firmware=Path(receipt['firmware'])
    clock=receipt['configured_clock_hz']; lut=receipt['resources']['post_route_luts']
    run=h.ROOT/'results'/('selected-coremark-board-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    run.mkdir(exist_ok=False)
    order=[(label,rep) for rep in range(1,4) for label in (('V1','V0') if rep==2 else ('V0','V1'))]
    record=dict(schema=1,protocol='v31' if pm['protocol']=='v27' else 'v28',status='prepared',configured_clock_hz=clock,
        measured_clock_hz=None,hardware_action_attempted=False,hardware_executed=False,
        final_qualification=False,receipt=receipt,observations=[],order=order,
        serial_read_length=args.serial_read_length,serial_poll_interval_seconds=args.serial_poll_interval,
        serial_read_retries=args.serial_read_retries,gateway_selection='qualified_control_probe',
        serial_drain_policy='immediate_when_nonempty',capture_attempts=args.capture_attempts,
        attempts=[],loader_serial_read_length=512)
    for name in ('run_selected_coremark_board.py','selected_coremark_board_evidence.py',
                 'fpga_lab_auth.py','fpga_lab_gateway.py','fpga_lab_native.py','run_embench_native.py',
                 'coremark_uart_frame.py','review_selected_clock.py','review_selected_loader.py',
                 'review_coremark_loader_evidence.py','embench_board_evidence.py','physical_instrumentation.py',
                 'redirect_physical_binding.py','redirect_loader_binding.py','selected_clock_profiles.py',
                 'fpga_serial_reads.py','fpga_capture_policy.py'):
        h.snapshot(h.ROOT/'scripts'/name,run/'tools'/name)
    h.snapshot(firmware/'inputs/check_coremark.py',run/'tools/check_coremark.py')
    h.snapshot(PLATFORM_SOURCE,run/'tools/platform.py')
    plan = 'v31_vex_stages_and_153_resource_efficiency.md' if pm['protocol']=='v27' else 'r58_selected_clock_qualification.md'
    h.snapshot(h.ROOT/'plans'/plan,run/'protocol.md')
    h.snapshot(args.full_rtl/'manifest.json',run/'full-rtl-at-preparation.json')
    def save(): h.write_json(run/'manifest.json',record)
    def event(kind,**data):
        with (run/'events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),kind=kind,**data))+'\n')
    save(); print('RUN '+str(run),flush=True)
    if args.prepare_only:
        return
    spec=importlib.util.spec_from_file_location('selected_board_checker',run/'tools/check_coremark.py')
    checker=importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    client=None; opened=False; did=None
    try:
        client=connect_native()
        current=select_healthy_gateway(client,event,run/'gateway-health',minimum_seconds=900)
        did=current['device_id']; record['device']=public_device(current); save()
        entries={r['configuration']:r for r in fm['firmware']}
        def capture(label,rep,attempt):
            nonlocal opened
            bit=physical/'implementation/generate_bitstream/pds_soc_top.sbit'
            if h.sha(bit)!=receipt['bitstream_sha256']:
                raise ValueError('Bitstream changed before programming')
            info=entries[label]; binary=firmware/'firmware'/label/'firmware.bin'
            if h.sha(binary)!=info['binary_sha256']:
                raise ValueError('Application changed before upload')
            app=binary.read_bytes(); prefix=f'{label}-r{rep}-a{attempt}'
            row=dict(configuration=label,repetition=rep,status='programming',
                cold_programmed=False,application=info,bitstream_sha256=h.sha(bit),
                attempt=attempt,prefix=prefix)
            record['attempts'].append(row); record['hardware_action_attempted']=True; save()
            client.firmware_download(did,bit)
            event('programming_requested',observation=prefix,bitstream_sha256=h.sha(bit))
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                progress=client.firmware_progress(did)
                event('programming_progress',observation=prefix,response=progress)
                phase=progress.get('phase') or progress.get('state')
                if phase in ('failed','error') or progress.get('isFailed') or progress.get('isWakeupFailed'):
                    raise RuntimeError('Board programming failed')
                if progress.get('isComplete') is True or phase=='complete':
                    break
                time.sleep(1)
            else: raise TimeoutError('Programming confirmation missing')
            row.update(programming_complete=progress,cold_programmed=True,status='uploading')
            record['hardware_executed']=True; save()
            event('serial_open',observation=prefix,response=client.serial_open(did,baud=115200)); opened=True
            raw=bytearray(); serial=run/(prefix+'-serial.bin'); serial.write_bytes(b'')
            read_length=512
            def poll():
                response=read_serial(client,did,read_length,args.serial_read_retries,
                    lambda **data:event('serial_read_error',observation=prefix,**data))
                event('serial_read',observation=prefix,response=response)
                chunk=receive_bytes(response); raw.extend(chunk)
                if chunk:
                    with serial.open('ab') as stream: stream.write(chunk)
                return chunk
            def send(payload):
                response=client.serial_send(did,payload.hex(),mode='hex')
                event('serial_send',observation=prefix,payload_hex=payload.hex(),response=response)
                if response_body(response).get('bytesSent')!=len(payload):
                    raise ValueError('Short serial send')
            def until(predicate,seconds):
                deadline=time.monotonic()+seconds
                while time.monotonic()<deadline:
                    chunk=poll()
                    if predicate(): return
                    if not chunk: time.sleep(args.serial_poll_interval)
                raise SerialCaptureError('Serial response deadline exceeded')
            poll(); send(b'?'); until(lambda:b'ZBOOT READY R\n' in raw,15)
            transfer_start=len(raw); send(b'R'+len(app).to_bytes(4,'little'))
            for index,offset in enumerate(range(0,len(app),256)):
                send(app[offset:offset+256])
                until(lambda:raw[transfer_start:].count(b'K')>=index+1,15)
            expression=rb'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n'
            until(lambda:re.search(expression,raw[transfer_start:]) is not None,20)
            crc=re.search(expression,raw[transfer_start:])
            acknowledgements=raw[transfer_start:transfer_start+crc.start()].count(b'K')
            if (crc[1].decode()!=info['ram_crc32'] or int(crc[2],16)!=len(app)
                    or acknowledgements!=len(app)//256+1):
                raise ValueError('RAM upload CRC/size/acknowledgement mismatch')
            ready=('ZGTC COREMARK READY send G; clock='+str(clock)+' Hz\n').encode()
            until(lambda:ready in raw[transfer_start:],30)
            boundary=len(raw)
            row.update(status='capturing',transfer_serial_offset=transfer_start,
                benchmark_serial_offset=boundary,loader_acknowledgements=acknowledgements,
                ram_crc32=crc[1].decode(),ram_byte_count=len(app)); save()
            read_length=args.serial_read_length
            send(b'G'); until(lambda:b'ZGTC COREMARK FINISHED\n' in raw[boundary:],240)
            time.sleep(0.2); poll()
            uart=run/(prefix+'-uart.log'); uart.write_bytes(raw[boundary:])
            parsed,frame,framing=transport_parse(bytes(raw[boundary:]),checker,info,clock,lut)
            (run/(prefix+'-frame.log')).write_text(frame,encoding='ascii')
            row.update(status='passed',correctness=True,result=parsed,framing=framing,
                uart_file=uart.name,uart_sha256=h.sha(uart),serial_file=serial.name,serial_sha256=h.sha(serial))
            event('serial_close',observation=prefix,response=client.serial_close(did)); opened=False
            save(); print(prefix+' passed cycles='+str(parsed['cycles'])+' CoreMark/LUT='+
                          str(parsed['iterations_per_second_per_lut']),flush=True)
            return row
        for label,rep in order:
            for attempt in range(1,args.capture_attempts+1):
                try:
                    row=capture(label,rep,attempt)
                    record['observations'].append(row); save()
                    break
                except SerialCaptureError as error:
                    rejected=record['attempts'][-1]
                    rejected.update(status='rejected_transport_capture',error=str(error))
                    event('capture_rejected',observation=rejected['prefix'],reason=str(error))
                    if opened:
                        event('serial_close',observation=rejected['prefix'],response=client.serial_close(did))
                        opened=False
                    save()
                    print(rejected['prefix']+' rejected; raw capture retained',flush=True)
                    if attempt==args.capture_attempts: raise
        for label in entries:
            observations=[r for r in record['observations'] if r['configuration']==label]
            if len(observations)!=3 or len({(r['result']['cycles'],r['result']['retired']) for r in observations})!=1:
                raise ValueError('Board repetition counters disagree')
        record['status']='board_observations_passed_pending_independent_review'
    except Exception as error:
        record.update(status='failed' if record['hardware_action_attempted'] else 'not_executed',error=str(error))
        raise
    finally:
        if client:
            if opened:
                try: client.serial_close(did)
                except Exception: event('serial_close_failed')
            if did is not None:
                try: client.release(did); event('device_released',device_id=did)
                except Exception: event('device_release_failed',device_id=did)
            client.close()
        record['finished_utc']=datetime.now(timezone.utc).isoformat()
        record['artifact_hashes']={p.relative_to(run).as_posix():h.sha(p)
            for p in run.rglob('*') if p.is_file() and p.name!='manifest.json'}
        save(); print(run,flush=True)


if __name__=='__main__': main()
