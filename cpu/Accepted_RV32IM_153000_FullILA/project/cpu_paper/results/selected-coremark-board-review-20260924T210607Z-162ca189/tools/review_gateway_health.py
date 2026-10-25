"""Reconstruct the UART control probe without contacting the remote lab."""
from pathlib import Path
import json
import run_embench as h
from run_embench_native import receive_bytes, response_body


def review_gateway_health(run, manifest, events):
    if manifest.get('gateway_selection')!='qualified_control_probe':
        return None  # Historical records predate this additional gate.
    root=Path(run)/'gateway-health'
    control=json.loads((root/'control-review.json').read_text())
    if not control.get('qualified') or control.get('status')!='board_and_full_rtl_verified':
        raise ValueError('UART control is not jointly qualified')
    selected=[e for e in events if e['kind']=='gateway_health_selected']
    if len(selected)!=1 or selected[0]['device']!=manifest['device']:
        raise ValueError('UART control and benchmark device differ')
    selected=selected[0]; attempt=selected['attempt']; did=selected['device']['device_id']
    if 'PG2L200H' not in str(selected['device'].get('board_model')):
        raise ValueError('Wrong UART control FPGA family')
    if (selected['control_review_sha256']!=h.sha(root/'control-review.json') or
            selected['bitstream_sha256']!=control['receipt']['bitstream_sha256']):
        raise ValueError('UART control image identity differs')
    probe=[e for e in events if e.get('attempt')==attempt and e.get('device_id')==did
           and e['kind'].startswith('gateway_probe_')]
    programmed=[e for e in probe if e['kind']=='gateway_probe_programming_requested']
    complete=[e for e in probe if e['kind']=='gateway_probe_programming_progress' and
              (e['response'].get('isComplete') is True or e['response'].get('phase')=='complete'
               or e['response'].get('state')=='complete')]
    if len(programmed)!=1 or programmed[0]['bitstream_sha256']!=selected['bitstream_sha256'] or len(complete)!=1:
        raise ValueError('UART control programming evidence missing')
    raw=bytearray(); boundaries=[]
    for entry in probe:
        if entry['kind']=='gateway_probe_serial_read': raw.extend(receive_bytes(entry['response']))
        if entry['kind']=='gateway_probe_query':
            if entry['serial_offset']!=len(raw) or response_body(entry['response']).get('bytesSent')!=1:
                raise ValueError('UART control query boundary or send count differs')
            boundaries.append((entry['query'],len(raw)))
    if [q for q,_ in boundaries]!=[1,2,3]: raise ValueError('Missing UART control queries')
    for index,(_,start) in enumerate(boundaries):
        end=boundaries[index+1][1] if index+1<len(boundaries) else len(raw)
        if b'ZBOOT READY R\n' not in raw[start:end]: raise ValueError('Complete UART control response missing')
    passed=[e for e in probe if e['kind']=='gateway_probe_passed']
    if len(passed)!=1 or passed[0]['complete_query_responses']!=3:
        raise ValueError('UART control pass record missing')
    path=root/('attempt-'+str(attempt)+'-serial.bin')
    if passed[0]['serial_file']!=path.name or path.read_bytes()!=raw or h.sha(path)!=passed[0]['serial_sha256']:
        raise ValueError('UART control raw capture differs')
    if any(e['kind'] in ('gateway_probe_failed','gateway_probe_serial_close_failed') for e in probe):
        raise ValueError('Selected UART control probe failed')
    return dict(device_id=did,attempt=attempt,complete_query_responses=3,
                control_bitstream_sha256=selected['bitstream_sha256'],raw_sha256=h.sha(path))
