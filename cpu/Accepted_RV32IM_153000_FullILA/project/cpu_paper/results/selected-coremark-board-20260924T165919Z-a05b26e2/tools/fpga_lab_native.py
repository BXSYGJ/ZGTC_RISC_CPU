"""Use the inspected native client with the existing Chrome session in memory.

No credentials or tokens are printed or saved. Upstream remains pristine.
"""
import importlib.util
from pathlib import Path
import sys
from browser_cdp import Chrome

ROOT=Path(__file__).resolve().parents[1]
PLATFORM_SOURCE=ROOT/'results/fpga-lab-inspection-20260918-155258/upstream/tool/fpga_lab/fpga_lab_server/platform.py'
ORIGIN='http://www.logicmatrixsemi.com:5174'

def connect(cdp_port=19477):
    chrome=Chrome(cdp_port)
    try:
        entries=chrome.call('DOMStorage.getDOMStorageItems',{'storageId':{'securityOrigin':ORIGIN,'isLocalStorage':True}})['entries']
    finally: chrome.close()
    storage=dict(entries)
    spec=importlib.util.spec_from_file_location('inspected_fpga_platform',PLATFORM_SOURCE)
    module=importlib.util.module_from_spec(spec)
    previous=sys.dont_write_bytecode; sys.dont_write_bytecode=True
    try: spec.loader.exec_module(module)
    finally: sys.dont_write_bytecode=previous
    client=module.PlatformClient(base_url=ORIGIN,session_file=None)
    client.token=storage.get('auth_token') or storage.get('token')
    client.refresh_token=storage.get('refresh_token')
    if not client.is_authenticated():
        client.close(); raise RuntimeError('Existing FPGA Lab session is unavailable')
    return client

def public_device(current):
    if not current: return None
    keys=('device_id','device_number','device_name','name','board_model','status','duration_minutes','planned_end_time','start_time')
    return {key:current.get(key) for key in keys}

if __name__=='__main__':
    import argparse
    import json
    parser=argparse.ArgumentParser(description='Read FPGA Lab session readiness and current device through Google Chrome.')
    parser.add_argument('--cdp-port',type=int,default=19477)
    args=parser.parse_args()
    client=connect(args.cdp_port)
    try: print(json.dumps(dict(authenticated=True,current=public_device(client.current_device())),ensure_ascii=True,indent=2))
    finally: client.close()
