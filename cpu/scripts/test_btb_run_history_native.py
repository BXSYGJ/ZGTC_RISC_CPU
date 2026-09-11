import hashlib
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'build/btb-run-history-stage/build/pds/20260909-094728-0bd161c9/synthesize/pds_soc_top_syn.vm'
VENDOR = Path('/mnt/d/PDS_2022.2-SP6.4/arch/vendor/pango/verilog/simulation')

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()

def extract(native):
    modules = re.findall(r'\bmodule\s+rv32_btb\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native predictor')
    cells = re.findall(r'GTP_\w+\b[^;]*;',modules[0])
    selected = []
    for output,port in (('N644[0]','Z'),('N644[1]','Z'),('N644[2]','Z5'),('N643','Z')):
        matches = [cell for cell in cells if re.search(r'\.'+port+r'\s*\(\s*'+re.escape(output)+r'\s*\)',cell)]
        if len(matches)!=1 or not matches[0].startswith(('GTP_LUT6 ','GTP_LUT6D ')):
            raise ValueError('Missing unique native history driver')
        selected.append(matches[0])
    storage = [cell for cell in cells if re.search(r'GTP_RAM\w+\s*/\* history_[ab]_',cell)]
    if len(storage)!=15:
        raise ValueError('Native history storage inventory differs')
    outputs = set()
    for cell in storage:
        found = re.search(r'/\* (history_a_([0-2])|history_b_([0-3])_([0-2])) \*/',cell)
        if not found or found[1] in outputs:
            raise ValueError('Native history slot duplicated or changed')
        outputs.add(found[1])
        bit = int(found[2] if found[2] is not None else found[4])
        ports = dict(re.findall(r'\.(DI|DO|ADDR|WCLK|WE)\s*\(([^)]*)\)',cell))
        ports = {key:value.strip() for key,value in ports.items()}
        if ports['DI']!=f'N644[{bit}]' or ports['WCLK']!='clk':
            raise ValueError('Native history data or clock mapping differs')
        if found[2] is not None and (ports['DO']!=f'prior_history[{bit}]' or ports['ADDR']!='update_index' or ports['WE']!='N643'):
            raise ValueError('Native history update view mapping differs')
    return selected

def simulate(cells):
    header = ['`timescale 1ns/1ps','module native_history_tb;','reg [2:0] prior_history;','reg update_taken,allocate_entry,N626,update_conditional,_N20745,_N20748;','wire [2:0] N644;','wire N643,_N2671,_N2680;','integer stimulus,expected,run_length,checked;','reg expected_enable;']
    body = ['initial begin','checked=0;','for(stimulus=0;stimulus<512;stimulus=stimulus+1) begin','{_N20748,_N20745,N626,allocate_entry,update_conditional,update_taken,prior_history}=stimulus[8:0];','#1;','expected_enable=N626 && (allocate_entry || update_conditional);','if(N643!==expected_enable) $fatal(1,"native history enable mismatch stimulus=%0d",stimulus);','if(expected_enable) begin','if(allocate_entry) expected=update_conditional ? (update_taken ? 4 : 0) : 0;','else begin','run_length=prior_history & 3;','if(prior_history[2]!=update_taken) run_length=0;','else if(run_length<3) run_length=run_length+1;','expected=(update_taken ? 4 : 0) | run_length;','end','if(N644!==expected[2:0]) $fatal(1,"native history data mismatch stimulus=%0d actual=%0d expected=%0d",stimulus,N644,expected);','checked=checked+1;','end','end','if(checked!=192) $fatal(1,"native history coverage mismatch");','$display("PASS native history gate_cases=512 data_cases=192 data_bits=576");','$finish;','end','endmodule']
    with tempfile.TemporaryDirectory(prefix='native-run-history-') as directory:
        work = Path(directory)
        source,image = work / 'native.sv',work / 'native.vvp'
        source.write_text(chr(10).join(header+cells+body)+chr(10))
        compiled = subprocess.run(['iverilog','-g2012','-s','native_history_tb','-y',str(VENDOR),'-o',str(image),str(source)],capture_output=True,text=True,timeout=30)
        if compiled.returncode:
            raise RuntimeError(compiled.stdout+compiled.stderr)
        result = subprocess.run(['vvp',str(image)],capture_output=True,text=True,timeout=30)
        return result

class NativeRunHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.native = NATIVE.read_text()
        cls.cells = extract(cls.native)
        print('BOUND native_sha256='+digest(NATIVE)+' test_sha256='+digest(Path(__file__)))
        for name in ('GTP_LUT6.v','GTP_LUT6D.v','GTP_LUT5.v','GTP_MUX2LUT6.v','INT_LUTMUX2_UDP.v','INT_LUTMUX4_UDP.v'):
            print('VENDOR '+name+' '+digest(VENDOR / name))

    def test_actual_vendor_simulation(self):
        self.assertEqual(digest(NATIVE),'12612DD67EC4D37AF7A25616315A550EEF22181DD4EA0EA2F0A55393B663E709')
        result = simulate(self.cells)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('gate_cases=512 data_cases=192 data_bits=576',result.stdout)
        print(result.stdout.strip())

    def test_runtime_netlist_mutants(self):
        for index in range(4):
            mutated = list(self.cells)
            mutated[index] = re.sub(r"(\.INIT\(64'b)([01]{64})",lambda match:match[1]+''.join('0' if bit=='1' else '1' for bit in match[2]),mutated[index])
            self.assertNotEqual(mutated[index],self.cells[index])
            result = simulate(mutated)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('FATAL',result.stdout+result.stderr)
            print(f'PASS native runtime rejection: truth_{index}')
        for name,before,after,index in (('history_bit','prior_history[0]','prior_history[1]',0),('allocation','allocate_entry',"1'b0",1),('training','N626',"1'b1",3),('conditional','update_conditional',"1'b0",2)):
            mutated = list(self.cells)
            self.assertIn(before,mutated[index])
            mutated[index] = mutated[index].replace(before,after)
            result = simulate(mutated)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('FATAL',result.stdout+result.stderr)
            print('PASS native runtime rejection: '+name)

    def test_storage_mutations(self):
        for name,before,after in (('data','.DI (N644[0])','.DI (N644[1])'),('view','.DO (prior_history[0])','.DO (prior_history[1])'),('slot','history_a_0','history_a_1')):
            self.assertIn(before,self.native)
            with self.assertRaises(ValueError):
                extract(self.native.replace(before,after,1))
            print('PASS native storage rejection: '+name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
