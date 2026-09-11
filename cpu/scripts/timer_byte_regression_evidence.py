import json
import re
from pathlib import Path

from early_redirect_isa_trace import verify_pair
from load_use_profile import file_hash, load_json, require


CORE_HASH = 'CE62DD68B477DCD6C752A6FB8BAC3E3397A249AC6EA59E723CB6D14D518F462A'
PARENT_HASH = 'CE62DD68B477DCD6C752A6FB8BAC3E3397A249AC6EA59E723CB6D14D518F462A'
TIMER_HASH = 'D0FD9F51FD4A068A19E7C360CAFE9FA1F838A1864CD76D4188C007DD0761571E'


def audit(root):
    root = Path(root)
    stage = root / 'build/timer-byte-compare-stage'
    parent = root / 'build/late-branch-predicate-stage'
    isa_path = stage / 'build/isa-target-paired-core-only/results.json'
    soc_path = stage / 'build/soc-paired-replay-qualified/results.json'
    isa = load_json(isa_path)
    soc = load_json(soc_path)
    require(isa['paired_cases'] == 98 and isa['executions'] == 196 and len(isa['records']) == 98, 'Incomplete paired ISA evidence')
    require(soc['paired_cases'] == 4 and soc['executions'] == 8 and len(soc['records']) == 4, 'Incomplete paired SoC evidence')
    require(isa['script_sha256'] == file_hash(root / 'build/replay_timer_byte_compare_target_isa.py'), 'ISA runner changed')
    require(isa['parameters'] == dict(ENABLE_CACHE=1,CACHE_SETS=6,ICACHE_SET_BITS=9,LOAD_USE_BUBBLE=1,FAST_ICACHE_HIT=1,DATA_OVERLAP=1,BTB_INDEX_BITS=8,EARLY_D_REQUEST=1,FAST_DCACHE_WRITE=1,FAST_DCACHE_READ=1,FETCH_OVERLAP=1,ENABLE_M=1), 'ISA parameters changed')
    require(soc['parameters'] == dict(ICACHE_SET_BITS=9,DATA_OVERLAP=1,BTB_INDEX_BITS=8,EARLY_D_REQUEST=1,FAST_DCACHE_WRITE=1,FAST_DCACHE_READ=1,FETCH_OVERLAP=1,ENABLE_PREDICTOR=1,CACHE_SET_BITS=6,ENABLE_CACHE=1,LOAD_USE_BUBBLE=1,FAST_ICACHE_HIT=1), 'SoC parameters changed')
    for report, bench in ((isa,'isa_tb.sv'),(soc,'soc_tb.sv')):
        for label, directory in (('baseline',parent),('candidate',stage)):
            inputs = sorted((directory / 'rtl').glob('*.sv'))+[directory / 'sim' / bench]
            actual = {path.relative_to(directory).as_posix():file_hash(path) for path in inputs}
            require(report['source_snapshots'][label] == actual, 'Integration source snapshot changed')
        require(report['source_snapshots']['baseline']['rtl/rv32_core.sv'] == PARENT_HASH == CORE_HASH and report['source_snapshots']['baseline']['rtl/rv32_peripherals.sv'] == '8C46872D243E7AA61B379FED21D85893C45F5466B1E8CC04C8870D239AA83F75', 'Unexpected integration parent')
        require(report['source_snapshots']['candidate'] == dict(report['source_snapshots']['baseline'],**{'rtl/rv32_peripherals.sv':TIMER_HASH}), 'Unexpected integration source delta')
    require(isa['scope'] == 'actual_i9_d6_paired_core_only_isa_timer_not_elaborated_not_certification_or_physical_score','ISA scope incorrectly includes timer')
    for label in ('baseline','candidate'):
        for uart in (0,1):
            for fault in (0,1):
                image = soc_path.parent / f'{label}_uart{uart}_fault{fault}.vvp'
                require(('timer_byte_greater' in image.read_text()) == (label == 'candidate'),'Actual SoC timer elaboration changed')
    directory = isa_path.parent
    for label in ('baseline','candidate'):
        for predictor in (0,1):
            image = directory / label / ('p'+str(predictor)+'_c1_s6.vvp')
            require('early_pair_condition' in image.read_text() and 'timer_byte_greater' not in image.read_text(), 'Actual ISA elaboration changed')
    identities = set()
    suite_counts = {}
    for record in isa['records']:
        entry = record['result']
        reference = record['baseline_result']
        identity = (record['suite'],entry['name'],entry['configuration'])
        require(identity not in identities, 'Duplicate paired ISA identity')
        identities.add(identity)
        suite_counts[record['suite']] = suite_counts.get(record['suite'],0)+1
        require(entry['configuration'] in ('p0_c1_s6','p1_c1_s6'), 'Unexpected ISA configuration')
        suite_build = root / 'build/early-direct-carry8-stage/build/isa' / isa['suites'][record['suite']]['build']
        require(file_hash(suite_build / 'results.json') == isa['suites'][record['suite']]['manifest_sha256'], 'ISA suite changed')
        firmware = suite_build / (entry['name']+'.hex')
        for label, outcome in (('baseline',reference),('candidate',entry)):
            require(outcome['name'] == entry['name'] and outcome['configuration'] == entry['configuration'] and outcome['hex_sha256'] == file_hash(firmware), 'ISA identity or firmware changed')
            log = directory / label / (outcome['name']+'_'+outcome['configuration']+'.log')
            require(file_hash(log) == outcome['log_sha256'], 'ISA raw log changed')
            matches = re.findall(r'^PASS ISA name=(\w+) cycles=(\d+) retired=(\d+) (.+)$',log.read_text(),re.M)
            require(len(matches) == 1 and matches[0][:3] == (outcome['name'],str(outcome['cycles']),str(outcome['retired'])), 'ISA counters differ from raw log')
            predictor = int(outcome['configuration'][1])
            expected = f'predictor={predictor} cache=1 sets=6 loadbubble=1 fastihit=1 m=1 overlap=1 fastdread=1 earlyd=1 btb=8 dataoverlap=1 fastdwrite=1 isets=9'
            require(matches[0][3] == expected, 'ISA raw parameters changed')
        require(entry['cycles'] == reference['cycles'] and entry['retired'] == reference['retired'] and record['cycle_delta'] == record['retired_delta'] == 0, 'ISA paired execution changed')
        require(verify_pair(directory / 'candidate',directory / 'baseline',entry,reference) == record['trace'], 'ISA raw trace or memory binding changed')
    require(suite_counts == {'rv32ui':82,'rv32um':16}, 'Incomplete ISA suite distribution')
    controls = isa['negative_controls']
    require(len(controls) == 8 and len({(entry['name'],entry['label']) for entry in controls}) == 8, 'Incomplete ISA rejection evidence')
    for entry in controls:
        log = directory / entry['label'] / (entry['name']+'.log')
        firmware = root / 'build/early-direct-carry8-stage/build/isa/20260908-084037-03b3a0d4' / (entry['name']+'.hex')
        require(file_hash(log) == entry['log_sha256'] and entry['expected_rejection'] in log.read_text() and file_hash(firmware) == entry['firmware_sha256'], 'ISA rejection evidence changed')
    identities = set()
    for record in soc['records']:
        identity = (record['firmware'],record['fault'])
        require(identity not in identities, 'Duplicate SoC identity')
        identities.add(identity)
        historical = record['firmware'] == 'historical'
        firmware_stage = root / ('build/load-use-address-plain-stage' if historical else 'build/load-route-predecode-stage')
        require(record['external_uart'] == int(not historical), 'SoC firmware UART mode changed')
        require(file_hash(firmware_stage / 'build/soc_selftest.hex') == record['hex_sha256'] and file_hash(firmware_stage / 'build/soc_selftest.elf') == record['elf_sha256'], 'SoC firmware changed')
        traces = []
        outputs = []
        for label in ('baseline','candidate'):
            stem = record['firmware']+'_'+label+'_fault'+str(record['fault'])
            log = soc_path.parent / (stem+'.log')
            trace = soc_path.parent / (stem+'.trace')
            outcome = record[label]
            require(file_hash(log) == outcome['log_sha256'] and log.read_text() == outcome['stdout'], 'SoC raw output changed')
            require(file_hash(trace) == outcome['trace_sha256'], 'SoC raw trace changed')
            traces.append(trace.read_bytes())
            outputs.append(log.read_text())
        require(traces[0] == traces[1] and outputs[0] == outputs[1] and record['raw_trace_equal'] is True, 'SoC paired execution changed')
    require(identities == {(label,fault) for label in ('historical','rebuilt') for fault in (0,1)}, 'Incomplete SoC identity coverage')
    return dict(scope='raw_core_only_ISA_and_actual_timer_SoC_not_physical_or_hardware_score',isa_pairs=98,isa_executions=196,isa_rejections=8,soc_pairs=4,soc_executions=8,isa_manifest_sha256=file_hash(isa_path),soc_manifest_sha256=file_hash(soc_path),auditor_sha256=file_hash(Path(__file__)))


if __name__ == '__main__':
    print(json.dumps(audit(Path(__file__).resolve().parents[1]),indent=2))
