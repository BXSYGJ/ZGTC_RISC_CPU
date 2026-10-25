"""Load exact application bytes over modeled UART into the accepted cached CPU."""
import argparse
from datetime import datetime, timezone
import re
from uuid import uuid4
from pathlib import Path
import run_embench as h

SETUP = r'''
        std::ifstream application(argv[3], std::ios::binary);
        if (!application) throw std::runtime_error("Cannot read application");
        std::vector<unsigned char> payload((std::istreambuf_iterator<char>(application)), std::istreambuf_iterator<char>());
        if (payload.empty() || payload.size()>45056) throw std::runtime_error("Invalid application length");
        std::vector<unsigned char> outgoing;
        outgoing.push_back('R');
        for (unsigned shift=0;shift<32;shift+=8) outgoing.push_back((payload.size()>>shift)&255);
        size_t payload_sent=std::min<size_t>(256,payload.size());
        outgoing.insert(outgoing.end(),payload.begin(),payload.begin()+payload_sent);
        size_t wire_index=0;
        uint64_t wire_start=10000;
        unsigned k_count=0, consumed_k=0;
        bool sent_g=false;
        std::string observed_uart;
'''
DRIVE = r'''
            if (wire_index < outgoing.size() && cycle >= wire_start) {
                auto elapsed=cycle-wire_start;
                if (elapsed < 320) {
                    unsigned bit_index=elapsed/32;
                    model->serial_rx=bit_index==0 ? 0 : bit_index<=8 ? ((outgoing[wire_index]>>(bit_index-1))&1) : 1;
                } else {
                    model->serial_rx=1; ++wire_index; wire_start=cycle+32;
                }
            } else model->serial_rx=1;
            if (wire_index==outgoing.size() && payload_sent<payload.size() && k_count>consumed_k) {
                consumed_k=k_count;
                size_t count=std::min<size_t>(256,payload.size()-payload_sent);
                outgoing.insert(outgoing.end(),payload.begin()+payload_sent,payload.begin()+payload_sent+count);
                payload_sent+=count; wire_start=cycle+32;
            }
            if (!sent_g && observed_uart.find(" send G\n")!=std::string::npos) {
                if (wire_index!=outgoing.size() || payload_sent!=payload.size()) throw std::runtime_error("Early application READY");
                outgoing.push_back('G'); wire_start=cycle+32; sent_g=true;
            }
'''

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('firmware_run',type=Path)
    args=parser.parse_args(); origin=args.firmware_run.resolve()
    import json
    fm=json.loads((origin/'manifest.json').read_text())
    if fm['status']!='built' or fm['protocol']!='v26': raise ValueError('Frozen v26 build required')
    run=h.ROOT/'results'/('embench-loader-rtl-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8]); run.mkdir(exist_ok=False)
    record=dict(status='running',protocol='v26',firmware_run=str(origin),firmware_manifest_sha256=h.sha(origin/'manifest.json'),results=[],
        scope='Actual UART R transfer, RAM CRC32, cache maintenance, exact paced binaries, independent cycle/retirement observers')
    def save(): h.write_json(run/'manifest.json',record)
    save(); print('RUN '+str(run),flush=True)
    try:
        for p in (origin/'inputs').rglob('*'):
            if p.is_file(): h.snapshot(p,run/'inputs'/p.relative_to(origin/'inputs'))
        sim=run/'inputs/port/sim_main.cpp'; code=sim.read_text()
        edits={
            '#include <cstdint>':'#include <cstdint>\n#include <vector>\n#include <algorithm>\n#include <iterator>',
            'if (argc != 3)':'if (argc != 4)',
            'uint32_t sequence = 0, sp = 0, minimum_sp = 65536;':SETUP+'\n        uint32_t sequence = 0, sp = 0, minimum_sp = 65536;',
            'uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;':DRIVE+'\n            uint64_t before_cycles = model->cycle_count, before_retired = model->retired_count;',
            'uart.put(char(byte)); std::cout.put(char(byte));':'uart.put(char(byte)); std::cout.put(char(byte)); observed_uart.push_back(char(byte)); if (byte==75 && !sent_g) ++k_count;'
        }
        for old,new in edits.items():
            if code.count(old)!=1: raise ValueError('Unexpected simulator structure')
            code=code.replace(old,new)
        sim.write_text(code)
        h.snapshot(__file__,run/'runner.py')
        hashes={p.relative_to(run/'inputs').as_posix():h.sha(p) for p in (run/'inputs').rglob('*') if p.is_file()}
        h.write_json(run/'source-hashes.json',hashes)
        executable=h.build_simulator(run); record['model_sha256']=h.sha(executable); save()
        for name in ('instrumentation-dummy','crc32','xgboost'):
            row=next(r for r in fm['results'] if r['workload']==name)
            work=run/name; work.mkdir()
            h.snapshot(origin/'workloads/uart-loader/firmware.hex',work/'firmware.hex')
            h.snapshot(origin/'workloads'/name/'firmware.bin',work/'application.bin')
            print('SIM '+name,flush=True)
            status=h.command([executable,work/'uart.log','2500000000',work/'application.bin'],work,'simulation',1800)
            log=(work/'simulation.log').read_text(); uart=(work/'uart.log').read_text()
            crc=re.search(r'BOOT CRC32=([0-9a-f]{8}) bytes=0x([0-9a-f]{8})\n',uart)
            result=re.search(r'EMBENCH cycles=0x([0-9a-f]{16}) retired=0x([0-9a-f]{16}) verified=1\n',uart)
            observer=re.search(r'OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)',log)
            valid=(status==0 and crc and crc[1]==row['ram_crc32'] and int(crc[2],16)==row['binary_bytes'] and result and observer
                   and tuple(int(x,16) for x in result.groups())==tuple(int(x) for x in observer.groups()[:2])
                   and 'EMBENCH FINISHED '+name+'\n' in uart)
            receipt=dict(workload=name,status='passed' if valid else 'failed',application_sha256=h.sha(work/'application.bin'),
                loader_firmware_sha256=h.sha(work/'firmware.hex'),uart_sha256=h.sha(work/'uart.log'),simulation_log_sha256=h.sha(work/'simulation.log'))
            if valid: receipt.update(cycles=int(result[1],16),retired_instructions=int(result[2],16),minimum_sp=int(observer[3]),ram_crc32=crc[1])
            record['results'].append(receipt); save()
            if not valid: raise ValueError('Loader RTL smoke failed: '+name)
        record['status']='passed'
    except Exception as error: record.update(status='failed',error=str(error)); raise
    finally: save()
    print(run,flush=True)

if __name__=='__main__': main()
