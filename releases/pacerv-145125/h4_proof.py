"""Strict byte-bound Loop16 H3 donor and exact H4 default-change provenance."""
from __future__ import annotations
import hashlib
import json
import re

H6='47573ae5b351a71c6bc453901822ca8910e7696c170bca71ecd77fb8eb5b0993'
H3='222223a16f58695fa149a0b709acaebfa2bab479b0acea916dfef76c9e8581ba'
H4='b362dea594ba68f5eba4274ee054a5ec4d09e57b2695c695f1b2bdf849e8eca0'
CORE='5e81f9c56246e502b43c6a48c14342dbb16ac437788ac01d00a482d9a06ca84b'
def require(condition,message):
    if not condition:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()

def verify_h4(read,actual_hash):
    prefix='evidence/rtl/load_simple_loop16_h4/'
    donor='evidence/rtl/load_simple_loop16/'
    loop='evidence/rtl/loop16/'
    load=lambda name:json.loads(read(name).decode('utf-8-sig'))
    binding=load('evidence/rtl/H4_BINDING.json')
    require(binding['schema']=='pacerv-h4-source-chain/v1','H4bindingschema')
    for relative,expected in binding['files'].items():
        require('..' not in relative.split('/') and digest(read('evidence/rtl/'+relative))==expected,'H4sourceorloghash:'+relative)
    change=load(prefix+'CHANGE.json')
    before,after=read(prefix+'BASELINE_FILE.sv'),read(prefix+'rv32_btb.sv')
    require(digest(before)==H3==change['baseline_btb_sha256'],'H4baselineH3source')
    require(digest(after)==H4==actual_hash==change['modified_btb_sha256'],'H4actualBTBsource')
    require(after==read(prefix+'MODIFIED_FILE.sv'),'H4modifiedcopies')
    old,new=before.decode('utf-8-sig'),after.decode('utf-8-sig')
    require(old.count('parameter integer HISTORY_BITS=3,')==new.count('parameter integer HISTORY_BITS=4,')==1,'H4singleparameter')
    require(new.replace('parameter integer HISTORY_BITS=4,','parameter integer HISTORY_BITS=3,',1)==old,'H4exactparameterinverse')
    donor_change=load(donor+'CHANGE.json')
    require(digest(read(donor+'BASELINE_FILE.sv'))==H6==donor_change['baseline_btb_sha256'],'H6donorbaseline')
    require(read(donor+'MODIFIED_FILE.sv')==read(donor+'rv32_btb.sv')==before,'H3exactdonorreplacement')
    require(donor_change['modified_btb_sha256']==H3 and donor_change['retained_core_sha256']==CORE,'H3donorchain')
    loop_change=load(loop+'CHANGE.json')
    require(read(loop+'rv32_btb.sv')==before and loop_change['candidate_sha256']==H3,'OriginalLoop16donorexact')
    require(digest(read(loop+'BASELINE_FILE.sv'))==loop_change['baseline_sha256'],'OriginalLoop16baselinebinding')
    require(change['retained_core_sha256']==CORE==digest(read('physical_inputs/rtl/rv32_core.sv')),'H4retainedSelectiveLoadCore')
    require(len(change['rtl'])==17 and len(change['physical_rtl'])==18,'H4overlaycounts')
    require(change['rtl']['rv32_btb.sv']==change['physical_rtl']['rv32_btb.sv']==H4,'H4overlayBTB')
    for filename,expected in change['physical_rtl'].items():
        require(digest(read('physical_inputs/rtl/'+filename))==expected,'H4exactphysicalsource:'+filename)
        if filename!='rv32_btb.sv':require(expected==donor_change['physical_rtl'][filename],'H4onlyBTBchanged:'+filename)
    for filename,expected in change['rtl'].items():
        require(expected==change['physical_rtl'][filename],'H4common17overlay:'+filename)
    evidence=load(prefix+'VERIFICATION.txt')
    if 'historical_short_verification_sha256' in binding:
        frozen=read(prefix+'SHORT_VERIFICATION_FROZEN.txt')
        require(digest(frozen)==binding['historical_short_verification_sha256'],'H4historicalshortreceipt')
        historical=json.loads(frozen.decode('utf-8-sig'))
        for field in ['changed_field','source_chain','core','predictor','screens']:
            require(evidence[field]==historical[field],'H4preservedshortproof:'+field)
        long=load(prefix+'LONG_FINAL_AUDIT.json')
        require(long['status']=='PASS_BOTH_ACTUAL6000_GT3P5' and long['pending']==[],'H4actual6000receiptcomplete')
    core=load(prefix+'CORE_VERIFICATION.json')
    require(core==evidence['core'] and core['status']=='PASS' and len(core['core'])==3,'H4BMRcorebinding')
    traces={}
    for test in core['core']:
        label=test['label']
        require(label in ['BASELINE','MODIFIED','ROLLBACK'],'H4BMRlabels')
        require(test['compile_exit_status']==test['exit_status']==0 and test['input']['core']==CORE and test['input']['mode']==2,'H4coreexitmodebinding')
        require(test['input']['sha256']==(H4 if label=='MODIFIED' else H3),'H4coreBTBinputhash')
        require('-Pcore_token_tb.LOAD_ALU_MODE=2' in test['compile_command'],'H4SelectiveLoadCoreMode')
        literal=read(prefix+label.lower()+'-core.log').decode('utf-8')
        require(literal==test['literal_output'] and 'CORE_TOKEN_PASS early=1 mode=1 scenarios=23' in literal,'H4actual23corelog')
        traces[label]=[line for line in literal.splitlines() if line.startswith('ARCH ')]
    require(len(traces['BASELINE'])==591 and traces['BASELINE']==traces['MODIFIED']==traces['ROLLBACK'],'H4architecture23equal')
    require(core['core'][0]['literal_output']==core['core'][2]['literal_output'],'H4rollbackfullcycles')
    rollback=load(prefix+'ROLLBACK_RESULT.json')
    require(rollback['ExitStatus']==0 and rollback['RestoredSHA256'].lower()==H3 and rollback['InputModifiedSHA256'].lower()==rollback['ActiveModifiedSHA256'].lower()==H4,'H4actualrollbackreceipt')
    require('SHA256='+H3.upper() in rollback['LiteralOutput'] and digest(read(prefix+'rollback_sources/rv32_btb.sv'))==H3,'H4actualrollbacksource')
    predictor=load(prefix+'PREDICTOR_CHECKS.json')
    require(predictor==evidence['predictor'] and predictor['status']=='PASS' and len(predictor['tests'])==6,'H4predictorreceiptbinding')
    models=[test for test in predictor['tests'] if test['label'] in ['BASELINE','MODIFIED','ROLLBACK']]
    require(len(models)==3,'H4loopmodel3')
    for test in models:
        label=test['label'];literal=read(prefix+label.lower()+'-loop-model.log').decode('utf-8')
        require(test['compile']['exit_status']==test['run']['exit_status']==0 and test['run']['literal_output']==literal,'H4loopmodellog')
        require(test['history_bits']==(4 if label=='MODIFIED' else 3) and 'LOOP_PREDICTOR_PASS checks=3902' in literal,'H4loopmodel3902')
    random=[test for test in predictor['tests'] if test['label']=='H4_default_equals_original_explicit_H4']
    expected={(4,16,0,0),(8,16,1,1),(4,32,4,1)}
    seen=set()
    for test in random:
        p=test['parameters'];config=tuple(p[k] for k in ['INDEX_BITS','ADDRESS_BITS','RETURN_STACK_DEPTH','HASH_INDEX']);seen.add(config)
        require(test['compile']['exit_status']==test['run']['exit_status']==0,'H4defaultrandomexit')
        log='history-default-'+'-'.join(map(str,config))+'.log'
        literal=read(prefix+log).decode('utf-8')
        require(test['run']['literal_output']==literal and 'BTB_HISTORY_DEFAULT_EQ_PASS' in literal,'H4defaultrandomlog')
        checks=re.search(r'checks=(\d+)',literal);require(checks and int(checks[1])>=40000,'H4defaultrandomcoverage')
    require(seen==expected,'H4threeconfigurations')
    tb=read(prefix+'history_default_tb.sv').decode()
    require('reference_btb #(.HISTORY_BITS(4),' in tb and 'rollback_btb #(.HISTORY_BITS(4),' in tb and '!==' in tb and '$random' in tb,'H4defaultvsExplicitH4ports')
    require(read(prefix+'reference_btb.sv').decode().replace('module reference_btb #(','module rv32_btb #(',1)==old,'H4randomreferenceproduction')
    require(read(prefix+'rollback_btb.sv').decode().replace('module rollback_btb #(','module rv32_btb #(',1)==old,'H4randomrollbackproduction')
    return dict(proposal='load_simple_loop16_h4',module='rv32_btb.sv',baseline_sha256=H3,modified_sha256=H4,core_scenarios=23,loop_model_cases_per_variant=3902,random_default_configurations=3,source_chain=['H6:'+H6,'H3Loop16:'+H3,'H4Loop16:'+H4],change_sha256=digest(read(prefix+'CHANGE.json')),verification_sha256=digest(read(prefix+'VERIFICATION.txt')),binding_sha256=digest(read('evidence/rtl/H4_BINDING.json')))
