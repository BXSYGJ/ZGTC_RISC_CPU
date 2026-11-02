from pathlib import Path
import hashlib
import json
import csv
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyArrowPatch
import numpy as np

sys.stdout.reconfigure(encoding='utf-8')
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[2]
plt.rcParams.update({'font.family': 'Microsoft YaHei', 'font.size': 10,
                     'svg.fonttype': 'none', 'axes.unicode_minus': False})
BLUE, TEAL, ORANGE = '#235B80', '#168570', '#B97828'


def save_figure(figure, target):
    for extension in ('svg', 'png'):
        figure.savefig(target.with_suffix('.' + extension), dpi=220, facecolor='white')
    plt.close(figure)


def architecture(target):
    figure, axis = plt.subplots(figsize=(13.6, 5.4))
    figure.subplots_adjust(left=.02, right=.98, bottom=.03, top=.98)
    axis.set(xlim=(0, 13.6), ylim=(0, 5.4))
    axis.axis('off')

    def box(x, y, w, h, text, fill='#F3F6F8', color=BLUE):
        axis.add_patch(Rectangle((x, y), w, h, facecolor=fill, edgecolor=color, linewidth=1.2))
        axis.text(x+w/2, y+h/2, text, ha='center', va='center', fontsize=12, color='#203545')

    def arrow(points, color=BLUE, dashed=False):
        for first, last in zip(points[:-2], points[1:-1]):
            axis.plot([first[0], last[0]], [first[1], last[1]], color=color, lw=1.5,
                      ls='--' if dashed else '-')
        axis.add_patch(FancyArrowPatch(points[-2], points[-1], arrowstyle='-|>',
                                      mutation_scale=13, color=color, lw=1.5,
                                      linestyle='--' if dashed else '-'))

    stages = [(0.35, '取指与前端\nIF'), (3.0, '译码\nID'), (5.65, '执行\nEX'),
              (8.3, '访存\nMEM'), (10.95, '写回\nWB')]
    for x, label in stages:
        box(x, 4.25, 2.0, .85, label)
    for left, right in zip(stages, stages[1:]):
        arrow([(left[0]+2, 4.675), (right[0], 4.675)])
    box(.35, 2.25, 2.0, 1.0, '指令缓存\n16 KiB')
    arrow([(1.35, 3.25), (1.35, 4.25)])
    axis.text(1.55, 3.73, '指令字节', fontsize=10, va='center')
    box(5.25, 2.25, 2.65, 1.0, '预备乘积\n乘积与有效标志', '#E9F3F5')
    arrow([(6.0, 4.25), (6.0, 3.25)], dashed=True)
    axis.text(5.8, 3.74, '乘法准备', ha='right', va='center', fontsize=10)
    arrow([(7.2, 3.25), (7.2, 4.25)])
    axis.text(7.4, 3.74, '结果', va='center', fontsize=10)
    box(9.1, 2.25, 3.15, 1.0, '访存单元 LSU\n数据缓存 2 KiB', '#EAF4EF', TEAL)
    arrow([(7.65, 4.43), (8.04, 4.43), (8.04, 2.75), (9.1, 2.75)], TEAL)
    axis.text(8.16, 3.65, '提前请求', color=TEAL, fontsize=10, va='center')
    arrow([(9.3, 4.25), (9.3, 3.25)], ORANGE, True)
    axis.text(9.52, 3.77, '寄存请求', color=ORANGE, fontsize=10, va='center')
    box(3.15, .35, 6.9, .9, '共享后备 BRAM · 64 KiB', '#F4F5F6')
    arrow([(1.22, 2.25), (1.22, .8), (3.15, .8)])
    arrow([(3.15, 1.04), (1.65, 1.04), (1.65, 2.25)])
    axis.text(1.9, 1.65, '存储服务', va='center', fontsize=10)
    arrow([(10.58, 2.25), (10.58, 1.0), (10.05, 1.0)], TEAL)
    arrow([(10.05, .68), (11.02, .68), (11.02, 2.25)], TEAL)
    axis.text(11.23, 1.57, '存储服务', va='center', fontsize=10)
    save_figure(figure, target)


def waveform(algorithm, target):
    source = WORKSPACE / f'ILA_Core_Releases_20261101/H3_Retained_145125/waveforms/core_bench_{algorithm}.decoded.csv'
    with source.open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 1024
    trigger = next(i for i, row in enumerate(rows) if int(row['Trigger']))
    start, stop = trigger-8, trigger+24
    assert 0 <= start < stop <= len(rows)
    title = {'list': '链表算法', 'matrix': '矩阵算法', 'state': '状态机算法'}[algorithm]
    figure, axis = plt.subplots(figsize=(14, 7.8))
    figure.subplots_adjust(left=.155, right=.98, bottom=.105, top=.79)
    figure.text(.155, .956, f'{title}：函数入口附近的流水线活动', fontsize=17, weight='bold')
    figure.text(.155, .91, 'PaceRV 结果保持版 · 本地 RTL 仿真 · 32 边沿放大视图', fontsize=11, color=BLUE)
    pc = [int(row['EX_PC'], 0) for row in rows]
    figure.text(.155, .869, f'触发条件：EX_PC = 0x{pc[trigger]:08X} 且 EX 传递有效；完整采样深度：1,024 边沿',
                fontsize=10, color='#4D5C65')
    channels = [('if_valid','取指有效 IF'), ('id_valid','译码有效 ID'), ('ex_valid','执行有效 EX'),
                ('mem_valid','访存有效 MEM'), ('wb_valid','写回事件 WB'), ('id_fire','译码传递 ID'),
                ('ex_fire','执行传递 EX'), ('mem_fire','访存传递 MEM'), ('mem_flush','访存冲刷'),
                ('frontend_fire','前端传递'), ('Trigger','触发条件')]
    for i in range(start, stop):
        axis.add_patch(Rectangle((i, 11.43), 1, .54, facecolor='#F0F4F7', edgecolor='#9DACB5', lw=.6))
        if i % 2 == 0 or i == trigger:
            axis.text(i+.5, 11.7, f'{pc[i]:04X}', ha='center', va='center', fontsize=8,
                      family='DejaVu Sans Mono', color=BLUE)
    positions, labels = [11.7], ['执行地址 PC（十六进制）']
    x = np.arange(start, stop+1)
    for index, (key, label) in enumerate(channels):
        y = 10.6-index
        values = np.array([int(row[key]) for row in rows[start:stop]])
        axis.step(x, np.r_[values, values[-1]]*.55+y-.27, where='post', linewidth=1.25,
                  color=ORANGE if key in ('Trigger','mem_flush') else BLUE if index < 5 else TEAL)
        axis.axhline(y-.35, color='#E2E6E9', lw=.5, zorder=0)
        positions.append(y)
        labels.append(label)
    axis.axvline(trigger, color=ORANGE, linestyle='--', lw=1)
    axis.set(xlim=(start,stop), ylim=(-.05,12.17), yticks=positions, yticklabels=labels)
    axis.set_xticks(np.arange(start,stop+1,2))
    axis.set_xlabel('1,024 边沿采样窗口中的边沿序号', labelpad=10)
    axis.tick_params(axis='y', length=0, pad=11)
    axis.grid(axis='x', color='#E2E6E9', lw=.55)
    for spine in ('left','right','top'):
        axis.spines[spine].set_visible(False)
    secondary = axis.secondary_xaxis('top', functions=(lambda x:x-trigger, lambda x:x+trigger))
    secondary.set_xlabel('相对触发边沿', labelpad=6)
    figure.text(.155,.026,'高电平表示信号为 1；竖虚线标出函数入口触发边沿。', fontsize=10, color='#4D5C65')
    save_figure(figure, target)
    return source


def main():
    assets = ROOT / 'assets'
    assets.mkdir(exist_ok=True)
    provenance = []
    diagram = WORKSPACE / 'Attend_an_academic_conference/camera-ready/manuscript/figures/fig1_architecture.pdf'
    architecture(assets / 'cpu-architecture')
    provenance.append({'file': 'assets/cpu-architecture.png', 'source': diagram.relative_to(WORKSPACE).as_posix(),
                       'source_sha256': hashlib.sha256(diagram.read_bytes()).hexdigest(), 'operation': 'Chinese vector reconstruction; source architecture connections retained'})
    for algorithm in ('list', 'matrix', 'state'):
        target = assets / f'coremark-{algorithm}.png'
        source = waveform(algorithm, target)
        provenance.append({'file': target.relative_to(ROOT).as_posix(), 'source': source.relative_to(WORKSPACE).as_posix(),
                           'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                           'sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
                           'operation': 'Chinese waveform redrawn from archived decoded CSV; trigger-relative 32-edge slice; local RTL simulation'})
    measured = []
    for release in ('H3_Base_145125', 'H3_Retained_145125'):
        source = WORKSPACE / 'PaceRV/cpu' / release / 'PERFORMANCE.json'
        rows = json.loads(source.read_text(encoding='utf-8-sig'))
        record = next(row for row in rows if row['configuration'] == 'V0')
        assert abs(record['coremark'] - record['iterations'] * record['clock_hz'] / record['cycles']) < 1e-9
        assert abs(record['coremark_per_mhz'] - record['iterations'] * 1e6 / record['cycles']) < 1e-9
        record['elapsed_seconds'] = record['cycles'] / record['clock_hz']
        measured.append(record)
    vex = json.loads((WORKSPACE / 'PaceRV-MCSoC2026/data/implementation/vex.json').read_text(encoding='utf-8-sig'))
    comparison = {
        'vex_coremark_per_mhz': vex['coremark_per_mhz_from_native_cycles'],
        'pacerv_retained_gain_percent': 100 * (measured[1]['coremark_per_mhz'] / vex['coremark_per_mhz_from_native_cycles'] - 1),
        'retention_demand_reduction_percent': 100 * (1 - 4373 / 375063),
        'vex_cycle_source': 'native RTL simulation', 'pacerv_cycle_source': 'archived board measurements'
    }
    article = {
        'title': 'Design of a Configurable Five-Stage Pipeline Processor Core Based on RV32IM',
        'doi': '10.3390/electronics13010120', 'url': 'https://www.mdpi.com/2079-9292/13/1/120',
        'verified_on': '2026-11-02', 'table_2_coremark_per_mhz': 3.51,
        'fpga_reported_in_section_4': 'Xilinx Artix7', 'fpga_frequency_mhz_reported': 200,
        'lut_ff_bram_counts': 'not reported in acquired full article text/tables',
        'score_to_board_configuration_binding': 'not explicitly established by the reported benchmark and FPGA-prototype paragraphs',
        'isa': 'RV32IM; exact RV32IMC comparison class differs',
        'acquisition': 'rendered publisher full text and tables; NJU inspect_source page acquisition; no PDF download',
        'interpretation': 'FPGA implementation cannot be excluded; resource cost cannot be inferred as high from missing counts.'
    }
    sources = [
        'PaceRV/cpu/H3_Base_145125/PERFORMANCE.json',
        'PaceRV/cpu/H3_Retained_145125/PERFORMANCE.json',
        'PaceRV-MCSoC2026/data/implementation/vex.json',
        'PaceRV/docs/architecture.md', 'PaceRV/docs/reproducibility.md', 'PaceRV/docs/performance-context.md',
        'PaceRV-MCSoC2026/docs/EVIDENCE.md', 'PaceRV-MCSoC2026/paper.json',
        'ILA_Core_Releases_20261101/analysis/IMPLEMENTATION_RESULTS.md', 'ILA_Core_Releases_20261101/analysis/README.md',
        'Attend_an_academic_conference/camera-ready/manuscript/main.tex',
        'ccfa-workfiles/competition/fpga-submission-study/downloads/cases/ultra-vision-2024/00-README.md',
        'ccfa-workfiles/competition/fpga-submission-study/downloads/cases/anlu-first-prize-2025/00-README.md',
        'ccfa-workfiles/competition/fpga-submission-study/cache/2026-design-report-template.md',
    ]
    evidence = {
        'date': '2026-11-02', 'artifact': 'CPU_REPORT.md',
        'scope': 'CPU subsystem report for integration with teammates competition report',
        'board_measurements': measured, 'comparisons': comparison, 'assets': provenance,
        'higher_reported_rv32im_result': article,
        'sources': [{'path': path, 'sha256': hashlib.sha256((WORKSPACE / path).read_bytes()).hexdigest()} for path in sources],
        'style_transfer': 'Ultra-Vision: specifications first, architectural decisions linked to benefits, concrete results and figures; Anlu: system/module relations and reproducibility. Original phrasing and engineering-status chatter not copied.',
        'claim_choices': {'sota_scope': 'verified publicly reported single-issue five-stage in-order RV32IMC FPGA implementations',
                          'publication': 'MCSoC 2026 accepted; no assertion of DOI assignment or IEEE indexing',
                          'frequency': 'qualified operating points and routed closure; no claim to an unmeasured physical maximum',
                          'ila_waveforms': 'local RTL simulation; no physical-board ILA acquisition claimed'}
    }
    (ROOT / 'EVIDENCE.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n', encoding='utf-8-sig')
    print(json.dumps({'measurements': measured, 'comparisons': comparison, 'asset_count': len(provenance)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
