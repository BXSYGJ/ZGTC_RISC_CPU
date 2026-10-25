"""Capture one qualified Embench execution through the inspected native API."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
from uuid import uuid4
import zlib
import run_embench as h
from embench_board_evidence import read,physical_binding,parse_frame
from fpga_lab_native import connect,public_device,PLATFORM_SOURCE

def response_body(response):
    return response['data'] if isinstance(response.get('data'),dict) else response

def receive_bytes(response):
    body=response_body(response); count=body.get('bytesRead',0)
    if not isinstance(count,int) or count<0 or count>512: raise ValueError('Invalid serial byte count')
    if not count: return b''
    value=body.get('hex')
    if not isinstance(value,str): raise ValueError('Raw hexadecimal serial data is required')
    raw=bytes.fromhex(value)
    if len(raw)!=count: raise ValueError('Serial hex/count mismatch')
    return raw

def main():
    p=argparse.ArgumentParser(); p.add_argument('physical',type=Path); p.add_argument('firmware_run',type=Path)
    p.add_argument('workload'); p.add_argument('--ram',action='store_true'); p.add_argument('--rtl-run',type=Path)
    args=p.parse_args(); physical=args.physical.resolve(); firmware=args.firmware_run.resolve()
    fm=read(firmware/'manifest.json'); row=next(r for r in fm['results'] if r['workload']==args.workload)
    if fm['status']!='built' or row['status']!='built': raise ValueError('Firmware is not qualified for execution')
    pm,timing=physical_binding(physical,'uart-loader' if args.ram else args.workload)
    if h.sha(firmware/'manifest.json')!=pm['firmware_manifest_sha256']: raise ValueError('Physical and application source runs differ')
    if args.ram:
        if not args.rtl_run: raise ValueError('RAM loader requires completed RTL gate')
        rm=read(args.rtl_run/'manifest.json')
        if rm['status']!='passed' or rm['firmware_manifest_sha256']!=h.sha(firmware/'manifest.json'): raise ValueError('RAM loader RTL gate failed')
        if {r['workload'] for r in rm['results']}!={'instrumentation-dummy','crc32','xgboost'}: raise ValueError('Incomplete loader RTL gate')
    bit=physical/'implementation/generate_bitstream/pds_soc_top.sbit'
    run=h.ROOT/'results'/('native-embench-'+args.workload+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]); run.mkdir(exist_ok=False)
    record=dict(status='running',protocol=fm['protocol'],workload=args.workload,transport='native FPGA Lab HTTP API',
        physical_run=str(physical),physical_manifest_sha256=h.sha(physical/'manifest.json'),bitstream_sha256=h.sha(bit),
        firmware_run=str(firmware),firmware_manifest_sha256=h.sha(firmware/'manifest.json'),application=row,
        configured_clock_hz=153000000,measured_clock_hz=None,cold_programmed=True,ram_loaded=args.ram,
        started_utc=datetime.now(timezone.utc).isoformat())
    if args.ram: record.update(rtl_run=str(args.rtl_run.resolve()),rtl_manifest_sha256=h.sha(args.rtl_run/'manifest.json'))
    def save(): h.write_json(run/'manifest.json',record)
    def event(kind,**values):
        with (run/'events.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),kind=kind,**values))+'\n')
    for original in (Path(__file__),PLATFORM_SOURCE,h.ROOT/'scripts/fpga_lab_native.py',h.ROOT/'scripts/embench_board_evidence.py'):
        h.snapshot(original,run/'tools'/original.name)
    h.write_json(run/'tool-hashes.json',{p.name:h.sha(p) for p in (run/'tools').glob('*')})
    save(); print('RUN '+str(run),flush=True)
    client=None; did=None; opened=False; raw_all=bytearray()
    try:
        client=connect(); current=client.current_device()
        if current:
            expires=current.get('planned_end_time')
            if expires:
                deadline=datetime.fromisoformat(expires.replace('Z','+00:00'))
                if deadline.tzinfo is None: raise ValueError('Ambiguous reservation timezone')
                if (deadline-datetime.now(timezone.utc)).total_seconds()<300:
                    client.release(current['device_id']); current=None
        if not current:
            client.reserve(minutes=30)
            for _ in range(30):
                current=client.current_device()
                if current: break
                time.sleep(1)
            if not current: raise RuntimeError('Device reservation did not complete')
        record['device']=public_device(current); save()
        if 'PG2L200H' not in str(current.get('board_model')): raise ValueError('Unexpected FPGA family')
        did=current['device_id']
        start=client.firmware_download(did,bit)
        event('programming_requested',device_id=did,bitstream_sha256=record['bitstream_sha256'])
        deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            progress=client.firmware_progress(did); event('programming_progress',response=progress)
            phase=progress.get('phase') or progress.get('state')
            if phase in ('failed','error') or progress.get('isFailed') or progress.get('isWakeupFailed'): raise RuntimeError('Programming failed')
            if progress.get('isComplete') is True or phase=='complete': break
            time.sleep(1)
        else: raise TimeoutError('Programming completion was not confirmed')
        record['programming_complete']=progress; save()
        opened_result=client.serial_open(did,baud=115200); opened=True
        event('serial_open',response=opened_result)
        def poll():
            response=client.serial_read(did,length=512); event('serial_read',response=response)
            chunk=receive_bytes(response)
            raw_all.extend(chunk)
            if chunk:
                with (run/'serial.bin').open('ab') as stream: stream.write(chunk)
            return chunk
        def send(payload):
            response=client.serial_send(did,payload.hex(),mode='hex'); event('serial_send',payload_hex=payload.hex(),response=response)
            if response_body(response).get('bytesSent')!=len(payload): raise ValueError('Short serial send')
        def until(predicate,seconds):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                poll()
                if predicate(): return
                time.sleep(0.05)
            raise TimeoutError('Serial response deadline exceeded')
        # Drain boot-time bytes before a fresh command. No capture client runs concurrently.
        until(lambda:True,5)
        if args.ram:
            app=(firmware/'workloads'/args.workload/'firmware.bin').read_bytes()
            if h.sha(firmware/'workloads'/args.workload/'firmware.bin')!=row['binary_sha256']: raise ValueError('Application bytes changed')
            send(b'?'); until(lambda:b'ZBOOT READY R\n' in raw_all,15)
            transfer_start=len(raw_all)
            send(b'R'+len(app).to_bytes(4,'little'))
            for index,offset in enumerate(range(0,len(app),256)):
                send(app[offset:offset+256])
                until(lambda:raw_all[transfer_start:].count(b'K')>=index+1,15)
            until(lambda:re.search(rb'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n',raw_all[transfer_start:]) is not None,20)
            crc=re.search(rb'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n',raw_all[transfer_start:])
            if crc[1].decode()!=row['ram_crc32'] or int(crc[2],16)!=len(app): raise ValueError('Received RAM image checksum differs')
            acknowledgements=raw_all[transfer_start:transfer_start+crc.start()].count(b'K')
            if acknowledgements!=len(app)//256+1: raise ValueError('Loader acknowledgement count differs')
            record.update(ram_crc32=crc[1].decode(),ram_byte_count=len(app),loader_acknowledgements=acknowledgements)
            until(lambda:('EMBENCH READY '+args.workload+' send G\n').encode() in raw_all,20)
        else:
            # The direct port prints READY immediately after programming; settle it before G.
            deadline=time.monotonic()+5
            while time.monotonic()<deadline: poll(); time.sleep(0.1)
        boundary=len(raw_all); record['benchmark_serial_offset']=boundary; save()
        send(b'G')
        finish=('EMBENCH FINISHED '+args.workload+'\n').encode()
        until(lambda:finish in raw_all[boundary:],180)
        benchmark=bytes(raw_all[boundary:]).decode('ascii')
        parsed,frame=parse_frame(benchmark,args.workload)
        (run/'uart.log').write_text(benchmark,encoding='ascii')
        (run/'uart-frame.log').write_text(frame,encoding='ascii')
        record.update(status='passed',result=parsed,uart_sha256=h.sha(run/'uart.log'),serial_sha256=h.sha(run/'serial.bin'),
            resources=pm['report']['resources'],setup_wns_ns=timing['cpu_setup_wns_ns'],hold_wns_ns=timing['cpu_hold_wns_ns'])
    except Exception as error:
        record.update(status='failed',error=str(error)); raise
    finally:
        if client:
            if opened:
                try: client.serial_close(did); event('serial_closed')
                except Exception: event('serial_close_failed')
            client.close()
        record['finished_utc']=datetime.now(timezone.utc).isoformat()
        if (run/'events.jsonl').exists(): record['events_sha256']=h.sha(run/'events.jsonl')
        if (run/'serial.bin').exists(): record['serial_sha256']=h.sha(run/'serial.bin')
        save(); print(run,flush=True)

if __name__=='__main__': main()
