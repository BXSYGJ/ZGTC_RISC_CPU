"""Standalone standard-library SG30 verifier for an extracted root or ZIP."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,re,zipfile,sys
sys.dont_write_bytecode=True
CORE_SL='5e81f9c56246e502b43c6a48c14342dbb16ac437788ac01d00a482d9a06ca84b'
CORE_KEEP='9896d2d8177cd69adda9a4399839023dac5a37d2343e5e0e74d117ddf152a411'
CORE_RANGE='8af95f92009be4979e23fa0bee77eff3bc6858357173470a0bdf7db75326c416'
BTB_SINGLE='13aa9b1196adc482149b3414f62d752e787ded7a9b0bf06438b28e9be8a563c8'
SIM_ID='5bfd35fb3ce5591c17d5b0f5a020662b3d4a7152b83cff437c7010a5f3be1778'
BIT='381a005b52f37eb7411bb46e98dc06b4ea1525ab4a2a21117f3fcde35836449b'
OPTIONS='-dc_duplication false -plc_decongestion 0 -gplace_seed 2 -logic_optimize_lut6d_combing_strategy 1'
def require(ok,message):
    if not ok:raise ValueError(message)
def digest(data):return hashlib.sha256(data).hexdigest()
def safe(name):
    p=PurePosixPath(name)
    require(bool(name) and not p.is_absolute() and '..' not in p.parts and ':' not in name and chr(92) not in name and p.as_posix()==name,'Unsafe member: '+name)
    return name
def parse(data):return json.loads(data.decode('utf-8-sig'))
def pass_receipt(v,token='SAT proof finished - no model found: SUCCESS!'):
    require(v['exit_status']==0 and token in v['literal_output'],'Proof receipt: '+token)
def core_bmr(read,prefix,before,after,btb=None):
    c=parse(read(prefix+'CORE_VERIFICATION.json'));tests=c.get('tests',c.get('core'))
    require(c['status']=='PASS' and len(tests)==3,'Core BMR count')
    traces=[];full=[]
    for t,label in zip(tests,['BASELINE','MODIFIED','ROLLBACK']):
        require(t['label']==label and t['compile_exit_status']==t['exit_status']==0,'Core BMR exits')
        inp=t['input']; expected=after if label=='MODIFIED' else before
        require(inp.get('core_sha256',inp.get('sha256'))==expected and inp['mode']==2,'Core BMR source/mode')
        if btb:require(inp.get('btb_sha256')==btb,'Core BMR BTB')
        literal=read(prefix+label.lower()+'-core.log').decode('utf-8')
        require(literal==t['literal_output'] and 'CORE_TOKEN_PASS early=1 mode=1 scenarios=23' in literal,'Core actual log')
        traces.append([l for l in literal.splitlines() if l.startswith('ARCH ')]);full.append(literal)
    require(len(traces[0])==591 and traces[0]==traces[1]==traces[2] and full[0]==full[1]==full[2],'591 ARCH and complete cycles equality')
    rr=parse(read(prefix+'ROLLBACK_RESULT.json'))
    require(rr.get('exit_status',rr.get('ExitStatus'))==0 and rr.get('restored_sha256',rr.get('RestoredSHA256','')).lower()==before,'Actual rollback binding')
    return c
def verify_chains(read):
    load=lambda p:parse(read(p))
    # Replay the original strict H6 -> H3 donor -> H4 proof against its historical snapshot.
    proxy=lambda p:read(p.replace('physical_inputs/rtl/','evidence/ancestors/H4/rtl/',1)) if p.startswith('physical_inputs/rtl/') else read(p)
    verify_h4(proxy,H4)
    sl='evidence/rtl/load_simple/'
    ch=load(sl+'CHANGE.json');ev=load(sl+'VERIFICATION.txt');direct=load(sl+'DIRECTED_VERIFICATION.json')
    require(digest(read(sl+'rv32_core.sv'))==CORE_SL==ch['candidate_sha256'],'SelectiveLoad original source')
    require(direct['architectural_match'] and direct['all_exit_zero'] and direct['formal_add_xor_all_inputs'] and direct['scenarios']==23,'SelectiveLoad original architecture')
    pass_receipt(ev['formal']);pass_receipt(load(sl+'DECODER_CLASSIFICATION.json'))
    require(all(x['expected_failure_observed'] and x['exit_status']!=0 for x in load(sl+'NEGATIVE_CONTROLS.json')),'SelectiveLoad negative controls')
    for t in ev['core_tests']:
        require(t['compile']['exit_status']==t['run']['exit_status']==0 and 'scenarios=23' in t['run']['literal_output'],'SelectiveLoad BMR')
    # Single-write RAM preserves H4 behavior. Full literal sources and production-state proofs are archived.
    sw='evidence/rtl/loop16_h4_single_write/'
    c=load(sw+'CHANGE.json');before=read(sw+'BASELINE_FILE.sv');after=read(sw+'MODIFIED_FILE.sv')
    require(digest(before)==H4==c['baseline_sha256'] and digest(after)==BTB_SINGLE==c['modified_sha256'],'Single-write H4 parent and production source')
    require(c['before']==before.decode('utf-8') and c['after']==after.decode('utf-8'),'Single-write full source binding')
    require(after==read(sw+'rv32_btb.sv')==read('physical_inputs/rtl/rv32_btb.sv'),'Single-write actual BTB')
    sh=load(sw+'SHORT_VERIFICATION_FROZEN.txt');formal=sh['production_state_transition_and_induction']
    require(formal['status']=='PASS' and formal['source_text_bound'] and formal['all_binary_current_states'] and formal['all_next_state_bits_compared'] and formal['sequential_induction_unbounded'],'Single-write source/induction scope')
    require({x['address_bits'] for x in formal['configurations']}=={8,16,32},'Single-write formal configurations')
    for x in formal['configurations']:
        pass_receipt(x['transition']);pass_receipt(x['sequence'],'Induction step proven: SUCCESS!')
    pass_receipt(sh['four_state']['run'],'LOOP_DATA_FOUR_STATE_PASS')
    bmr=load(sw+'CORE_VERIFICATION.json');require(bmr['modified_full_cycle_equal'] and bmr['architecture_lines']==591,'Single-write BMR full cycles')
    for t in bmr['core']:
        require(t['compile_exit_status']==t['exit_status']==0 and t['input']['core']==CORE_SL,'Single-write core binding')
        require(t['input']['sha256']==(BTB_SINGLE if t['label']=='MODIFIED' else H4),'Single-write BMR source')
        require(read(sw+t['label'].lower()+'-core.log').decode()==t['literal_output'],'Single-write log bytes')
    rr=load(sw+'ROLLBACK_RESULT.json');require(rr['ExitStatus']==0 and rr['RestoredSHA256'].lower()==H4,'Single-write rollback')
    # Attribute-only target boundary, exact inverse to the complete SelectiveLoad core.
    keep='evidence/rtl/loop16_h4_ram_target_keep/'
    c=load(keep+'CHANGE.json');b=read(keep+'BASELINE_FILE.sv');a=read(keep+'MODIFIED_FILE.sv')
    require(digest(b)==CORE_SL==c['baseline_sha256'] and digest(a)==CORE_KEEP==c['modified_sha256'],'Keep source chain')
    text=a.decode('utf-8');needle='(* syn_keep=1 *) wire [31:0] frontend_direct_target='
    require(text.count(needle)==1 and text.replace(needle,'wire [31:0] frontend_direct_target=',1)==b.decode('utf-8'),'Keep exact attribute inverse')
    core_bmr(read,keep,CORE_SL,CORE_KEEP,BTB_SINGLE)
    # Memory range branch: retain the unknown-fault fallback and every other byte.
    ran='evidence/rtl/loop16_h4_ram_memory_range/'
    c=load(ran+'CHANGE.json');b=read(ran+'BASELINE_FILE.sv');a=read(ran+'MODIFIED_FILE.sv')
    require(digest(b)==CORE_KEEP==c['baseline_sha256'] and digest(a)==CORE_RANGE==c['modified_sha256'],'Range source chain')
    text=a.decode('utf-8')
    for old,new in [(c['insertion_before'],c['insertion_after']),(c['branch_before'],c['branch_after'])]:
        require(text.count(new)==1,'Range exact transform uniqueness');text=text.replace(new,old,1)
    require(text==b.decode('utf-8') and a==read('physical_inputs/rtl/rv32_core.sv'),'Range inverse and actual core')
    ev=load(ran+'RANGE_VERIFICATION.json');require(ev['production_source_extraction'] and ev['exact_source_inverse'],'Range production extraction')
    for name,h in ev['source_bindings'].items():require(digest(read(ran+name))==h,'Range extracted input binding '+name)
    pass_receipt(ev['formal']);pass_receipt(ev['fourstate'],'RANGE_FOURSTATE_PASS')
    require(ev['negative_wrong_fault_branch']['exit_status']!=0 and ev['negative_missing_xz_fallback']['exit_status']!=0,'Range negative controls')
    require(ev['parameter_widths']==list(range(34)) and 'checks=705704' in ev['fourstate']['literal_output'],'Range fourstate/parameters')
    core_bmr(read,ran,CORE_KEEP,CORE_RANGE,BTB_SINGLE)
    require(digest(read('physical_inputs/rtl/rv32_cache.sv'))=='c9d73d59e80a70399df214dfbbe3316083e6df0d33974e1564795a4ae875d6c1','Original cache bytes')
def verify_content(read,names):
    require(len(names)==len(set(names)),'Duplicate members')
    for n in names:safe(n)
    m=parse(read('MANIFEST.json'));entries=m['files']
    require(m['schema']=='pacerv-sg30-qualified-release/v1' and m['frequency_hz']==145125000 and m['setup_uncertainty_ns']==0.15,'Package contract')
    require(set(names)=={x['path'] for x in entries}|{'MANIFEST.json'} and len(entries)==len({x['path'] for x in entries}),'Exact manifest inventory')
    for e in entries:
        data=read(safe(e['path']));require(len(data)==e['bytes'] and digest(data)==e['sha256'],'Manifest hash '+e['path'])
    ph=parse(read('evidence/physical/BUILD_RESULT.json'))
    require(ph['Status']=='completed_timing_pass' and ph['Error'] is None and ph['ConfiguredCpuClockHz']==145125000 and ph['ReferenceClockHz']==27000000 and ph['SetupUncertaintyNs']==0.15,'Physical status/clock')
    require(ph['Seed']==2 and ph['PnrOptions']==OPTIONS,'Exact PNR recipe')
    tcl=read('evidence/physical/implementation/build.tcl').decode('utf-8-sig')
    require(('pnr '+OPTIONS+'\n') in tcl.replace('\r\n','\n'),'Actual PNR TCL')
    invocation=parse(read('evidence/physical/implementation/INVOCATION.json'))
    require(invocation['ExitStatus']==0 and str(invocation['Pid'])=='73144','Original completed PDS invocation')
    raw=read('evidence/physical/implementation/report_timing/pds_soc_top.rtr')
    checks=parse_timing_report(raw)
    require(len(checks)==10 and checks==ph['Timing']['Checks'] and ph['Timing']['AllReportedChecksPass'],'Raw ten timing checks')
    require(b'Design Summary : All Constraints Met.' in raw and digest(raw)==ph['Timing']['ReportSHA256'].lower() and b'-0.150' in raw,'Actual timing closure and uncertainty')
    require(all(rows and all(x['WorstSlackNs']>=0 and x['TotalNegativeSlackNs']==0 and x['FailingEndpoints']==0 and x['TotalEndpoints']>0 for x in rows) for rows in checks.values()),'All raw timing rows pass')
    require(checks['Setup_Slow'][0]['WorstSlackNs']==0.043,'Selected slow setup')
    prr=read('evidence/physical/implementation/place_route/pds_soc_top.prr').decode('utf-8-sig')
    resources={k:sum(map(int,re.findall(r'\|\s+'+k+r'\s+\|\s*(\d+)\s*\|',prr))) for k in ['LUT','FF']}
    for label,key in [('DRM','DRM36K'),('APM','APM'),('GPLL','GPLL')]:resources[key]=int(re.search(r'\| Use of '+label+r'\s+\|\s*(\d+)',prr)[1])
    require(resources==dict(LUT=6621,FF=2557,DRM36K=25,APM=4,GPLL=1)==m['resources']=={k:ph['Resources'][k] for k in resources},'Actual PRR resource counts')
    require(digest(read('bitstreams/V0.sbit'))==BIT==ph['Bitstream']['SHA256'].lower() and len(read('bitstreams/V0.sbit'))==9188552,'Actual bitstream')
    for row in parse(read('evidence/physical/INPUT_HASHES.json')):
        path=row['RelativePath'].replace(chr(92),'/');data=read('physical_inputs/'+safe(path))
        require(digest(data)==row['SHA256'].lower() and len(data)==row['Bytes'],'Actual physical input '+path)
    audit=parse(read('evidence/qualification/SG30_LUT1_QUALIFICATION_AUDIT.json'))
    inventory=audit['source_inventory_35'];require(len(inventory['rtl'])==17 and len(inventory['physical_rtl'])==18,'35 source inventory')
    for kind,prefix in [('rtl','simulation/rtl/'),('physical_rtl','physical_inputs/rtl/')]:
        for n,h in inventory[kind].items():require(digest(read(prefix+n))==h,'Source inventory '+kind+'/'+n)
    require(len([n for n in names if n.startswith('simulation/rtl/') and n.endswith('.sv')])==17 and len([n for n in names if n.startswith('physical_inputs/rtl/') and n.endswith('.sv')])==18,'Exact 17/18 RTL files')
    for n in inventory['rtl']:require(read('simulation/rtl/'+n)==read('physical_inputs/rtl/'+n),'17 common RTL exact')
    recipe=parse(read('recipe.json'));identity=hashlib.sha256()
    for arg in recipe['simulation']['argv']:
        prefix='simulation/rtl/' if '/simulation/inputs/rtl/' in arg else 'simulation/sim/' if '/simulation/inputs/sim/' in arg else None
        if prefix:
            name=PurePosixPath(arg).name;identity.update(name.encode());identity.update(read(prefix+name))
    identity.update(b'1');require(identity.hexdigest()==SIM_ID==audit['simulation_identity'],'Actual simulator identity including vendor inputs')
    for role,cycles in [('V0',1712559880),('V1',1713586192)]:
        prefix='firmware/'+role+'/';run=parse(read(prefix+'RUN.json'));build=parse(read(prefix+'BUILD.json'));process=parse(read(prefix+'PROCESS.json'))
        uart=read(prefix+'uart.log').decode('utf-8-sig');stdout=read(prefix+'simulation.log').decode('utf-8-sig')
        require(run['firmware']==build and run['stdout']==stdout and process['status']=='COMPLETED' and process['native_exit_status']==run['exit_status']==0,'Actual long receipts '+role)
        require(run['rtl_sha256']==process['rtl_sha256']==SIM_ID and run['load_use_bubble']==1 and build['role']==role and build['iterations']==6000,'Long source/iterations '+role)
        require('-DCPU_CLOCK_HZ=145125000u' in build['command'] and '-DITERATIONS=6000' in build['command'],'Compiler macros '+role)
        require(all(run['checks'].values()) and not run['error_lines'] and run['formal_ten_seconds'],'Long checks '+role)
        require(run['timed_cycles']==cycles and cycles/145125000>=10 and abs(6000000000/cycles-run['coremark_per_mhz'])<1e-12 and 6000000000/cycles>3.5,'Actual score/duration '+role)
        cs=re.search(r'cycles_hex=([0-9a-fA-F]{16}) retired_hex=([0-9a-fA-F]{16}) clock_hz=(\d+)',uart)
        obs=re.search(r'OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)',stdout)
        require(cs and obs and int(cs[1],16)==int(obs[1])==cycles and int(cs[2],16)==int(obs[2])==run['retired'] and int(cs[3])==145125000 and int(obs[3])==run['minimum_sp'] and 49152<=run['minimum_sp']<=65536,'UART and independent observer '+role)
        expected={'V0':['0xe714','0x1fd7','0x8e3a','0xa14c'],'V1':['0xe3c1','0x0747','0x8d84','0x18e1']}[role]
        require(re.findall(r'\[0\](?:crc(?:list|matrix|state)|crcfinal)\s*:\s*(0x[0-9a-fA-F]+)',uart)==expected==run['crc_fields'] and 'Correct operation validated.' in uart and 'ZGTC COREMARK FINISHED' in uart,'Actual CRC '+role)
        for path,h in build['source_hashes'].items():require(digest(read(prefix+'inputs/'+safe(path)))==h,'Firmware source '+role+'/'+path)
        h=digest(read(prefix+'firmware.hex'));require(h==build['firmware_hex_sha256'],'Firmware image '+role)
        if role=='V0':require(h==ph['FirmwareSHA256'].lower()==digest(read('physical_inputs/firmware.hex'))=='941041b71bd0b8a3075bd3470fdd566605492f3ceb21ba8faea677dd230bc0cf','V0 bitstream firmware')
    # Constraint bytes match the protected H4 and original SG30-s2 checkpoints.
    for n in ['board.fdc','uart_board.fdc','uart_remotelab.fdc']:
        a=read('physical_inputs/constraints/'+n)
        require(a==read('evidence/ancestors/H4/constraints/'+n)==read('evidence/ancestors/SG30s2/constraints/'+n),'Exact constraint bytes '+n)
    require(read('physical_inputs/fpga/rv32_pll.sv')==read('evidence/ancestors/H4/fpga/rv32_pll.sv'),'Exact PLL')
    for n,field in [('netlist.v','NetlistSHA256'),('source.adf','DatabaseSHA256')]:
        require(digest(read('evidence/physical/implementation/'+n))==ph['ReusedSynthesis'][field].lower()==audit['reused_netlist_sha256' if n=='netlist.v' else 'reused_ADF_sha256'],'Reused checkpoint '+n)
    txn='evidence/packing1_transaction/';old=read(txn+'BASELINE_FILE.tcl').decode('utf-8-sig');new=read(txn+'MODIFIED_FILE.tcl').decode('utf-8-sig')
    normalize=lambda s:re.sub(r'\{[^{}]+/(implementation|inputs)/',r'{BUILD/\1/',s.replace(chr(92),'/'))
    require(normalize(old).replace('-logic_optimize_lut6d_combing_strategy 3','-logic_optimize_lut6d_combing_strategy 1')==normalize(new),'Exact single packing option change')
    require(read(txn+'MODIFIED_FILE.tcl')==read('evidence/physical/implementation/build.tcl'),'Packing transaction actual recipe')
    pr=parse(read(txn+'ROLLBACK_RESULT.json'))
    require(pr['exit_status']==0 and pr['rollback']['exit_status']==0 and pr['rollback']['restored_sha256']==digest(read(txn+'BASELINE_FILE.tcl')),'Packing independent-copy rollback')
    verify_chains(read)
    return dict(status='SG30_PACKAGE_PASS',files=len(entries),rtl=17,physical_rtl=18,timing=10,LUT=6621,FF=2557,slow_setup_ns=0.043,bitstream_sha256=BIT,source_identity=SIM_ID)

def parse_timing_report(data):
    text = data.decode("utf-8-sig")
    require("Design Summary : All Constraints Met." in text and "clock uncertainty" in text and "-0.150" in text, "Actualtimingreportclosureanduncertainty")
    require("CLKOUT0_Inferred  6.8900" in text and "145.1379 MHz" in text, "Actualgeneratedclockperiod")
    checks = {}
    for corner in ("Slow", "Fast"):
        for kind in ("Setup", "Hold", "Recovery", "Removal", "Minimum Pulse Width"):
            section = re.search(re.escape(kind + " Summary(" + corner + " Corner):") + r"(.*?)(?=\r?\n=+)", text, re.S)
            require(section is not None, "Actualtimingsection:" + kind + "/" + corner)
            rows = re.findall(r"^\s*(.*?)\s+([+-]?\d+\.\d+)\s+([+-]?\d+\.\d+)\s+(\d+)\s+(\d+)\s*$", section[1], re.M)
            require(bool(rows), "Actualtimingendpointrows:" + kind + "/" + corner)
            checks[kind + "_" + corner] = [dict(Clocks=clocks.strip(), WorstSlackNs=float(slack), TotalNegativeSlackNs=float(total), FailingEndpoints=int(failing), TotalEndpoints=int(endpoints)) for clocks, slack, total, failing, endpoints in rows]
    return checks
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


def main():
    ap=argparse.ArgumentParser(description=__doc__);group=ap.add_mutually_exclusive_group(required=True);group.add_argument('--root',type=Path);group.add_argument('--zip',type=Path);args=ap.parse_args()
    if args.zip:
        with zipfile.ZipFile(args.zip) as z:
            require(z.testzip() is None,'ZIP CRC');names=[x.filename for x in z.infolist() if not x.is_dir()];result=verify_content(z.read,names)
    else:
        base=args.root.resolve();names=[p.relative_to(base).as_posix() for p in base.rglob('*') if p.is_file()];result=verify_content(lambda n:(base/safe(n)).read_bytes(),names)
    print('SG30_PACKAGE_PASS files='+str(result['files'])+' RTL=17/18 timing=10/10 LUT=6621 FF=2557 slow=+.043ns actual6000=2 scores_gt3.5=2 source='+SIM_ID+' bit='+BIT)
if __name__=='__main__':main()
