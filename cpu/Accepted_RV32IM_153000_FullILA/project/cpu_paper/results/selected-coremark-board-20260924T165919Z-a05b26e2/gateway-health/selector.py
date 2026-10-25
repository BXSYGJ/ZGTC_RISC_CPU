"""Select the historically verified UART gateway using ordinary reservations."""
from datetime import datetime, timezone
import time
from fpga_lab_native import public_device


def select_healthy_gateway(client, event, artifacts, minimum_seconds=900):
    """Test assigned PG2L200H sessions with the fully qualified R58 UART loader.

    The pinned standalone beacon binary is absent locally. This control image
    is already qualified on hardware; three complete query responses establish
    session health before the caller cold-programs its benchmark image.
    """
    import json
    import run_embench as h
    from fpga_serial_reads import read_serial
    from run_embench_native import receive_bytes, response_body
    if not 300 <= minimum_seconds <= 1500:
        raise ValueError('Unsupported reservation duration requirement')
    control=h.ROOT/'results/selected-coremark-board-review-20260924T150110Z-94a8383d/review.json'
    reviewed=json.loads(control.read_text())
    receipt=reviewed['receipt']
    from pathlib import Path
    physical=Path(receipt['physical'])
    bit=physical/'implementation/generate_bitstream/pds_soc_top.sbit'
    if (not reviewed['qualified'] or reviewed['status']!='board_and_full_rtl_verified' or
            h.sha(physical/'manifest.json')!=receipt['physical_manifest_sha256'] or
            h.sha(bit)!=receipt['bitstream_sha256']):
        raise ValueError('Known UART control image qualification changed')
    artifacts=Path(artifacts); artifacts.mkdir(exist_ok=False)
    h.snapshot(control,artifacts/'control-review.json')
    h.snapshot(Path(__file__),artifacts/'selector.py')
    event('gateway_health_policy',control_review_sha256=h.sha(control),
          bitstream_sha256=h.sha(bit),serial_read_length=512,required_responses=3)
    for attempt in range(1,9):
        current=client.current_device()
        if current:
            end=datetime.fromisoformat(current['planned_end_time'].replace('Z','+00:00'))
            if end.tzinfo is None:
                raise ValueError('Ambiguous reservation timezone')
            if (end-datetime.now(timezone.utc)).total_seconds()<=minimum_seconds:
                client.release(current['device_id']); current=None
        if not current:
            client.reserve(minutes=30)
            for _ in range(30):
                current=client.current_device()
                if current: break
                time.sleep(1)
        event('gateway_health_reservation',attempt=attempt,device=public_device(current))
        if not current: continue
        did=current['device_id']; opened=False; healthy=False
        print('UART control probe '+str(attempt)+': device '+str(did),flush=True)
        def log(kind,**data): event('gateway_probe_'+kind,attempt=attempt,device_id=did,**data)
        raw=bytearray(); raw_path=artifacts/('attempt-'+str(attempt)+'-serial.bin')
        raw_path.write_bytes(b'')
        try:
            if 'PG2L200H' not in str(current.get('board_model')):
                raise ValueError('Assigned device is not the required PG2L200H family')
            client.firmware_download(did,bit)
            log('programming_requested',bitstream_sha256=h.sha(bit))
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                progress=client.firmware_progress(did); log('programming_progress',response=progress)
                phase=progress.get('phase') or progress.get('state')
                if phase in ('failed','error') or progress.get('isFailed') or progress.get('isWakeupFailed'):
                    raise RuntimeError('Control image programming failed')
                if progress.get('isComplete') is True or phase=='complete': break
                time.sleep(1)
            else: raise TimeoutError('Control image programming did not complete')
            log('serial_open',response=client.serial_open(did,baud=115200)); opened=True
            def poll():
                response=read_serial(client,did,512,3,lambda **data:log('read_error',**data))
                log('serial_read',response=response)
                chunk=receive_bytes(response); raw.extend(chunk)
                with raw_path.open('ab') as stream: stream.write(chunk)
                return chunk
            # Drain startup text, then request and verify three fresh replies.
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                if not poll(): break
            for query in range(1,4):
                boundary=len(raw)
                sent=client.serial_send(did,b'?'.hex(),mode='hex')
                log('query',query=query,serial_offset=boundary,response=sent)
                if response_body(sent).get('bytesSent')!=1: raise ValueError('Control query not sent')
                deadline=time.monotonic()+10
                while time.monotonic()<deadline:
                    chunk=poll()
                    if b'ZBOOT READY R\n' in raw[boundary:]: break
                    if not chunk: time.sleep(0.1)
                else: raise TimeoutError('Complete control UART response missing')
            healthy=True
            log('passed',serial_file=raw_path.name,serial_sha256=h.sha(raw_path),complete_query_responses=3)
        except Exception as error:
            # Do not put HTTP response bodies or authentication data in errors.
            log('failed',error_type=type(error).__name__,http_status=getattr(error,'status',None))
            print('UART control probe rejected: '+type(error).__name__,flush=True)
        finally:
            if opened:
                try: client.serial_close(did)
                except Exception: log('serial_close_failed'); healthy=False
            if not healthy:
                client.release(did); log('released')
        if healthy:
            event('gateway_health_selected',device=public_device(current),attempt=attempt,
                  control_review_sha256=h.sha(control),bitstream_sha256=h.sha(bit))
            print('UART control passed on device '+str(did),flush=True)
            return current
    raise RuntimeError('No assigned PG2L200H session passed the recorded UART control probes')


def select_known_gateway(client, event, minimum_seconds=300):
    if not 300 <= minimum_seconds <= 1500:
        raise ValueError('Unsupported reservation duration requirement')
    def usable(current):
        if current and current.get('planned_end_time'):
            end=datetime.fromisoformat(current['planned_end_time'].replace('Z','+00:00'))
            if end.tzinfo is None:
                raise ValueError('Ambiguous reservation timezone')
            return (end-datetime.now(timezone.utc)).total_seconds()>minimum_seconds
        return False
    for attempt in range(1, 9):
        current=client.current_device()
        if current and current.get('device_id')==62 and usable(current):
            if 'PG2L200H' not in str(current.get('board_model')):
                raise ValueError('Unexpected board on known gateway')
            event('gateway_selected',attempt=attempt,device=public_device(current))
            return current
        if current:
            client.release(current['device_id'])
            event('gateway_released',device_id=current['device_id'])
        client.reserve(minutes=30)
        current=None
        for _ in range(30):
            current=client.current_device()
            if current:
                break
            time.sleep(1)
        event('gateway_reservation',attempt=attempt,device=public_device(current))
        print('Gateway reservation '+str(attempt)+': '+str(current.get('device_id') if current else None),flush=True)
        if current and current.get('device_id')==62 and usable(current):
            if 'PG2L200H' not in str(current.get('board_model')):
                raise ValueError('Unexpected reserved FPGA family')
            return current
        if current:
            client.release(current['device_id'])
            event('gateway_released',device_id=current['device_id'])
    raise RuntimeError('Known-good gateway unavailable after eight automatic reservations')
