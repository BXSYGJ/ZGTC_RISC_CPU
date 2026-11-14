"""Production FreeRTOS ROM + frozen 125 MHz native NPU, all layers golden.

The actual RV32IMC processor runs the normal application, timer interrupts,
queue handoff and UART tasks. The unchanged 125 MHz NPU/DDR sources execute
one complete real inference; accelerator completion/results are never forced.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = ROOT / 'sim/experiments/cpu_native_joint'
sys.path.insert(0, str(ROOT / 'sim'))
import run_sim as sim


def once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError('Review task-local native insertion: ' + old[:100])
    return text.replace(old, new)


def linux_path(path):
    p = Path(path).resolve().as_posix()
    if len(p) < 3 or p[1:3] != ':/':
        raise ValueError('Expected Windows drive path: ' + p)
    return '/mnt/' + p[0].lower() + p[2:]


def decode(data):
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        return data.decode('utf-16', errors='replace')
    if data.count(b'\x00') > len(data) // 8:
        return data.decode('utf-16-le', errors='replace')
    return data.decode('utf-8', errors='replace')


SHARED_DDR = r'''
// Native CPU/M3 path matches the production bridge and sharing modules.
wire pacerv_dd_req_valid,pacerv_dd_req_ready,pacerv_dd_req_write;
wire [31:0] pacerv_dd_req_address,pacerv_dd_req_data;
wire [3:0] pacerv_dd_req_strobe;
wire pacerv_dd_rsp_valid,pacerv_dd_rsp_ready,pacerv_dd_rsp_error;
wire [31:0] pacerv_dd_rsp_data;
wire pacerv_cpu_m3_valid,pacerv_cpu_m3_ready,pacerv_cpu_fault;
wire [36:0] pacerv_cpu_m3_cmd;
wire [255:0] pacerv_cpu_m3_wdata;
wire [31:0] pacerv_cpu_m3_wstrb;
wire [3:0] pacerv_c_wready,pacerv_c_rvalid,pacerv_c_done,pacerv_c_abort;
wire [255:0] pacerv_c_rdata;
wire pacerv_m3_valid,pacerv_m3_ready,pacerv_share_fault,pacerv_share_active;
wire [36:0] pacerv_m3_cmd;
wire [255:0] pacerv_m3_wdata;
wire [31:0] pacerv_m3_wstrb;
wire [1:0] pacerv_share_owner;
pace_cpu_ddr_bridge pacerv_ddr_bridge(
 .clk(clk),.rst_n(rst_n),.ddr_ok(1'b1),
 .req_valid(pacerv_dd_req_valid),.req_ready(pacerv_dd_req_ready),
 .req_address(pacerv_dd_req_address),.req_write(pacerv_dd_req_write),
 .req_data(pacerv_dd_req_data),.req_strobe(pacerv_dd_req_strobe),
 .rsp_valid(pacerv_dd_rsp_valid),.rsp_ready(pacerv_dd_rsp_ready),
 .rsp_data(pacerv_dd_rsp_data),.rsp_error(pacerv_dd_rsp_error),
 .m_cmd_valid(pacerv_cpu_m3_valid),.m_cmd(pacerv_cpu_m3_cmd),
 .m_wdata(pacerv_cpu_m3_wdata),.m_wstrb(pacerv_cpu_m3_wstrb),
 .m_rd_ready(pacerv_cpu_m3_ready),.m_wready(pacerv_c_wready[3]),
 .m_rvalid(pacerv_c_rvalid[3]),.m_rdata(pacerv_c_rdata),
 .m_done(pacerv_c_done[3]),.m_abort(pacerv_c_abort[3]),.fault(pacerv_cpu_fault));
ddr3_m3_share pacerv_m3_share(
 .clk(clk),.rst_n(rst_n),.boot_done(1'b1),
 .c_valid({pacerv_cpu_m3_valid,3'b000}),
 .c_cmd({pacerv_cpu_m3_cmd,111'd0}),
 .c_wdata({pacerv_cpu_m3_wdata,768'd0}),
 .c_wstrb({pacerv_cpu_m3_wstrb,96'd0}),
 .c_rd_ready({pacerv_cpu_m3_ready,3'b111}),
 .c_wready(pacerv_c_wready),.c_rvalid(pacerv_c_rvalid),
 .c_done(pacerv_c_done),.c_abort(pacerv_c_abort),.c_rdata(pacerv_c_rdata),
 .m_valid(pacerv_m3_valid),.m_cmd(pacerv_m3_cmd),.m_wdata(pacerv_m3_wdata),
 .m_wstrb(pacerv_m3_wstrb),.m_rd_ready(pacerv_m3_ready),
 .m_wready(n_wready_beat[3]),.m_rvalid(n_rd_valid_vec[3]),.m_rdata(n_rd3),
 .m_done(n_done_vec[3]),.m_abort(n_cmd_to_err[3] || n_addr_err[3]),
 .fault(pacerv_share_fault),.owner(pacerv_share_owner),.active(pacerv_share_active));
integer pacerv_ddr_requests=0,pacerv_ddr_responses=0;
always @(posedge clk) if(rst_n) begin
 if(pacerv_cpu_fault || pacerv_share_fault) $fatal(1,"PaceRV native DDR fault");
 if(pacerv_dd_req_valid && pacerv_dd_req_ready) pacerv_ddr_requests=pacerv_ddr_requests+1;
 if(pacerv_dd_rsp_valid && pacerv_dd_rsp_ready) pacerv_ddr_responses=pacerv_ddr_responses+1;
end
// Physical byte address 0x00300000 is the boot self-test's first word.
initial begin #1; n_model.mem[98304][31:0]=32'h5a5a00ff; end
'''


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--firmware', choices=('rtos', 'baseline125'), default='rtos')
    ap.add_argument('--backend', choices=('wsl-verilator', 'iverilog'), default='wsl-verilator')
    ap.add_argument('--verilator', default=os.environ.get(
        'PACERV_VERILATOR', '/home/bx/.local/src/verilator-5.040/bin/verilator'))
    ap.add_argument('--distro', default='Ubuntu-22.04')
    ap.add_argument('--jobs', type=int, default=2)
    ap.add_argument('--timeout', type=int, default=900)
    ap.add_argument('--prepare-only', action='store_true')
    ap.add_argument('--elaborate-only', action='store_true')
    ap.add_argument('--debug-ddr', action='store_true')
    ap.add_argument('--run-label', default=datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S'))
    args = ap.parse_args()
    if not args.run_label.replace('-', '').replace('_', '').isalnum():
        raise ValueError('Invalid run-label')
    if not 1 <= args.jobs <= 8:
        raise ValueError('jobs must be in 1..8')
    is_rtos = args.firmware == 'rtos'
    label = ('rtos125_' if is_rtos else 'baseline125_') + args.run_label
    work = ROOT / 'build/sim' / ('cpu_native_joint_' + label)
    if work.exists():
        raise RuntimeError('Choose a new label; evidence directory already exists: ' + str(work))
    rom = ROOT / ('build/rtos/firmware/prog.hex' if is_rtos else 'rtos/baseline125/src/cpu/prog_pacerv.hex')
    if not rom.is_file():
        raise RuntimeError('Missing firmware: ' + str(rom))
    vendor = ROOT / 'rtos/baseline125/src/cpu/vendor/pacerv_h3'
    contract = ROOT / 'scripts/outputs/medley_48k/layer_contract.json'
    weights = ROOT / 'scripts/outputs/medley_48k/weights_image.bin'
    contract_doc = json.loads(contract.read_text(encoding='utf-8'))
    weights_hash = hashlib.sha256(weights.read_bytes()).hexdigest()
    if weights_hash != contract_doc['image_sha256']:
        raise RuntimeError('Production weight image does not match its contract')
    baseline = json.loads((ROOT / 'rtos/BASELINE.json').read_text(encoding='utf-8-sig'))
    prefix = 'src/cpu/vendor/pacerv_h3/'
    prov = {'files': [{'file': row['path'][len(prefix):], 'sha256': row['sha256']}
                      for row in baseline['files'] if row['path'].startswith(prefix)]}
    vendor_paths = []
    for item in prov['files']:
        p = vendor / item['file']
        if hashlib.sha256(p.read_bytes()).hexdigest().lower() != item['sha256'].lower():
            raise RuntimeError('Frozen vendor changed: ' + str(p))
        vendor_paths.append(p)
    state = {'status': 'preparing', 'firmware': args.firmware, 'frame_major': True,
             'production_contract': str(contract), 'production_weights': str(weights),
             'weight_image_sha256': weights_hash,
             'backend': args.backend, 'DDR_bytes': 8388608,
             'DDR_IP_address_units': '32-bit words; 256-bit memory index = address[27:3]',
             'commands': [], 'inputs': []}

    def save():
        (work / 'PACERV_NATIVE_REPORT.json').write_text(json.dumps(state, indent=2) + '\n', encoding='utf-8')

    def execute(command, cwd, timeout):
        started = time.monotonic()
        live_log = work / (state['status'] + '.live.log')
        error_log = work / (state['status'] + '.stderr.log')
        with live_log.open('wb') as stream, error_log.open('wb') as errors:
            process = subprocess.Popen([str(x) for x in command], cwd=cwd,
                                       stdout=stream, stderr=errors)
            state['live_process_pid'] = process.pid
            state['live_log'] = str(live_log)
            save()
            try:
                code = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                state['status'] = 'observation_timeout'
                save()
                raise
        output = decode(live_log.read_bytes()) + decode(error_log.read_bytes())
        state['commands'].append({'command': [str(x) for x in command], 'cwd': str(cwd),
                                  'exit_status': code, 'output': output,
                                  'elapsed_seconds': round(time.monotonic() - started, 3)})
        state['live_process_pid'] = None
        save()
        return code, output

    def native_case(case, ignored_tool, ignored_options):
        # The base runner reads the historical image directly; replace only
        # its generated preload asset with the verified current image.
        (work / 'assets/weights.hex').write_text(''.join(f'{v:08x}\n' for v in weights.read_bytes()), encoding='ascii')
        model_source = ROOT / 'sim/experiments/npu_pingpong_native/ddr3_axi_model_full.sv'
        model_text = model_source.read_text(encoding='ascii')
        if model_text.count('[27:5]') < 2:
            raise RuntimeError('Review frozen model address-index repair')
        model_text = model_text.replace('[27:5]', '[27:3]')
        model_text = model_text.replace('(s_awaddr>>5)', '(s_awaddr>>3)')
        model_text = model_text.replace('(s_araddr>>5)', '(s_araddr>>3)')
        model_text = model_text.replace('wire [23:0] wr_mem_idx', 'wire [25:0] wr_mem_idx')
        model_text = model_text.replace('wire [23:0] rd_mem_idx', 'wire [25:0] rd_mem_idx')
        model = work / 'pacerv_ddr3_axi_model_full.sv'
        model.write_text('// Task-local 32-bit-IP-address correction; frozen source remains unchanged.\n' + model_text, encoding='ascii')
        text = Path(case.tb).read_text(encoding='ascii')
        text = once(text, 'reg clk=0; always #5 clk=~clk;', 'reg clk=0; always #4 clk=~clk;')
        old_top = (ROOT / 'src/ctrl/top_rv_core.v').read_text(encoding='ascii')
        new_top = (ROOT / 'rtos/baseline125/src/ctrl/instrec_top.v').read_text(encoding='ascii')
        old_launch = '    reg cpu_npu_pending;' + old_top.split('    reg cpu_npu_pending;', 1)[1].split('    npu_top ', 1)[0]
        new_launch = '    reg cpu_npu_pending;' + new_top.split('    reg cpu_npu_pending;', 1)[1].split('    npu_top ', 1)[0]
        text = once(text, old_launch, new_launch)
        text = once(text, '.ENABLE_M(0),.ENABLE_PREDICTOR(0)',
                    '.ENABLE_M(1),.ENABLE_C(1),.ENABLE_PREDICTOR(1)' + (',.IMEM_WORDS(4096),.DMEM_WORDS(4096)' if is_rtos else ''))
        if is_rtos:
            text = once(text, '$display("CPU UART %s",uart_line);', '''$display("CPU UART %s",uart_line);
       if(uart_line.len()>=10 && uart_line.substr(0,9)=="RTOS FATAL")
        $fatal(1,"RTOS fatal: %s",uart_line);
       if(busy && uart_line.len()>=14 && uart_line.substr(0,13)=="RTOS HEARTBEAT")
        rtos_heartbeats_busy=rtos_heartbeats_busy+1;''')
            text = once(text, 'if(uart_line==expected_report && expected_report!="") report_seen=1;',
                        'if(expected_report!="" && uart_line.len()>=expected_report.len() && uart_line.substr(0,expected_report.len()-1)==expected_report) report_seen=1;')
            text = once(text, 'if(cpu_trap) $fatal(1,"real CPU trapped cause=%h",cpu_trap_cause);', '''if(cpu_trap) begin
      if(cpu_trap_cause==32'h80000007) rtos_timer_interrupts=rtos_timer_interrupts+1;
      else if(cpu_trap_cause==32'd11) rtos_yield_traps=rtos_yield_traps+1;
      else $fatal(1,"unexpected RTOS CPU trap cause=%h",cpu_trap_cause);
     end''')
            text = once(text, 'if(!cpu_alive || cpu_requests!=1 || busy || start)',
                        'if(cpu_requests!=1 || cpu_acks!=1 || busy || start)')
        text = once(text, '.PROG_HEX("src/cpu/prog.hex")', '.PROG_HEX("' + rom.relative_to(ROOT).as_posix() + '")')
        text = once(text, '.npu_soft_start(cpu_npu_start));', '''.npu_soft_start(cpu_npu_start),
 .dd_req_valid(pacerv_dd_req_valid),.dd_req_ready(pacerv_dd_req_ready),
 .dd_req_address(pacerv_dd_req_address),.dd_req_write(pacerv_dd_req_write),
 .dd_req_data(pacerv_dd_req_data),.dd_req_strobe(pacerv_dd_req_strobe),
 .dd_rsp_valid(pacerv_dd_rsp_valid),.dd_rsp_ready(pacerv_dd_rsp_ready),
 .dd_rsp_data(pacerv_dd_rsp_data),.dd_rsp_error(pacerv_dd_rsp_error));''')
        text = once(text, "{2'b00,owner_valid,1'b0}", "{pacerv_m3_valid,1'b0,owner_valid,1'b0}")
        text = once(text, "{2'b00,owner_ready,1'b0}", "{pacerv_m3_ready,1'b0,owner_ready,1'b0}")
        text = once(text, ".m3_cmd(37'd0)", '.m3_cmd(pacerv_m3_cmd)')
        text = once(text, ".m3_wdata(256'd0)", '.m3_wdata(pacerv_m3_wdata),.m3_wstrb(pacerv_m3_wstrb)')
        text = once(text, 'ddr3_ctrl_axi #(.AXI_TO_LIMIT(64),.P3_QUOTA_TIMEOUT(32))',
                    'ddr3_ctrl_axi #(.M3_MASK_ENABLE(1),.AXI_TO_LIMIT(64),.P3_QUOTA_TIMEOUT(32))')
        if is_rtos:
            begin = text.index(' expected_report=$sformatf(')
            end = text.index(' $finish;', begin)
            text = text[:begin] + ''' expected_report=$sformatf("RTOS NPU top1=%0d last_class=%0d last_p=%0d c=%0d seq=1 tick=",top1,last_idx,last_pct,last_cycles);
     wait(report_seen);wait(cpu_acks==2);repeat(50) @(negedge clk);
     if(u_cpu.npu_probs_st || u_cpu.npu_done_st || u_cpu.npu_timeout_st) $fatal(1,"RTOS did not clear completed result status");
     if(!log_has("RTOS BOOT hz=125000000 tick=1000") || !log_has("RTOS IMC OK") || !log_has("RTOS DDR OK")) $fatal(1,"RTOS boot transcript incomplete");
     if(launches!=1 || cpu_requests<1 || cpu_requests>2 || cpu_acks!=2) $fatal(1,"unexpected RTOS control counts");
     if(u_cpu.result_cycles_q!==last_cycles || u_cpu.probs_pct_q!==last_pct || u_cpu.probs_idx_q!==last_idx) $fatal(1,"RTOS MMIO payload differs from actual NPU event");
     if(pacerv_ddr_requests!=33 || pacerv_ddr_responses!=33) $fatal(1,"RTOS DDR boot checks incomplete");
     if(rtos_timer_interrupts<100 || rtos_yield_traps<100 || rtos_heartbeats_busy<2) $fatal(1,"RTOS scheduling did not remain active during full NPU inference");
     $display("RTOS_NATIVE DDR requests=%0d responses=%0d",pacerv_ddr_requests,pacerv_ddr_responses);
     $display("RTOS_NATIVE scheduling timer_irqs=%0d yield_traps=%0d heartbeats_while_busy=%0d",rtos_timer_interrupts,rtos_yield_traps,rtos_heartbeats_busy);
     $display("CPU_NATIVE expected report=%s",expected_report);
     $display("RESULT: PASS production FreeRTOS tasks, full native golden NPU, immutable queue result report and acknowledgement");
    ''' + text[end:]
        else:
            check = ' if(pacerv_ddr_requests!=pacerv_ddr_responses || pacerv_ddr_requests<200) $fatal(1,"baseline DDR boot checks incomplete");\n'
            check += ' if(!log_has("PACERV IMC OK 0") || !log_has("PACERV DDR OK 0 CRC=")) $fatal(1,"baseline boot transcript incomplete");\n'
            check += ' $display("BASELINE_NATIVE DDR requests=%0d responses=%0d",pacerv_ddr_requests,pacerv_ddr_responses);\n'
            text = once(text, ' $display("CPU_NATIVE expected report=%s",expected_report);', check + ' $display("CPU_NATIVE expected report=%s",expected_report);')
        pos = text.rfind('endmodule')
        extra = 'integer rtos_timer_interrupts=0,rtos_yield_traps=0,rtos_heartbeats_busy=0;\n' + SHARED_DDR
        if args.debug_ddr:
            extra += '''
always @(posedge clk) if(rst_n) begin
 if(pacerv_dd_req_valid && pacerv_dd_req_ready && pacerv_ddr_requests<140)
  $display("DDREQ %0d addr=%h write=%b data=%h mask=%h",pacerv_ddr_requests,pacerv_dd_req_address,pacerv_dd_req_write,pacerv_dd_req_data,pacerv_dd_req_strobe);
 if(pacerv_dd_rsp_valid && pacerv_dd_rsp_ready && pacerv_ddr_responses<140)
  $display("DDRSP %0d data=%h err=%b",pacerv_ddr_responses,pacerv_dd_rsp_data,pacerv_dd_rsp_error);
 if(n_axi_wready && n_awid==3 && pacerv_ddr_requests<140)
  $display("DDWRITE addr=%h data=%h mask=%h modelidx=%h",n_model.aw_addr_r,n_axi_wdata,n_axi_wstrb,n_model.wr_mem_idx);
 if(n_rvalid_axi && n_rid==3 && pacerv_ddr_responses<140)
  $display("DDREAD addr=%h data=%h modelidx=%h",n_model.ar_addr_r,n_axi_rdata,n_model.rd_mem_idx);
end
'''
        text = text[:pos] + extra + text[pos:]
        tb = work / 'tb_pacerv_native_npu.sv'
        tb.write_text(text, encoding='ascii')
        rtl = []
        for relative in case.rtl:
            if relative.startswith('../cpu/rtl/') or 'ddr3_axi_model_full.sv' in relative:
                continue
            path = ROOT / 'rtos/rtl/rv32_cpu_subsys.sv' if is_rtos and relative == 'src/cpu/rv32_cpu_subsys.sv' else ROOT / 'rtos/baseline125' / relative
            if not path.is_file():
                raise FileNotFoundError('Frozen 125 MHz source missing: ' + str(path))
            rtl.append(path)
        rtl += vendor_paths + [model, ROOT / 'rtos/rtl/machine_timer.v',
                               ROOT / 'rtos/baseline125/src/ddr3/pace_cpu_ddr_bridge.v',
                               ROOT / 'rtos/baseline125/src/ddr3/ddr3_m3_share.v']
        rtl = list(dict.fromkeys(rtl))
        paths = rtl + [tb, rom, model_source, BASE / 'run.py', BASE / 'native_owner.vh',
                       BASE / 'cpu_joint.vh', ROOT / 'src/ctrl/top_rv_core.v',
                       ROOT / 'sim/experiments/npu_full_native/tb_npu_full_native.sv',
                       ROOT / 'rtos/baseline125/src/ctrl/instrec_top.v', ROOT / 'scripts/golden_pipeline.py',
                       contract, weights, ROOT / 'scripts/outputs/mel_tables.json',
                       ROOT / 'sim/experiments/npu_conv1/feat_u8.bin',
                       ROOT / 'src/mel/exp_lut.hex']
        paths += [Path(__file__).resolve(), ROOT / 'rtos/BASELINE.json']
        if is_rtos:
            paths += [ROOT / 'build/rtos/firmware/BUILD.json']
            paths += sorted(p for p in (ROOT / 'rtos/sw').rglob('*') if p.is_file())
        paths += sorted((work / 'assets').glob('*.hex'))
        state['inputs'] = [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]
        (work / 'inputs.json').write_text(json.dumps(state['inputs'], indent=2) + '\n', encoding='utf-8')
        state['status'] = 'prepared'
        save()
        print('PACERV_NATIVE_PREPARED ' + str(work), flush=True)
        log = work / 'pacerv_native_npu.log'
        if args.prepare_only:
            log.write_text('PREPARED: execution not requested\n', encoding='ascii')
            return SimpleNamespace(ok=False, output='PREPARED only\n', log_path=log)
        if args.backend == 'iverilog':
            iv = shutil.which('iverilog')
            vvp = shutil.which('vvp')
            if not iv or not vvp:
                raise RuntimeError('Put native Icarus iverilog/vvp on PATH')
            target = work / 'pacerv_native_npu.vvp'
            command = [iv, '-g2012', '-s', 'tb_npu_full_native', '-o', target, tb, *rtl]
        else:
            probe = ['wsl.exe', '-d', args.distro, '--cd', linux_path(ROOT), '--exec']
            code, output = execute(probe + [args.verilator, '--version'], ROOT, 30)
            if code or 'Verilator 5.' not in output:
                raise RuntimeError('Verilator 5 timing tool is not ready: ' + output)
            target = work / 'obj_pacerv/Vtb_npu_full_native'
            command = probe + [args.verilator, '--binary', '--timing', '-Wno-fatal',
                               '--top-module', 'tb_npu_full_native', '-j', str(args.jobs),
                               '--Mdir', linux_path(target.parent), '-CFLAGS', '-O2',
                               linux_path(tb)] + [linux_path(p) for p in rtl]
        state['status'] = 'compiling'
        save()
        print('PACERV_NATIVE_COMPILING backend=' + args.backend, flush=True)
        code, output = execute(command, ROOT, 1200)
        (work / 'pacerv_compile.log').write_text(output, encoding='utf-8')
        if code:
            state['status'] = 'compile_failed'; save()
            return SimpleNamespace(ok=False, output=output, log_path=work / 'pacerv_compile.log')
        if args.elaborate_only:
            state['status'] = 'elaboration_pass'; save()
            log.write_text('ELABORATE_PASS\n', encoding='ascii')
            return SimpleNamespace(ok=False, output='ELABORATE_PASS\n', log_path=log)
        state['status'] = 'running'; save()
        print('PACERV_NATIVE_RUNNING firmware=' + args.firmware, flush=True)
        command = [vvp, '-i', target] if args.backend == 'iverilog' else probe + [linux_path(target)]
        code, output = execute(command, ROOT, args.timeout)
        log.write_text(output, encoding='utf-8')
        complete = ('RESULT: PASS production FreeRTOS tasks, full native golden NPU, immutable queue result report and acknowledgement' if is_rtos else
                    'RESULT: PASS real CPU ROM MMIO launch, full native golden NPU, real result report and acknowledgement')
        ok = code == 0 and complete in output
        matches = re.findall(r'CPU UART RTOS NPU top1=(\d+) last_class=(\d+) last_p=(\d+) c=(\d+) seq=(\d+) tick=(\d+)', output)
        if is_rtos and ok and len(matches) != 1:
            raise RuntimeError('Expected exactly one actual RTOS queued inference result')
        state['actual_result'] = list(map(int, matches[0])) if matches else None
        for row in state['inputs']:
            if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() != row['sha256']:
                raise RuntimeError('Input changed during native validation: ' + row['path'])
        state['status'] = 'pass' if ok else 'run_failed'
        save()
        return SimpleNamespace(ok=ok, output=output, log_path=log)

    original_case, original_tools, original_argv = sim.run_case, sim._toolchain, sys.argv
    old_env = {key: os.environ.get(key) for key in ('INSTREC_CONTRACT', 'INSTREC_WEIGHTS_IMAGE')}
    os.environ['INSTREC_CONTRACT'] = str(contract)
    os.environ['INSTREC_WEIGHTS_IMAGE'] = str(weights)
    sim.run_case = native_case
    sim._toolchain = lambda: (Path(args.verilator), Path('make'))
    try:
        spec = importlib.util.spec_from_file_location('pacerv_native_base', BASE / 'run.py')
        base = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(base)
        # The base generator checks its historical UART spelling after the
        # callback. It still performs the same independent golden argmax test.
        old_run_case = sim.run_case
        def result_spelling_case(*case_args):
            result = old_run_case(*case_args)
            if result.ok:
                result.output = result.output.replace('CPU_NATIVE expected report=RTOS NPU top1=',
                                                      'CPU_NATIVE expected report=NPU top1=')
            return result
        sim.run_case = result_spelling_case
        sys.argv = ['run.py', '--run-label', label, '--frame-major']
        result = base.main()
        if args.prepare_only or args.elaborate_only:
            return 0 if state['status'] in ('prepared', 'elaboration_pass') else 1
        return result
    finally:
        sim.run_case, sim._toolchain, sys.argv = original_case, original_tools, original_argv
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        if work.exists():
            save()


if __name__ == '__main__':
    raise SystemExit(main())
