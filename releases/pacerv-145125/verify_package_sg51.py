"""Standalone standard-library verification of the SG51 LUT6571 release root or ZIP."""
from pathlib import Path,PurePosixPath
import argparse,hashlib,io,itertools,json,re,sys,types,zipfile
sys.dont_write_bytecode=True
SELECTION = {'package_name':'PaceRV_H4_Loop16_SelectiveLoad_MuxLUT6D_145125_LUT6571_Verified','physical_work':'sg51-regfile-compare-mux-lut6d-lut3-s1','packing_transaction':'sg51_packing3_transaction','resources':{'LUT':6571,'FF':2557,'DRM36K':25,'APM':4,'GPLL':1},'slow_setup_ns':0.099,'seed':1,'packing':3,'options':'-dc_duplication false -plc_decongestion 0 -gplace_seed 1 -logic_optimize_lut6d_combing_strategy 3','bit_sha256':'deca4cb64cc00c9c16bc24f6f55ff21f19f9428c0e12ee915679208a1368e3f3'}
NAME=SELECTION['package_name']
PARENT_ZIP='a93a91cebe227bf793a766d941e4cee89e0d62f7f85442d63bd763de3a19deb5'
PARENT_VERIFIER='ac17ff6f9fc08c5884fd77cf9e1a0674d4e12ffa1cea00c4c262bdabea5b3c35'
CORE='75d136f28c97f1eaf6f5101b9cc4b1fdb17c2d2655d9ec50af733ca625a028e6'
BEFORE='8af95f92009be4979e23fa0bee77eff3bc6858357173470a0bdf7db75326c416'
SIM_ID='963a2d5dd9e239ca82b30fcf5a5734aa81c9281950dc9c336ef99af0a347371d'
EXE='ea512622369973fc8489d43bfa46b895dd1efac7e989657565cc3a77cb0ab8ff'
BIT=SELECTION['bit_sha256']
OPTIONS=SELECTION['options']
INIT=0xff55aa00d8d8d8d8
RUNTIME_MODELS={'vendor/GTP_LUT6D.v':'98170b772b3a38a9b2b1ba114bdc4c179ed0f9f17ac0e9784eda8a3e69b2d646','derived_vendor/GTP_LUT5.v':'69962a5cd2eac937520a9707e2f12d3ef5b71fe375e4a8ddb6abe64b5e1fbef7','derived_vendor/GTP_MUX2LUT6.v':'cf9d0398739f3189ca354b958fd10dac7502dcaca8191c18d40e931d7a80747a','derived_vendor/INT_LUTMUX2_UDP.sv':'6e637cd21650c5d8ef724407294c75c00f0a146100fa5f1bd6aaaa1ff3d946fa','derived_vendor/INT_LUTMUX4_UDP.sv':'93eb375ae61799da0101e719a3ae18642ea6bc7a3ef916f666ff1b2896b1d364'}
OFFICIAL_MODELS={'GTP_LUT5.v':'7835a0cf88a3249b36615ea127eb3b32b18f4e118ce0efb70907720a140beaf9','GTP_LUT6D.v':'98170b772b3a38a9b2b1ba114bdc4c179ed0f9f17ac0e9784eda8a3e69b2d646','GTP_MUX2LUT6.v':'307d95f567f6d20ce4941dc8cadb885d4be33d660817973fec341a20fef8229a','INT_LUTMUX2_UDP.v':'8d4ac4b61d25107396bb362c2ea4b668a5747f0fd7094bcb258ac29f0225342a','INT_LUTMUX4_UDP.v':'11b26877f200570e3685e41ce8c72c9c396caaa12a3c46d0ff9e034c5f899841'}
EXPECTED_CYCLES={'V0':1712559880,'V1':1713586192}
EXPECTED_PIDS={'V0':12337,'V1':12341}
CRCS={'V0':['0xe714','0x1fd7','0x8e3a','0xa14c'],'V1':['0xe3c1','0x0747','0x8d84','0x18e1']}
SHORT_FIRMWARE={'V0':{'BUILD.json':'1d9a79c7c7589253724ddf18fc928827b605cf46ce534d7f5915be697cf6be92','firmware.bin':'e194dcf950252e2687c3b4ab7448b5daf103bacdec26488cb69597f17bcd6c7c','firmware.dis':'1cc81731ecdb4ebf124d03e2828fd817bcca6c3ab78f5ef4a6b02deab04ef18b','firmware.elf':'1a44caf90e4e780f3e34390ecaeb1ee0e4ba05c3561a715627577262bdf53140','firmware.hex':'39504b698a04826e0584891b9cd321b73c1f3990fd3af6fe8de66268f8801355'},'V1':{'BUILD.json':'102029677d3dc4303e72bd98123019fc3b14be3c4bb3fd35e73e9163af9d1602','compiler.log':'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855','firmware.bin':'e975634005b87540da3283edf2caf708706e179f24bbabbdd25f5afa072f91f0','firmware.dis':'55b611c8d709838ef8d317f7965fa9b2c72378d592079cef18b593b360d603e7','firmware.elf':'e1574ae69ac61bb8c2014b6a1b1a7990e0eab94f217d3cb5abbb4d82e6ca0fbb','firmware.hex':'02a9c2dd04deee83269acbc97a7556c3dd6a2bbd522feb20f4a3307d0e997f2d','firmware.map':'4bf3f3f96be7b08ae6de425446ea07415632c34ea589df2148d1140bb945f584'}}

def require(ok,message):
    if not ok:raise ValueError(message)
def digest(b):return hashlib.sha256(b).hexdigest()
def parse(b):return json.loads(b.decode('utf-8-sig'))
def safe(n):
    p=PurePosixPath(n)
    require(bool(n) and p.as_posix()==n and not p.is_absolute() and '..' not in p.parts and ':' not in n and chr(92) not in n,'Unsafe package member '+n)
    return n
def receipt(r,token):require(r['exit_status']==0 and token in r['literal_output'],'Evidence receipt '+token)

def parent_chain(read):
    data=read('parents/SG30_LUT6621_Verified.zip')
    require(digest(data)==PARENT_ZIP,'Original SG30 parent ZIP bytes')
    z=zipfile.ZipFile(io.BytesIO(data));require(z.testzip() is None,'Parent ZIP CRC')
    code=z.read('verify_package_sg30.py');require(digest(code)==PARENT_VERIFIER,'Original strict parent verifier')
    module=types.ModuleType('_trusted_sg30');module.__file__='embedded_parent_verify_package_sg30.py'
    exec(compile(code,module.__file__,'exec'),module.__dict__)
    result=module.verify_content(z.read,[i.filename for i in z.infolist() if not i.is_dir()])
    require(result['files']==536 and result['LUT']==6621,'Complete qualified parent chain')
    return z,module

def source_and_models(read,parent,legacy):
    p='evidence/rtl/regfile_compare_mux_lut6d/'
    c=parse(read(p+'CHANGE.json'));a=read(p+'MODIFIED_FILE.sv');b=read(p+'BASELINE_FILE.sv')
    require(digest(a)==CORE==c['modified_sha256'] and digest(b)==BEFORE==c['baseline_sha256'],'SG51 raw source identity')
    require(b==parent.read('physical_inputs/rtl/rv32_core.sv'),'Exact SG30 source parent')
    text=a.decode();inverse=text
    for before,after in reversed(c['edits']):
        require(inverse.count(after)==1,'Source inverse uniqueness');inverse=inverse.replace(after,before,1)
    require(inverse.encode()==b and len(c['edits'])==3,'Exact two keeps plus compare-mux inverse')
    require(a==read('physical_inputs/rtl/rv32_core.sv')==read('simulation/rtl/rv32_core.sv'),'Actual physical/simulation core source')
    require(text.count("GTP_LUT6D #(.INIT(64'hff55aa00d8d8d8d8))")==2 and 'compare_pair_bit<16' in text,'32 source macros')
    require('translate_off' not in text and '`ifdef' not in text,'Unified production fourstate implementation')
    for port in ['a','b']:
        require("default: compare_next_"+port+'[2*compare_pair_bit+:2]=ex_ready ? id_operand_'+port+'[2*compare_pair_bit+:2] : forwarded_'+port+'[2*compare_pair_bit+:2];' in text,'Original ternary fallback '+port)
    for folder,count,prefix in [('rtl',17,'simulation/rtl/'),('physical_rtl',18,'physical_inputs/rtl/')]:
        require(len(c[folder])==count,'Source count '+folder)
        for n,h in c[folder].items():
            data=read(prefix+n);require(digest(data)==h,'Raw source '+folder+'/'+n)
            parent_path='physical_inputs/fpga/'+n if n=='rv32_pll.sv' else 'physical_inputs/rtl/'+n
            if n!='rv32_core.sv':require(data==parent.read(parent_path),'Only core changed '+n)
    legacy.core_bmr(read,p,BEFORE,CORE,c['parent_btb_sha256'])
    cones=parse(read(p+'READ_CONE_VERIFICATION.json'))
    require(cones['actual_sources']=={'BASELINE_FILE.sv':BEFORE,'MODIFIED_FILE.sv':CORE},'Source-extracted read proof binding')
    receipt(cones['SAT'],'SAT proof finished - no model found: SUCCESS!')
    receipt(cones['fourstate'],'REGFILE_READ_CONE_FOURSTATE_PASS checks=8192')
    require(cones['negative_wrong_INIT']['exit_status']==1,'Source wrong INIT negative')
    guard=parse(read(p+'PRODUCTION_GUARD.json'))
    require(guard['production_core_sha256']==CORE and guard['actual_extracted_body_matches_source'] and guard['macro_pairs']==32 and guard['fourstate_cases_per_pair']==1024 and guard['output_bit_checks']==65536,'Actual32macro production guard scope')
    body=read(p+'actual_production_mux.sv').decode()
    production=text[text.index('    wire [31:0] compare_mux_lut_a,compare_mux_lut_b;'):text.index('    // One comparison bank follows')]
    require(digest(production.encode())==guard['production_compare_body_sha256'] and production in body,'Exact extracted production guard body')
    receipt(guard['tests'][1],'ACTUAL_PRODUCTION_PAIR_GUARD_PASS cases=1024')
    support=parse(read(p+'MODEL_SUPPORT.json'));adapt=parse(read(p+'MODEL_ADAPTATION.json'))
    require(support['status']=='MODEL_EQUIVALENT_AND_VERILATOR_SUPPORTED','Proven normalized vendor models')
    require(support['simulation_model_sha256']==RUNTIME_MODELS,'Fixed official and proven derived runtime model identities')
    for name,h in OFFICIAL_MODELS.items():require(digest(read('simulation/models/vendor/'+name))==h,'Fixed installed official model '+name)
    for relative,h in support['simulation_model_sha256'].items():require(digest(read('simulation/models/'+relative))==h,'Actual simulation primitive '+relative)
    for row in support['normalization']:
        before=read('simulation/models/vendor/'+row['file']).decode();after=read('simulation/models/derived_vendor/'+row['file']).decode()
        require(digest(before.encode())==row['official_sha256'] and digest(after.encode())==row['derived_sha256'],'Normalized official source hashes')
        for original,new in reversed(row['edits']):
            require(after.count(new)==1,'Anonymous instance inverse uniqueness');after=after.replace(new,original,1)
        require(after==before and row['exact_byte_inverse'],'Only anonymous instance names changed')
    receipt(adapt['full_fourstate'],'UDP_FULL_FOURSTATE_EQUIVALENCE_PASS mux2_cases=64 mux4_cases=4096 checks=4160')
    require(adapt['negative_wrong_truth_row']['exit_status']==1,'UDP negative control')
    model_count=verify_udp_and_lut(read,adapt)
    return c,support,model_count

def verify_udp_and_lut(read,adapt):
    tables={}
    for row in adapt['source_records']:
        name=row['name'];official=read('simulation/models/vendor/'+name+'.v').decode();derived=read('simulation/models/derived_vendor/'+name+'.sv').decode()
        require(digest(official.encode())==row['official_sha256'] and digest(derived.encode())==row['derived_sha256'],'UDP actual source hash '+name)
        body=re.search(r'\btable\b(.*?)\bendtable\b',official,re.S)[1]
        rules=[]
        for line in body.splitlines():
            line=line.split('//',1)[0].strip()
            if not line:continue
            pattern,out=re.fullmatch(r'([01x?\s]+):\s*([01x])\s*;',line).groups();rules.append((pattern.split(),out))
        require(len(rules)==row['table_rows'],'Official UDP table rows')
        tables[name]=rules
        # Regenerate exact original row translation; no eval of package code.
        translated=['`timescale 1ns/1ps','// Deterministic translation of installed UDP table rows. UDP inputs Z match X.',
            'module '+name+'('+','.join(row['ports'])+');','output reg '+row['ports'][0]+';',
            'input '+','.join(row['ports'][1:])+';','always @* begin',"    "+row['ports'][0]+"=1'bx;"]
        for pattern,out in rules:
            terms=[]
            for signal,value in zip(row['ports'][1:],pattern):
                if value in '01':terms.append('('+signal+"===1'b"+value+')')
                elif value=='x':terms.append('('+signal+"!==1'b0 && "+signal+"!==1'b1)")
            translated.append('    if ('+' && '.join(terms)+') '+row['ports'][0]+"=1'b"+out+';')
        translated+=['end','endmodule','']
        require('\n'.join(translated)==derived,'Production UDP row translation exact '+name)
    def udp(name,args):
        matched=[]
        for pattern,out in tables[name]:
            if all(p=='?' or p==v or (p=='x' and v in 'xz') for p,v in zip(pattern,args)):matched.append(out)
        require(len(set(matched))<=1,'Official UDP overlapping contradictions')
        return matched[-1] if matched else 'x'
    lut5=read('simulation/models/vendor/GTP_LUT5.v').decode()
    calls=re.findall(r'\b(INT_LUTMUX[24]_UDP)\s*\(([^;]+)\);',lut5)
    require(len(calls)==11,'Actual LUT5 vendor structure')
    def five(init,x):
        values={'I'+str(i):v for i,v in enumerate(x)}
        def term(t):
            t=t.strip();m=re.fullmatch(r'INIT\[(\d+)\]',t)
            return str((init>>int(m[1]))&1) if m else values[t]
        for name,args in calls:
            args=[s.strip() for s in args.split(',')];values[args[0]]=udp(name,[term(t) for t in args[1:]])
        return values['Z']
    def ternary(s,a,b):return a if s=='1' else b if s=='0' else a if a==b else 'x'
    checks=0
    for x in itertools.product('01xz',repeat=5):
        low=five(INIT&0xffffffff,x);high=five(INIT>>32,x)
        raw=(high,low);expected=(ternary(x[0],x[3],x[4]),ternary(x[0],x[1],x[2]))
        guarded=raw if all(v in '01' for v in x) else expected
        require(guarded==expected,'Recomputed production LUT/guard VM truth')
        checks+=1
    require(checks==1024,'Complete pair VM cases')
    return checks

def physical(read,parent,legacy):
    p='evidence/physical/';ph=parse(read(p+'BUILD_RESULT.json'))
    require(read('tools/Build-PacePds.snapshot.ps1')==parent.read('tools/Build-PacePds.snapshot.ps1'),'Unchanged actual PDS builder recipe')
    require(ph['Status']=='completed_timing_pass' and ph['Error'] is None,'Completed physical build')
    require(ph['ConfiguredCpuClockHz']==145125000 and ph['SetupUncertaintyNs']==0.15 and ph['ReferenceClockHz']==27000000,'Physical clock contract')
    require(ph['Seed']==SELECTION['seed'] and ph['PnrOptions']==OPTIONS,'SG51 selected seed/packing')
    tcl=read(p+'implementation/build.tcl').decode('utf-8-sig').replace('\r\n','\n')
    require('pnr '+OPTIONS+'\n' in tcl,'Actual packing TCL')
    invocation=parse(read(p+'implementation/INVOCATION.json'));require(invocation['ExitStatus']==0,'Actual physical native exit')
    rtr=read(p+'implementation/report_timing/pds_soc_top.rtr');checks=legacy.parse_timing_report(rtr)
    require(len(checks)==10 and checks==ph['Timing']['Checks'] and all(v and all(x['WorstSlackNs']>=0 and x['TotalNegativeSlackNs']==0 and x['FailingEndpoints']==0 and x['TotalEndpoints']>0 for x in v)for v in checks.values()),'Raw all10 timing checks')
    require(checks['Setup_Slow'][0]['WorstSlackNs']==SELECTION['slow_setup_ns'] and digest(rtr)==ph['Timing']['ReportSHA256'].lower(),'Actual selected timing report')
    prr=read(p+'implementation/place_route/pds_soc_top.prr').decode('utf-8-sig')
    resources={k:sum(map(int,re.findall(r'\|\s+'+k+r'\s+\|\s*(\d+)\s*\|',prr)))for k in ['LUT','FF']}
    for label,key in [('DRM','DRM36K'),('APM','APM'),('GPLL','GPLL')]:resources[key]=int(re.search(r'\| Use of '+label+r'\s+\|\s*(\d+)',prr)[1])
    require(resources==SELECTION['resources']=={k:ph['Resources'][k]for k in resources},'Raw PRR current selected resources')
    require(digest(read('bitstreams/V0.sbit'))==BIT==ph['Bitstream']['SHA256'].lower() and len(read('bitstreams/V0.sbit'))==9188552,'Exact SG51 bitstream')
    inventory=parse(read(p+'INPUT_HASHES.json'));require(len(inventory)==25,'25 physical inputs')
    expected={'constraints/board.fdc','constraints/uart_board.fdc','constraints/uart_remotelab.fdc','firmware.hex','fpga/rv32_pll.sv','pds_soc_top.v','runner.py'}|{'rtl/'+n for n in parse(read('evidence/rtl/regfile_compare_mux_lut6d/CHANGE.json'))['physical_rtl']}
    require({row['RelativePath'].replace(chr(92),'/') for row in inventory}==expected,'Exact25 physical input inventory')
    for row in inventory:
        relative=safe(row['RelativePath'].replace(chr(92),'/'));data=read('physical_inputs/'+relative)
        require(len(data)==row['Bytes'] and digest(data)==row['SHA256'].lower(),'Actual physical input hash '+row['RelativePath'])
        if relative not in ['rtl/rv32_core.sv','pds_soc_top.v']:require(data==parent.read('physical_inputs/'+relative),'Unchanged parent physical input '+relative)
    wrapper=lambda b:re.sub(r'\.INIT_FILE\("[^"]+"\)', '.INIT_FILE("FW/firmware.hex")',b.decode('utf-8-sig').replace('\r\n','\n'))
    require(wrapper(read('physical_inputs/pds_soc_top.v'))==wrapper(parent.read('physical_inputs/pds_soc_top.v')),'Wrapper only relocates firmware path')
    for name in ['board.fdc','uart_board.fdc','uart_remotelab.fdc']:require(read('physical_inputs/constraints/'+name)==parent.read('physical_inputs/constraints/'+name),'Unchanged FDC '+name)
    require(read('physical_inputs/fpga/rv32_pll.sv')==parent.read('physical_inputs/fpga/rv32_pll.sv'),'Unchanged PLL source')
    net=read(p+'implementation/netlist.v');require(digest(net)==ph['ReusedSynthesis']['NetlistSHA256'].lower(),'Actual synthesis netlist')
    require(digest(read(p+'implementation/source.adf'))==ph['ReusedSynthesis']['DatabaseSHA256'].lower(),'Actual synthesis checkpoint')
    pll=re.search(r'GTP_GPLL /\* pll \*/ #(.*?)\)\s*\\?pll\s*\(',net.decode(),re.S)
    require(pll is not None,'Actual mapped PLL instance')
    for key,value in [('CLKIN_FREQ','27'),('STATIC_RATIOI','1'),('STATIC_RATIOM','1'),('STATIC_RATIO0','8'),('STATIC_RATIOF','43')]:
        require(re.search(r'\.'+key+r'\('+value+r'\)',pll[1]) is not None,'Actual mapped PLL '+key)
    verify_mapped_macros(net)
    tx='evidence/packing3_transaction/';before=read(tx+'BASELINE_FILE.tcl').decode('utf-8-sig');after=read(tx+'MODIFIED_FILE.tcl').decode('utf-8-sig')
    norm=lambda s:re.sub(r'\{[^{}]+/(implementation|inputs)/',r'{BUILD/\1/',s.replace(chr(92),'/').replace('\r\n','\n'))
    require(norm(before).replace('-logic_optimize_lut6d_combing_strategy 1','-logic_optimize_lut6d_combing_strategy '+str(SELECTION['packing']))==norm(after),'Exact packing single-field transaction')
    require(read(tx+'MODIFIED_FILE.tcl')==read(p+'implementation/build.tcl'),'Actual new packing transaction')
    rollback=parse(read(tx+'ROLLBACK_RESULT.json'));require(rollback['exit_status']==rollback['rollback']['exit_status']==0 and rollback['rollback']['restored_sha256']==digest(read(tx+'BASELINE_FILE.tcl')),'Packing actual rollback exit/source')
    require(digest(read(tx+'rollback_copy.tcl'))==digest(read(tx+'BASELINE_FILE.tcl')),'Packing independent-copy bytes restored')
    return ph,checks,resources

def exact_parent_minimum_sp(value,parent,role,phase):
    parent_min=parse(parent.read('firmware/'+role+'/RUN.json'))['minimum_sp']
    require(value==parent_min==65152,phase+' exact parent minimum_sp '+role)


def short_runs(read,parent=None):
    if parent is None:parent,_=parent_chain(read)
    for role,cycles in [('V0',28550446),('V1',28565259)]:
        prefix='short_runs/'+role+'/';run=parse(read(prefix+'RUN.json'));build=parse(read(prefix+'BUILD.json'));process=parse(read(prefix+'PROCESS.json'))
        require(build['iterations']==100 and build['role']==role and run['firmware']==build,'Separate actual100 firmware '+role)
        require(run['exit_status']==0 and run['rtl_sha256']==SIM_ID and run['load_use_bubble']==1 and run['timed_cycles']==cycles,'Actual100 matching model/count '+role)
        require(run['stdout']==read(prefix+'simulation.log').decode('utf-8-sig') and process['native_exit_status']==0 and process['status']=='COMPLETED','Actual100 native exit/log '+role)
        uart=read(prefix+'uart.log').decode('utf-8-sig');stdout=read(prefix+'simulation.log').decode('utf-8-sig')
        csr=re.search(r'cycles_hex=([0-9a-fA-F]{16}) retired_hex=([0-9a-fA-F]{16}) clock_hz=(\d+)',uart)
        observer=re.search(r'OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)',stdout)
        require(csr and observer and int(csr[1],16)==int(observer[1])==run['timed_cycles']==cycles and int(csr[3])==145125000,'Actual100 raw cycle/clock '+role)
        require(int(csr[2],16)==int(observer[2])==run['retired'],'Actual100 raw retired '+role)
        require(int(observer[3])==run['minimum_sp'],'Actual100 raw minimum_sp '+role)
        exact_parent_minimum_sp(int(observer[3]),parent,role,'Actual100')
        require(abs(run['coremark_per_mhz']-100000000/cycles)<1e-12,'Actual100 recomputed score '+role)
        crcs=re.findall(r'\[0\](?:crc(?:list|matrix|state)|crcfinal)\s*:\s*(0x[0-9a-fA-F]+)',uart)
        require(crcs==CRCS[role][:3]+[{'V0':'0x988c','V1':'0x844d'}[role]]==run['crc_fields'],'Actual100 raw four CRCs '+role)
        require(all(run['checks'].values()) and not run['error_lines'] and 'ZGTC COREMARK FINISHED' in uart,'Actual100 complete checks '+role)
        require(not run['formal_ten_seconds'] and 'Must execute for at least 10 secs' in uart,'Actual100 duration diagnostic retained '+role)
        for name,h in SHORT_FIRMWARE[role].items():require(digest(read(prefix+name))==h,'Exact original actual100 firmware/build '+role+'/'+name)
        require(build['firmware_hex_sha256']==process['firmware_sha256']==digest(read(prefix+'firmware.hex')),'Actual100 firmware process identity '+role)
        result=parse(read('evidence/shorts/SHORT_'+role+'_RESULT.json'))
        require(result['status']=='PASS_ACTUAL100_EXACT_PARENT_COUNTS_UART_CRC' and result['run']==run,'Actual100 worker receipt '+role)


def simulation_model(read,support):
    p='evidence/rtl/regfile_compare_mux_lut6d/'
    ext=parse(read(p+'EXTENDED_RECIPE.json'))
    original=read('tools/experiment.py');derived=read('tools/experiment_extended.py')
    require(digest(original)==ext['original']['sha256']=='beffece72e788e84a6d77f6f9b4135772a422d0bf4341c1a07dc727f5331e541','Original standard simulation builder')
    require(digest(derived)==ext['derived']['sha256']=='cdf7ead08a5b33a5624b414245c96150a3b930d2f5b2285de597e63325008fd8','Actual extended simulation builder')
    inverse=derived.decode()
    for before,after in reversed(ext['edits']):
        require(inverse.count(after)==1,'Extended builder inverse uniqueness');inverse=inverse.replace(after,before,1)
    require(inverse.encode()==original and len(ext['edits'])==3,'Exact model-only standard builder extension')
    recipe=parse(read('recipe.json'));require(digest(read('recipe.json'))==ext['recipe']['sha256']=='2dc0bcbe90ff8c07f06820d5f526cd4073e87be7b6a4774ea55434c4dc5c8004','Unmodified standard recipe bytes')
    identity=hashlib.sha256();ordered=[]
    for arg in recipe['simulation']['argv']:
        prefix='simulation/rtl/' if '/simulation/inputs/rtl/' in arg else 'simulation/sim/' if '/simulation/inputs/sim/' in arg else None
        if prefix:ordered.append((PurePosixPath(arg).name,prefix+PurePosixPath(arg).name))
    require(sum(path.startswith('simulation/rtl/') for name,path in ordered)==17,'Exactly17 simulation sources in recipe')
    require(ext['extra_models']==support['simulation_model_sources'] and len(ext['extra_models'])==5,'Exactly5 proven runtime models')
    for original_path in support['simulation_model_sources']:
        suffix=original_path.split('/regfile_compare_mux_lut6d/',1)[1];ordered.append((PurePosixPath(original_path).name,'simulation/models/'+suffix))
    for name,path in ordered:identity.update(name.encode());identity.update(read(path))
    identity.update(b'1');require(identity.hexdigest()==SIM_ID,'Recomputed all17 RTL/driver/observer/5model simulation identity')
    native=parse(read('simulation/native/BUILD.json'));compiled=parse(read(p+'EXTENDED_MODEL_BUILD.json'))
    require(native['source_sha256']==compiled['identity']==SIM_ID and native['command']==compiled['command'],'Actual native build identity and command')
    require(digest(read('simulation/native/BUILD.json'))==compiled['BUILD']['sha256'] and digest(read('simulation/native/compile.log'))==compiled['compile_log']['sha256'],'Actual native compilation receipts')
    require(digest(read('simulation/native/Vrv32_observed_soc'))==compiled['executable_sha256']==EXE and compiled['threads']==compiled['load_bubble']==1,'Actual compiled executable/thread/bubble')
    actual=native['command'];base=actual[actual.index('--cc'):]
    expected=[]
    for arg in recipe['simulation']['argv']:
        if arg=='{OUTPUT}/objects':arg='/tmp/pacerv_h3_'+SIM_ID[:16]
        elif '/simulation/inputs/rtl/' in arg:arg='/SG51_RTL/'+PurePosixPath(arg).name
        elif arg.startswith('{RELEASE}'):arg='/SG51_ROOT'+arg[len('{RELEASE}'):]
        expected.append(arg)
    expected[expected.index('-j')+1]='1'
    expected+=['/SG51_ROOT/rtl_proposals/regfile_compare_mux_lut6d/'+p.split('/regfile_compare_mux_lut6d/',1)[1] for p in support['simulation_model_sources']]
    normalized=[]
    for arg in base:
        if '/candidates/loop16_h4_regfile_compare_mux_lut6d/rtl/' in arg:arg='/SG51_RTL/'+PurePosixPath(arg).name
        elif '/pacerv_h3_optimization/' in arg:arg='/SG51_ROOT/'+arg.split('/pacerv_h3_optimization/',1)[1]
        normalized.append(arg)
    require(normalized==expected and actual[0]==recipe['simulation']['tool_original'],'Exact standard flags, driver, observer, tools and added models')
    return native


def launch_contract(read,c):
    prefix='evidence/longs/';launch=parse(read(prefix+'LAUNCH_VERIFICATION_FROZEN.txt'));model=parse(read(prefix+'MODEL_READY.json'))
    require(launch['standard_simulation_rtl_identity']==model['rtl_sha256']==SIM_ID and launch['executable_sha256']==model['executable_sha256']==EXE,'Original6000 launch identity')
    require(launch['source17']==c['rtl'] and launch['physical18']==c['physical_rtl'] and model['model_build']==parse(read('simulation/native/BUILD.json')) and model['threads']==model['load_bubble']==1,'Original6000 model/source launch contract')
    require(digest(read('evidence/physical/BUILD_RESULT.json'))==launch['physical_build']['sha256'] and digest(read('evidence/physical/INPUT_HASHES.json'))==launch['physical_INPUT_HASHES']['sha256'],'Launch bound selected passing physical build')
    for name,row in model['source_proofs'].items():
        original=read('evidence/rtl/regfile_compare_mux_lut6d/'+name)
        require(digest(original)==row['original']['sha256']==row['snapshot']['sha256'],'Launch-frozen source proof '+name)
        require(read('evidence/shorts/SOURCE_'+name)==original,'Compiled-model source proof snapshot '+name)
    for name,row in launch['source_proofs'].items():
        original=read('evidence/rtl/regfile_compare_mux_lut6d/'+name)
        require(digest(original)==row['original']['sha256']==row['snapshot']['sha256'] and read(prefix+'SOURCE_'+name)==original,'Launch source proof snapshot '+name)
    for role in ['V0','V1']:
        fw='firmware/'+role+'/';reuse=parse(read(fw+'FIRMWARE_REUSE.json'));binding=reuse['source_binding']
        require(binding['rtl_17_sha256']==c['rtl'] and binding['physical_rtl_18_sha256']==c['physical_rtl'] and binding['rtl_sha256']==SIM_ID and binding['executable_sha256']==EXE,'Original6000 firmware source binding '+role)
        require(binding['short_verification_sha256']==digest(read(prefix+'LAUNCH_VERIFICATION_FROZEN.txt')) and binding['model_build']==model['model_build'],'Original6000 launch/compilation binding '+role)
        require(reuse['firmware_sha256']==digest(read(fw+'firmware.hex')) and reuse['build_json_sha256']==digest(read(fw+'BUILD.json')) and reuse['exact_firmware_bytes'] and reuse['exact_build_receipt_bytes'] and not reuse['compiler_flags_regenerated'],'Original6000 firmware reuse receipt '+role)
    return launch

def verify_mapped_macros(net):
    text=net.decode();starts=list(re.finditer(r'^\s*GTP_\w+\s*/\*.*?\*/',text,re.M));found={}
    for i,m in enumerate(starts):
        chunk=text[m.start():starts[i+1].start() if i+1<len(starts) else len(text)]
        pair=re.search(r'GTP_LUT6D /\*\s*\\g_compare_pair\[(\d+)\]\.compare_mux_([ab])\s*\*/',chunk)
        if not pair:continue
        bit=int(pair[1]);port=pair[2];require(0<=bit<16,'Mapped pair index')
        literal=re.search(r'\.INIT\(64\x27([bBhH])([0-9a-fA-F_]+)\)',chunk)
        require(literal is not None and int(literal[2].replace('_',''),2 if literal[1].lower()=='b' else 16)==INIT,'Mapped32 macro INIT')
        pins={k:v.strip()for k,v in re.findall(r'\.(\w+)\s*\(([^()]*)\)',chunk)}
        expected={'I0':'ex_ready','I1':f'id_operand_{port}[{2*bit}]','I2':f'forwarded_{port}[{2*bit}]','I3':f'id_operand_{port}[{2*bit+1}]','I4':f'forwarded_{port}[{2*bit+1}]','I5':"1'b1",'Z5':f'compare_mux_lut_{port}[{2*bit}]','Z':f'compare_mux_lut_{port}[{2*bit+1}]'}
        require(all(pins[k]==v for k,v in expected.items()),'Mapped32 macro actual pins')
        require((bit,port)not in found,'Duplicate mapped macro');found[(bit,port)]=True
    require(len(found)==32,'Actual32 physical compare macros')

def long_runs(read,c,support,ph,parent):
    p='evidence/longs/';audit=parse(read(p+'LONG_FINAL_AUDIT.json'))
    require(audit['status']=='PASS_BOTH_ACTUAL6000_AND_MATCHING_6571_TIMING' and audit['pending']==[] and len(audit['completed'])==2,'PENDING_OR_MISSING_FORMAL6000')
    model=parse(read(p+'MODEL_READY.json'));require(model['rtl_sha256']==SIM_ID and model['executable_sha256']==EXE,'Actual long model identity')
    require(model['model_build']==parse(read('simulation/native/BUILD.json')) and model['threads']==model['load_bubble']==1,'Launch model matches actual native compilation')
    require(audit['exact_model_identity']==SIM_ID and audit['source17']==c['rtl'] and audit['physical18']==c['physical_rtl'],'Matched formal6000 physical sources')
    for role in ['V0','V1']:
        prefix='firmware/'+role+'/';run=parse(read(prefix+'RUN.json'));build=parse(read(prefix+'BUILD.json'));proc=parse(read(prefix+'PROCESS.json'))
        require(proc['status']=='COMPLETED' and proc['native_pid']==EXPECTED_PIDS[role] and proc['native_exit_status']==run['exit_status']==0,'Original native process completed '+role)
        require(proc['rtl_sha256']==run['rtl_sha256']==SIM_ID and run['load_use_bubble']==1,'Long model/loadbubble '+role)
        require(proc['command']==run['command'] and proc['command'][0]=='/tmp/pacerv_h3_'+SIM_ID[:16]+'/Vrv32_observed_soc' and proc['command'][-1]=='2400000000' and proc['cwd']==run['working_directory'],'Original executable/process launch '+role)
        require(build['iterations']==6000 and build['role']==role and '-DITERATIONS=6000' in build['command'] and '-DCPU_CLOCK_HZ=145125000u' in build['command'],'Actual6000 build '+role)
        require(run['firmware']==build and run['stdout']==read(prefix+'simulation.log').decode('utf-8-sig'),'Actual RUN/BUILD/stdout binding '+role)
        require(all(run['checks'].values()) and not run['error_lines'] and run['formal_ten_seconds'],'Formal6000 complete checks '+role)
        uart=read(prefix+'uart.log').decode('utf-8-sig');stdout=run['stdout'];cycles=EXPECTED_CYCLES[role]
        require(read(prefix+'uart.log')==parent.read(prefix+'uart.log'),'Full actual UART equals qualified parent '+role)
        csr=re.search(r'cycles_hex=([0-9a-fA-F]{16}) retired_hex=([0-9a-fA-F]{16}) clock_hz=(\d+)',uart)
        obs=re.search(r'OBSERVER cycles=(\d+) retired=(\d+) minimum_sp=(\d+)',stdout)
        require(csr and obs and int(csr[1],16)==int(obs[1])==run['timed_cycles']==cycles and int(csr[2],16)==int(obs[2])==run['retired'] and int(csr[3])==145125000 and int(obs[3])==run['minimum_sp'],'CSR/UART/independent observer '+role)
        exact_parent_minimum_sp(run['minimum_sp'],parent,role,'Formal6000')
        require(cycles/145125000>=10 and 6000000000/cycles>=3.5 and abs(run['coremark_per_mhz']-6000000000/cycles)<1e-12,'Recomputed formal duration/score '+role)
        require(re.findall(r'\[0\](?:crc(?:list|matrix|state)|crcfinal)\s*:\s*(0x[0-9a-fA-F]+)',uart)==CRCS[role]==run['crc_fields'] and 'Correct operation validated.' in uart and 'ZGTC COREMARK FINISHED' in uart,'All four CRCs and completion '+role)
        for name in ['BUILD.json','firmware.hex','firmware.bin','firmware.elf','firmware.map','firmware.dis','compiler.log']:require(read(prefix+name)==parent.read(prefix+name),'Exact original firmware/build '+role+'/'+name)
        for name,h in build['source_hashes'].items():require(digest(read(prefix+'inputs/'+safe(name)))==h,'Firmware source '+role+'/'+name)
        require(digest(read(prefix+'firmware.hex'))==build['firmware_hex_sha256']==proc['firmware_sha256'],'Firmware identity '+role)
        if role=='V0':require(digest(read(prefix+'firmware.hex'))==ph['FirmwareSHA256'].lower()==digest(read('physical_inputs/firmware.hex')),'Actual V0 bitstream firmware')
        worker=parse(read(p+'LONG_'+role+'_RESULT.json'));require(worker['status']=='PASS_GT3P5' and worker['run']==run and worker['process']==proc and worker['run_json_sha256']==digest(read(prefix+'RUN.json')),'Original long worker exit/result '+role)
    return 2

def verify_content(read,names):
    require(len(names)==len(set(names)),'Duplicate ZIP members')
    for n in names:safe(n)
    m=parse(read('MANIFEST.json'));require(m['schema']=='pacerv-sg51-qualified-release/v1' and m['name']==NAME,'SG51 package contract')
    require(parse(read('SELECTED_PHYSICAL.json'))==SELECTION,'Exact selected physical contract')
    require(m['qualification']=='actual6000_both_ge3.5_and_all10_physical_checks_pass','PENDING_OR_MISSING_FORMAL6000')
    entries=m['files'];require(set(names)=={x['path']for x in entries}|{'MANIFEST.json'} and len(entries)==len({x['path']for x in entries}),'Exact manifest inventory')
    for e in entries:
        data=read(safe(e['path']));require(len(data)==e['bytes'] and digest(data)==e['sha256'],'Manifest hash '+e['path'])
    parent,legacy=parent_chain(read)
    c,support,vm=source_and_models(read,parent,legacy)
    require({n.removeprefix('simulation/rtl/') for n in names if n.startswith('simulation/rtl/')}==set(c['rtl']),'Exact17 source directory inventory')
    require({n.removeprefix('physical_inputs/rtl/') for n in names if n.startswith('physical_inputs/rtl/')}==set(c['physical_rtl']),'Exact18 physical RTL directory inventory')
    simulation_model(read,support)
    ph,checks,resources=physical(read,parent,legacy)
    launch_contract(read,c)
    require(m['frequency_hz']==145125000 and m['setup_uncertainty_ns']==0.15 and m['resources']==resources,'Current package metadata resources/clock')
    short_runs(read,parent)
    long_runs(read,c,support,ph,parent)
    return dict(status='SG51_PACKAGE_PASS',files=len(entries),LUT=resources['LUT'],FF=resources['FF'],timing=10,slow_setup_ns=SELECTION['slow_setup_ns'],formal6000=2,source_identity=SIM_ID,bitstream_sha256=BIT,production_pair_VM_cases=vm,parent_chain_files=536)

def main():
    ap=argparse.ArgumentParser(description=__doc__);g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--root',type=Path);g.add_argument('--zip',type=Path);args=ap.parse_args()
    if args.zip:
        with zipfile.ZipFile(args.zip) as z:
            require(z.testzip() is None,'ZIP CRC');result=verify_content(z.read,[i.filename for i in z.infolist()if not i.is_dir()])
    else:
        root=args.root.resolve();result=verify_content(lambda n:(root/safe(n)).read_bytes(),[p.relative_to(root).as_posix()for p in root.rglob('*')if p.is_file()])
    print('SG51_PACKAGE_PASS files='+str(result['files'])+' parent536=verified RTL17/18 macro32_VM1024=PASS all10=PASS LUT'+str(result['LUT'])+' FF'+str(result['FF'])+' slow='+str(result['slow_setup_ns'])+' actual6000=2 source='+SIM_ID+' bit='+BIT)
if __name__=='__main__':main()
