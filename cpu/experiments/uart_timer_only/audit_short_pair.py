import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build/regfile-valid-fanout-stage/scripts'))
from run_coremark_compiled import check_simulation_result, file_hash, verify_artifacts


def audit(stage):
    binding = json.loads((stage / 'input-binding.json').read_text(encoding='utf-8-sig'))
    if binding['ClockHz'] != 157500000 or binding['ScoreQualified'] or binding['HardwareValidated']:
        raise ValueError('Wrong candidate scope')
    for relative, expected in binding['Files'].items():
        if file_hash(stage / relative) != expected:
            raise ValueError('Candidate stage changed: ' + relative)
    references = {False: '20260909-124427-6703b76c', True: '20260909-124442-609daef4'}
    results = []
    for validation, reference_id in references.items():
        matching = []
        for directory in (stage / 'build/compiled').iterdir():
            manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8-sig'))
            firmware = manifest['FirmwareBuild']
            if manifest['SimulationPassed'] and firmware['Iterations'] == 10 and firmware['ConsoleDelayCycles'] == 0 and firmware['ValidationRun'] == validation:
                matching.append((directory, manifest))
        if len(matching) != 1:
            raise ValueError('Need one unambiguous passed short run per seed')
        directory, manifest = matching[0]
        verify_artifacts(directory, manifest)
        for relative, expected in manifest['SourceSnapshot'].items():
            if file_hash(stage / relative) != expected:
                raise ValueError('Short simulation differs from staged source: ' + relative)
        firmware_path = stage / 'build' / (manifest['FirmwareBuild']['RunName'] + '.hex')
        if file_hash(firmware_path) != manifest['FirmwareSha256']:
            raise ValueError('Short firmware binding changed')
        measured = check_simulation_result((directory / 'coremark.sim.uart').read_text(), manifest['FirmwareBuild'], manifest['HardwareParameters'], True)
        reference = ROOT / 'build/regfile-valid-fanout-stage/build/compiled' / reference_id
        reference_manifest = json.loads((reference / 'manifest.json').read_text(encoding='utf-8-sig'))
        verify_artifacts(reference, reference_manifest)
        expected = check_simulation_result((reference / 'coremark.sim.uart').read_text(), reference_manifest['FirmwareBuild'], reference_manifest['HardwareParameters'], True)
        if measured != expected:
            raise ValueError('Candidate short result differs from accepted reference')
        results.append(dict(validation_run=validation, build=directory.name, reference=reference_id,
                            result=measured, firmware_sha256=manifest['FirmwareSha256'],
                            manifest_sha256=file_hash(directory / 'manifest.json')))
    return dict(clock_hz=157500000, short_pair_identical=True, hardware_validated=False, full_score_qualified=False,
                input_binding_sha256=file_hash(stage / 'input-binding.json'), results=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', type=Path)
    arguments = parser.parse_args()
    result = audit(arguments.stage)
    (arguments.stage / 'short-qualification.json').write_text(json.dumps(result, indent=2) + chr(10), encoding='utf-8')
    print(json.dumps(result, indent=2))
