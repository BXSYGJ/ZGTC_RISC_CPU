"""Reparse native CoreMark upload, programming, UART and repeated board evidence."""
import argparse
import csv
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from uuid import uuid4
import run_embench as h
from embench_board_evidence import read
from redirect_loader_binding import contained, require
from selected_coremark_board_evidence import bind_inputs, parse
from run_embench_native import receive_bytes, response_body
from review_gateway_health import review_gateway_health


def review(run, allow_pending=False):
    run=contained(run,'results'); bm=read(run/'manifest.json'); old=bm['receipt']
    require(bm.get('status')=='board_observations_passed_pending_independent_review' and
            bm.get('hardware_executed') is True,'Completed hardware observations required')
    for name,digest in bm['artifact_hashes'].items():
        path=run/name
        require(path.resolve().is_relative_to(run) and h.sha(path)==digest,'Board artifact changed')
    current,pm,fm=bind_inputs(*(Path(old[k]) for k in
        ('physical','variants','boot','smoke','firmware','screen','full_rtl')),allow_pending=allow_pending)
    for key in ('configured_clock_hz','physical_manifest_sha256','variant_manifest_sha256',
                'boot_manifest_sha256','smoke_manifest_sha256','firmware_manifest_sha256',
                'screen_manifest_sha256','bitstream_sha256','resources','instrumentation_profile'):
        require(current[key]==old[key],'Prepared evidence identity differs: '+key)
    pending=current['full_rtl_pending_at_preparation']
    require(not pending or old['full_rtl_pending_at_preparation'],'Unexpected pending RTL state')
    firmware=Path(current['firmware']); clock=current['configured_clock_hz']
    require(bm['configured_clock_hz']==clock and bm.get('measured_clock_hz') is None,
            'Board clock basis differs')
    require(h.sha(run/'tools/check_coremark.py')==h.sha(firmware/'inputs/check_coremark.py'),
            'Board checker differs from frozen firmware checker')
    spec=importlib.util.spec_from_file_location('reviewed_board_checker',run/'tools/check_coremark.py')
    checker=importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    entries={r['configuration']:r for r in fm['firmware']}
    expected=[(label,rep) for rep in range(1,4) for label in (('V1','V0') if rep==2 else ('V0','V1'))]
    require([tuple(x) for x in bm['order']]==expected and
            [(r['configuration'],r['repetition']) for r in bm['observations']]==expected,
            'Missing, duplicate or reordered observations')
    events=[json.loads(line) for line in (run/'events.jsonl').read_text().splitlines()]
    gateway=review_gateway_health(run,bm,events)
    if 'attempts' in bm:
        require(1<=bm.get('capture_attempts',0)<=3,'Invalid capture-attempt bound')
        require([r for r in bm['attempts'] if r['status']=='passed']==bm['observations'],
                'Passing attempts and final observations differ')
        sequence=[]
        for label,rep in expected:
            group=[r for r in bm['attempts'] if (r['configuration'],r['repetition'])==(label,rep)]
            require(1<=len(group)<=bm['capture_attempts'] and
                    [r['attempt'] for r in group]==list(range(1,len(group)+1)) and
                    group[-1]['status']=='passed','Missing or reordered capture attempts')
            for row in group[:-1]:
                require(row['status']=='rejected_transport_capture' and row['error'] in
                        ('Control bytes in CoreMark frame','Non-ASCII UART capture','Serial response deadline exceeded',
                         'Incomplete or duplicated CoreMark field'),
                        'A failed correctness observation was retried')
                require((run/(row['prefix']+'-serial.bin')).is_file(),'Rejected capture evidence missing')
            sequence+=group
        require(sequence==bm['attempts'],'Capture attempts differ from declared observation order')
    rows=[]; lut=current['resources']['post_route_luts']
    for observation in bm['observations']:
        label=observation['configuration']; rep=observation['repetition']
        prefix=f'{label}-r{rep}'
        if 'attempt' in observation:
            prefix+='-a'+str(observation['attempt'])
            require(observation.get('prefix')==prefix,'Capture attempt prefix differs')
        require(observation['status']=='passed' and observation.get('correctness') is True and
                observation['cold_programmed'] is True,'Failed hardware observation')
        info=entries[label]
        require(observation['application']==info and observation['bitstream_sha256']==current['bitstream_sha256'],
                'Observation application/image identity differs')
        serial=run/(prefix+'-serial.bin'); uart=run/(prefix+'-uart.log')
        require(observation['serial_file']==serial.name and observation['uart_file']==uart.name and
                h.sha(serial)==observation['serial_sha256'] and h.sha(uart)==observation['uart_sha256'],
                'Raw serial identity differs')
        stream=serial.read_bytes(); frame_bytes=uart.read_bytes()
        require(stream[observation['benchmark_serial_offset']:]==frame_bytes,'UART frame/serial boundary differs')
        selected=[e for e in events if e.get('observation')==prefix]
        programmed=[e for e in selected if e['kind']=='programming_requested']
        require(len(programmed)==1 and programmed[0]['bitstream_sha256']==current['bitstream_sha256'],
                'Unique programming request absent')
        confirmed=[e['response'] for e in selected if e['kind']=='programming_progress' and
                   (e['response'].get('isComplete') is True or e['response'].get('phase')=='complete'
                    or e['response'].get('state')=='complete')]
        require(confirmed==[observation['programming_complete']],'Programming completion evidence differs')
        reconstructed=bytearray(); sent=[]; boundaries={}
        read_errors=0
        for event in selected:
            if event['kind']=='serial_read':
                reconstructed.extend(receive_bytes(event['response']))
            elif event['kind']=='serial_read_error':
                require(event['status'] in (502,503,504) and event.get('will_retry') is True and
                        1<=event['attempt']<=bm.get('serial_read_retries',0)<=3,
                        'Unapproved or exhausted serial retry')
                read_errors+=1
            elif event['kind']=='serial_send':
                payload=bytes.fromhex(event['payload_hex']); sent.append(payload)
                require(response_body(event['response']).get('bytesSent')==len(payload),'Short upload in raw events')
                if payload==b'G': boundaries['benchmark']=len(reconstructed)
                if len(payload)==5 and payload[:1]==b'R': boundaries['transfer']=len(reconstructed)
        app=(firmware/'firmware'/label/'firmware.bin').read_bytes()
        expected_sends=[b'?',b'R'+len(app).to_bytes(4,'little')]+[app[i:i+256] for i in range(0,len(app),256)]+[b'G']
        require(sent==expected_sends,'Raw upload bytes/command order differ from exact firmware')
        require(bytes(reconstructed)==stream,'Serial events disagree with raw capture')
        require(boundaries==dict(benchmark=observation['benchmark_serial_offset'],
                                 transfer=observation['transfer_serial_offset']),
                'Command boundaries disagree with raw events')
        before=stream[boundaries['transfer']:boundaries['benchmark']]
        crc=list(re.finditer(rb'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n',before))
        require(len(crc)==1 and crc[0][1].decode()==info['ram_crc32']==observation['ram_crc32'] and
                int(crc[0][2],16)==len(app)==observation['ram_byte_count'],'Captured RAM verification differs')
        require(before[:crc[0].start()].count(b'K')==len(app)//256+1==observation['loader_acknowledgements'],
                'Captured loader acknowledgements differ')
        require(('ZGTC COREMARK READY send G; clock='+str(clock)+' Hz\n').encode() in before,
                'Correct READY banner absent before trigger')
        result,frame,framing=parse(frame_bytes,checker,info,clock,lut)
        require(result==observation['result'] and framing==observation['framing'] and
                (run/(prefix+'-frame.log')).read_text(encoding='ascii')==frame,
                'Reparsed result/framing differs')
        if not pending:
            rtl=[r for r in current['full_rtl_receipt']['observations'] if r['configuration']==label]
            require(len(rtl)==1 and (rtl[0]['cycles'],rtl[0]['retired_instructions'])==
                    (result['cycles'],result['retired']),'Board and full-length RTL counters differ')
        rows.append(dict(configuration=label,repetition=rep,configured_clock_hz=clock,measured_clock_hz=None,
            cycles=result['cycles'],retired=result['retired'],seconds=result['seconds'],
            coremark=result['iterations_per_second'],lut=lut,coremark_per_lut=result['iterations_per_second_per_lut'],
            crc_valid=result['crc_valid'],duration_pass=result['reportable_duration'],
            efficiency_pass=result['iterations_per_second_per_lut']>=0.051,
            transient_read_errors=read_errors))
    for label in entries:
        require(len({(r['cycles'],r['retired']) for r in rows if r['configuration']==label})==1,
                'Repetition counters disagree')
    passed=all(r['efficiency_pass'] and r['duration_pass'] and r['crc_valid'] and r['lut']<9502 for r in rows)
    return dict(status='board_observations_verified_full_rtl_pending' if pending else 'board_and_full_rtl_verified',
        qualified=passed and not pending,efficiency_threshold_met=passed,full_rtl_pending=pending,
        rows=rows,receipt=current,board_manifest_sha256=h.sha(run/'manifest.json'),gateway_health=gateway,
        scope='Configured PLL throughput and exact image resources; frequency is not independently measured.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path); parser.add_argument('--allow-pending-full-rtl',action='store_true')
    args=parser.parse_args(); result=review(args.run,args.allow_pending_full_rtl)
    out=h.ROOT/'results'/('selected-coremark-board-review-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    out.mkdir(exist_ok=False)
    for name in ('review_selected_coremark_board.py','selected_coremark_board_evidence.py','review_coremark_loader_evidence.py','review_gateway_health.py'):
        h.snapshot(h.ROOT/'scripts'/name,out/'tools'/name)
    h.write_json(out/'review.json',result)
    with (out/'results.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(result['rows'][0])); writer.writeheader(); writer.writerows(result['rows'])
    h.write_json(out/'manifest.json',dict(status=result['status'],qualified=result['qualified'],
        hashes={p.relative_to(out).as_posix():h.sha(p) for p in out.rglob('*') if p.is_file()}))
    print(json.dumps(result['rows']),flush=True); print(out,flush=True)


if __name__=='__main__': main()
