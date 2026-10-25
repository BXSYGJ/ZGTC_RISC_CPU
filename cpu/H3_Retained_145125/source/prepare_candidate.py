"""Freeze H3-O and create its isolated retained-eligibility implementation."""
from __future__ import annotations

import difflib
import hashlib
import json
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
PAPER = TASK.parents[1]
PARENT = PAPER / 'variants/dual-release-area-optimization/h3-alu32-queryhalves-ge64-snapshot-native4-early-read'
CANDIDATE = TASK / 'source/h3o-retained-token'
PARENT_RECEIPT = PAPER / 'ccfa-workfiles/dual-release-area-optimization/h3-storage/snapshot-native4-early-read/CANDIDATE_SOURCE.json'
MANUSCRIPT = PAPER / 'research/micpro-submission-20261003/manuscript'


def sha(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def patch(value: bytes, old: bytes, new: bytes) -> bytes:
    assert value.count(old) == 1, f'Unique structural anchor missing: {old[:100]!r}'
    changed = value.replace(old, new, 1)
    assert changed.replace(new, old, 1) == value
    return changed


def main() -> int:
    assert sha(PARENT_RECEIPT) == '93558bb8e1a67c312ac502901b6bd16b3f49782e2f7f12d98879cd2182fd2819'
    parent_receipt = json.loads(PARENT_RECEIPT.read_text(encoding='utf-8-sig'))
    actual = {p.relative_to(PARENT).as_posix(): sha(p) for p in PARENT.rglob('*') if p.is_file()}
    assert actual == parent_receipt['candidate_source_sha256'], 'H3-O source inventory changed'
    receipt_path = TASK / 'SOURCE_IDENTITY.json'
    assert not receipt_path.exists() and not CANDIDATE.exists(), 'Candidate already prepared; preserve frozen inputs'
    shutil.copytree(PARENT, CANDIDATE)
    changed = []
    inverses = []

    def edit(name: str, edits: list[tuple[str, str]]) -> None:
        path = CANDIDATE / name
        before = path.read_bytes()
        newline = b'\r\n' if b'\r\n' in before else b'\n'
        anchors = [(old.encode().replace(b'\n', newline), new.encode().replace(b'\n', newline)) for old, new in edits]
        after = before
        for old, new in anchors:
            after = patch(after, old, new)
        inverse = after
        for old, new in reversed(anchors):
            inverse = patch(inverse, new, old)
        assert inverse == before, name
        path.write_bytes(after)
        changed.append(dict(relative_path=name, parent_sha256=hashlib.sha256(before).hexdigest(),
                            candidate_sha256=sha(path), structural_inverse_exact=True))
        inverses.append(dict(relative_path=name, edits=[dict(old=old, new=new) for old, new in edits]))
        (TASK / 'analysis' / (Path(name).stem + '.patch')).write_text(
            ''.join(difflib.unified_diff(before.decode('utf-8').splitlines(True), after.decode('utf-8').splitlines(True),
                                        fromfile='H3-O/' + name, tofile='H3-O-token/' + name)), encoding='utf-8')

    edit('rtl/rv32_core.sv', [
        ('    parameter integer EARLY_D_REQUEST=0,',
         '    parameter integer EARLY_D_REQUEST=0,\n    parameter integer RETAIN_MUL_ELIGIBILITY=1,'),
        ('    always @(posedge clk or negedge rst_n) begin\n        if(!rst_n) mul_precomputed<=0;\n        else mul_precomputed<=mul_precompute;\n    end',
         '    // The EX slot owns an admitted preparation until consumption or cancellation.\n'
         '    // Admission already excludes older EX/MEM operand writers. The product\n'
         '    // bank is held by the same token; no second operand or result bank is needed.\n'
         '    wire mul_request_accept=ex_can_fire && ex_muldiv && !execute_common_exception &&\n'
         '        !muldiv_started && muldiv_ready;\n'
         '    always @(posedge clk or negedge rst_n) begin\n'
         '        if(!rst_n) mul_precomputed<=0;\n'
         '        else if(RETAIN_MUL_ELIGIBILITY==0) mul_precomputed<=mul_precompute;\n'
         '        else if(mem_flush || frontend_barrier) mul_precomputed<=0;\n'
         '        else if(mul_precompute) mul_precomputed<=1;\n'
         '        else if(mul_request_accept || ex_fire || !ex_valid || !ex_muldiv ||\n'
         '            execute_common_exception || muldiv_started) mul_precomputed<=0;\n'
         '    end'),
        ('        rv32_muldiv #(.PRECOMPUTE(1)) unit(',
         '        rv32_muldiv #(.PRECOMPUTE(1),.RETAIN_PREPARATION(RETAIN_MUL_ELIGIBILITY)) unit('),
    ])
    edit('rtl/rv32_muldiv.sv', [
        ('module rv32_muldiv #(parameter integer PRECOMPUTE=0) (',
         'module rv32_muldiv #(parameter integer PRECOMPUTE=0, parameter integer RETAIN_PREPARATION=0) ('),
        ('        end else if(state==IDLE) begin\n            product_low_low<=req_operand_a[15:0]*req_operand_b[15:0];',
         '        end else if(state==IDLE && !(RETAIN_PREPARATION!=0 && PRECOMPUTE!=0 && req_precomputed)) begin\n'
         '            // The owner token protects all four partial products during a wait.\n'
         '            product_low_low<=req_operand_a[15:0]*req_operand_b[15:0];'),
    ])
    candidate_hashes = {p.relative_to(CANDIDATE).as_posix(): sha(p) for p in CANDIDATE.rglob('*') if p.is_file()}
    assert set(candidate_hashes) == set(actual)
    assert {name for name in actual if actual[name] != candidate_hashes[name]} == {'rtl/rv32_core.sv', 'rtl/rv32_muldiv.sv'}
    archive = TASK / 'baseline/prior-manuscript-source-and-PDFs.zip'
    assert not archive.exists()
    prior_preflight = json.loads((PAPER / 'ccfa-workfiles/vex-feature-matched-comparison/analysis/FINAL_BUILD_AUTHORIZATION.json').read_text(encoding='utf-8-sig'))
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as bundle:
        for name in prior_preflight['source_and_asset_sha256']:
            bundle.write(MANUSCRIPT / name, 'manuscript/' + name)
        for name in ('main_native_vex.pdf', 'supplementary_native_vex.pdf'):
            bundle.write(MANUSCRIPT / name, 'manuscript/' + name)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
    receipt = dict(schema='h3o-retained-token-source/v1', frozen_utc=datetime.now(timezone.utc).isoformat(),
                   status='isolated_candidate_frozen_validation_pending', parent=PARENT.as_posix(), candidate=CANDIDATE.as_posix(),
                   parent_receipt_sha256=sha(PARENT_RECEIPT), parent_source_sha256=actual,
                   candidate_source_sha256=candidate_hashes, changed_files=changed,
                   inverse_edits=inverses, complete_source_file_count=len(actual),
                   no_functionality_removed=True, cache_peripheral_CSR_memory_geometry_unchanged=True,
                   token_owner='The admitted low-word MUL instruction in the in-order EX slot',
                   baseline_archive=archive.as_posix(), baseline_archive_sha256=sha(archive),
                   supplied_basis=dict(preparation_available_cycles=1, interaction_predictor_counts={'matmult-int':183219, 'edn':102283, 'xgboost':0},
                                       unconsumed_eligible_preparations={'matmult-int':{'issue_on':3978,'issue_off':187200}, 'edn':{'issue_on':0,'issue_off':102295}, 'xgboost':{'issue_on':0,'issue_off':0}},
                                       independently_reverified=False, authority='User-provided supporting basis; no re-verification required'),
                   new_measurements_claimed=False, PDF_built=False)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    state = dict(schema='h3o-retained-token-task/v1', stage='classification-and-candidate-component-validation',
                 objective_tasks=['Classify, revise and cross-check the manuscript to make H3-O the default system; H3 remains an optimization baseline',
                                  'Implement and fully evaluate retained eligibility on H3-O and revise the mechanism argument from actual evidence'],
                 source_identity_sha256=sha(receipt_path), supplied_basis_accepted_without_reverification=True,
                 global_string_replacement_allowed=False, candidate_qualified=False,
                 manuscript_classification_complete=False, manuscript_revisions_complete=False,
                 PDF_build_allowed=False, required_gates=['classification','component-correctness','full-ISA',
                 'H3-O-mechanism-controls','full-public-suite','retention-by-issue-interaction','full-CoreMark',
                 'routed-resource-timing','real-board','independent-evidence-audit','manuscript-revision-crosscheck'],
                 completed_gates=[], remaining_technical_work=['Candidate validation and full evaluation','H3-O evidence migration','Classified manuscript revision and final review'])
    (TASK / 'TASK_STATE.json').write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(status=receipt['status'], candidate=receipt['candidate'], files=len(actual),
                          changed_files=changed, source_receipt_sha256=sha(receipt_path)), indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (OSError, UnicodeError, ValueError, AssertionError, zipfile.BadZipFile) as error:
        print(f'Candidate preparation failed: {error}', file=sys.stderr)
        raise SystemExit(1)
