import random
import subprocess
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
CORE = PROJECT / 'experiments/loop_predictor_small/rv32_btb.sv'


class Reference:
    def __init__(self, index_bits=8, address_bits=16, hashed=1):
        self.index_bits = index_bits
        self.address_bits = address_bits
        self.hashed = hashed
        self.base = {}
        self.loops = {}

    def index(self, pc):
        mask = (1 << self.index_bits) - 1
        rotation = 4 % self.index_bits
        upper = (pc >> (self.index_bits + 2)) & mask
        folded = ((upper << rotation) | (upper >> (self.index_bits - rotation))) & mask
        return ((pc >> 2) ^ (folded if self.hashed else 0)) & mask

    def cycle(self, reset, invalidate, fetch, valid, pc, target, taken, conditional):
        index = self.index(pc)
        slot = (index >> 5) & 1
        if not reset or invalidate:
            self.base.clear()
            self.loops.clear()
        elif valid and pc < (1 << self.address_bits) and target < (1 << self.address_bits) and pc % 4 == target % 4 == 0:
            tag = pc >> (self.index_bits + 2)
            entry = self.base.get(index)
            if entry is None or entry['tag'] != tag or entry['conditional'] != conditional:
                entry = dict(tag=tag, target=target, conditional=conditional, history=taken if conditional else 0, counters=[2 if taken else 1] * 8)
                self.base[index] = entry
            else:
                entry['target'] = target
                if conditional:
                    history = entry['history']
                    entry['counters'][history] = max(0, min(3, entry['counters'][history] + (1 if taken else -1)))
                    entry['history'] = ((history << 1) | taken) & 7
            loop = self.loops.get(slot)
            if conditional and target < pc:
                if loop is None or loop['pc'] != pc:
                    loop = dict(pc=pc, count=0, trip=None, confidence=0, overflow=False)
                    self.loops[slot] = loop
                if taken:
                    loop['count'] += 1
                    if loop['count'] > 31:
                        loop['count'] = 31
                        loop['overflow'] = True
                        loop['confidence'] = 0
                else:
                    if loop['overflow'] or loop['count'] == 0:
                        loop['trip'] = None
                        loop['confidence'] = 0
                    else:
                        loop['confidence'] = min(3, loop['confidence'] + 1) if loop['trip'] == loop['count'] else 0
                        loop['trip'] = loop['count']
                    loop['count'] = 0
                    loop['overflow'] = False
            elif loop is not None and loop['pc'] == pc:
                del self.loops[slot]
        lookup = self.base.get(self.index(fetch))
        hit = fetch < (1 << self.address_bits) and fetch % 4 == 0 and lookup is not None and lookup['tag'] == fetch >> (self.index_bits + 2)
        predicted = False
        destination = (fetch + 4) & 0xffffffff
        if hit:
            destination = lookup['target']
            predicted = not lookup['conditional'] or lookup['counters'][lookup['history']] >= 2
            loop = self.loops.get((self.index(fetch) >> 5) & 1)
            if lookup['conditional'] and loop is not None and loop['pc'] == fetch and loop['confidence'] >= 2:
                predicted = loop['count'] < loop['trip']
        return int(hit), int(predicted), destination


def vectors(index_bits=8, address_bits=16, hashed=1):
    reference = Reference(index_bits, address_bits, hashed)
    rows = []
    def emit(fetch=0x514, pc=0x514, target=0x504, taken=1, conditional=1, valid=1, reset=1, invalidate=0):
        inputs = reset, invalidate, fetch, valid, pc, target, taken, conditional
        outputs = reference.cycle(*inputs)
        rows.append(' '.join(f'{value:x}' for value in inputs + outputs))
    emit(reset=0)
    for pc, target in ((0x514, 0x504), (0x414, 0x404), (0x584, 0x574), (0x900, 0x940)):
        for trips in (29, 29, 29, 29, 29, 4, 4, 4, 4, 31, 31, 31, 31, 32, 40, 40, 40, 40, 40, 0, 3, 3, 3, 3):
            for iteration in range(trips):
                emit(fetch=pc, pc=pc, target=target)
            emit(fetch=pc, pc=pc, target=target, taken=0)
        emit(fetch=pc, pc=pc, invalidate=1, valid=0)
        emit(fetch=pc, pc=pc, target=target)
        emit(fetch=pc, pc=pc, target=target, conditional=0)
        emit(fetch=pc, pc=pc, target=target, conditional=1)
    for repeat in range(6):
        for iteration in range(9):
            emit()
        emit(taken=0)
    emit(invalidate=1, valid=0)
    emit()
    for repeat in range(6):
        for iteration in range(9):
            emit()
        emit(taken=0)
    emit(reset=0)
    emit()
    for pc, target in ((0x515, 0x504), (0x514, 0x505), (0x10514, 0x504), (0x514, 0x10504)):
        for repeat in range(5):
            for iteration in range(7):
                emit(pc=pc, target=target)
            emit(pc=pc, target=target, taken=0)
    randomizer = random.Random(67531)
    pool = [0x100 + value * 4 for value in range(64)] + [0x500 + value * 4 for value in range(64)]
    for trial in range(8192):
        pc = randomizer.choice(pool)
        emit(fetch=pc if trial % 2 else randomizer.choice(pool), pc=pc, target=randomizer.choice(pool),
             taken=randomizer.randrange(2), conditional=randomizer.randrange(2), valid=int(trial % 7 != 0),
             reset=int(trial % 257 != 0), invalidate=int(trial % 223 == 0))
    for fetch in (0x515, 0x516, 0x517, 0x10514, 0xfffffffc):
        emit(fetch=fetch, valid=0)
    return rows


class SmallLoopRtlTests(unittest.TestCase):
    def simulate(self, index_bits=8, address_bits=16, hashed=1, mutation=None):
        source = CORE.read_text()
        if mutation:
            before, after = mutation
            self.assertEqual(source.count(before), 1)
            source = source.replace(before, after)
        with tempfile.TemporaryDirectory(prefix='small-loop-rtl-') as temporary:
            directory = Path(temporary)
            rtl = directory / 'rv32_btb.sv'
            rtl.write_text(source)
            data = directory / 'vectors.txt'
            rows = vectors(index_bits, address_bits, hashed)
            data.write_text(chr(10).join(rows) + chr(10))
            image = directory / 'test.vvp'
            compiled = subprocess.run(['iverilog', '-g2012', '-s', 'btb_history_width_tb',
                f'-Pbtb_history_width_tb.INDEX_BITS={index_bits}', f'-Pbtb_history_width_tb.ADDRESS_BITS={address_bits}',
                f'-Pbtb_history_width_tb.HASH_INDEX={hashed}', '-Pbtb_history_width_tb.HISTORY_BITS=3',
                '-Pbtb_history_width_tb.COUNTER_BITS=2', '-o', str(image), str(rtl), str(PROJECT / 'sim/btb_history_width_tb.sv')], capture_output=True, text=True, timeout=30)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run(['vvp', str(image), '+vectors=' + str(data)], capture_output=True, text=True, timeout=60)
            return result, len(rows)

    def test_exact_predictor_only_extension(self):
        parent = PROJECT / 'build/wb-byte-retime-stage/rtl/rv32_btb.sv'
        self.assertEqual(sha256(parent.read_bytes()).hexdigest().upper(), 'BBB08D9A074D31CF846B26B1BCF4456C991AFA03068A09EF4B96BEC46823F2DB')
        self.assertEqual(sha256(CORE.read_bytes()).hexdigest().upper(), '826199447568BB4D2BE0BF3D48CFF50E8393AE3EF722666EABA770BEDCC346E0')
        source = CORE.read_text()
        changes = [("    parameter integer COUNTER_BITS=2", "    parameter integer COUNTER_BITS=2,\n    parameter integer LOOP_INDEX_BITS=1,\n    parameter integer LOOP_INDEX_SHIFT=5,\n    parameter integer LOOP_COUNT_BITS=5"), ("    assign predicted_taken=prediction_hit && (!conditional[fetch_index] || pattern_prediction[history[fetch_index]]);", "    localparam integer LOOP_ENTRIES=1<<LOOP_INDEX_BITS;\n    reg [LOOP_ENTRIES-1:0] loop_valid;\n    reg [ADDRESS_BITS-3:0] loop_tags [0:LOOP_ENTRIES-1];\n    reg [LOOP_COUNT_BITS-1:0] loop_count [0:LOOP_ENTRIES-1];\n    reg [LOOP_COUNT_BITS-1:0] loop_trip [0:LOOP_ENTRIES-1];\n    reg [1:0] loop_confidence [0:LOOP_ENTRIES-1];\n    reg loop_overflow [0:LOOP_ENTRIES-1];\n    reg loop_direction [0:LOOP_ENTRIES-1];\n    wire [LOOP_INDEX_BITS-1:0] loop_fetch_index;\n    wire [LOOP_INDEX_BITS-1:0] loop_update_index;\n    genvar loop_index_bit;\n    generate for (loop_index_bit=0;loop_index_bit<LOOP_INDEX_BITS;loop_index_bit=loop_index_bit+1) begin: loop_index_wires\n        if (loop_index_bit+LOOP_INDEX_SHIFT<INDEX_BITS) begin: mapped\n            assign loop_fetch_index[loop_index_bit]=fetch_index[loop_index_bit+LOOP_INDEX_SHIFT];\n            assign loop_update_index[loop_index_bit]=update_index[loop_index_bit+LOOP_INDEX_SHIFT];\n        end else begin: unused_index\n            assign loop_fetch_index[loop_index_bit]=1'b0;\n            assign loop_update_index[loop_index_bit]=1'b0;\n        end\n    end endgenerate\n    wire loop_fetch_match=loop_valid[loop_fetch_index] &&\n        loop_tags[loop_fetch_index]==fetch_pc[ADDRESS_BITS-1:2];\n    wire loop_update_match=loop_valid[loop_update_index] &&\n        loop_tags[loop_update_index]==update_pc[ADDRESS_BITS-1:2];\n    wire loop_use=loop_fetch_match && loop_confidence[loop_fetch_index][1];\n    always @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin\n            loop_valid<=0;\n        end else if (invalidate) begin\n            loop_valid<=0;\n        end else if (train_update) begin\n            if (update_conditional && update_target<update_pc) begin\n                loop_valid[loop_update_index]<=1;\n                loop_tags[loop_update_index]<=update_pc[ADDRESS_BITS-1:2];\n                if (!loop_update_match) begin\n                    loop_count[loop_update_index]<=update_taken ? {{(LOOP_COUNT_BITS-1){1'b0}},1'b1} : {LOOP_COUNT_BITS{1'b0}};\n                    loop_trip[loop_update_index]<=0;\n                    loop_confidence[loop_update_index]<=0;\n                    loop_overflow[loop_update_index]<=0;\n                    loop_direction[loop_update_index]<=1;\n                end else if (update_taken) begin\n                    if (loop_count[loop_update_index]=={LOOP_COUNT_BITS{1'b1}}) begin\n                        loop_overflow[loop_update_index]<=1;\n                        loop_confidence[loop_update_index]<=0;\n                        loop_direction[loop_update_index]<=0;\n                    end else begin\n                        loop_count[loop_update_index]<=loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-1){1'b0}},1'b1};\n                        loop_direction[loop_update_index]<=(loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-1){1'b0}},1'b1})<loop_trip[loop_update_index];\n                    end\n                end else begin\n                    loop_count[loop_update_index]<=0;\n                    loop_overflow[loop_update_index]<=0;\n                    if (loop_overflow[loop_update_index] || loop_count[loop_update_index]==0) begin\n                        loop_trip[loop_update_index]<=0;\n                        loop_confidence[loop_update_index]<=0;\n                        loop_direction[loop_update_index]<=0;\n                    end else begin\n                        loop_trip[loop_update_index]<=loop_count[loop_update_index];\n                        loop_direction[loop_update_index]<=1;\n                        if (loop_trip[loop_update_index]==loop_count[loop_update_index]) begin\n                            if (loop_confidence[loop_update_index]!=2'b11)\n                                loop_confidence[loop_update_index]<=loop_confidence[loop_update_index]+2'b01;\n                        end else begin\n                            loop_confidence[loop_update_index]<=0;\n                        end\n                    end\n                end\n            end else if (loop_update_match) begin\n                loop_valid[loop_update_index]<=0;\n            end\n        end\n    end\n    assign predicted_taken=prediction_hit && (!conditional[fetch_index] ||\n        (loop_use ? loop_direction[loop_fetch_index] : pattern_prediction[history[fetch_index]]));")]
        for before, after in reversed(changes):
            self.assertEqual(source.count(after), 1)
            source = source.replace(after, before)
        self.assertEqual(source, parent.read_text())

    def test_independent_state_model(self):
        for index, address, hashed in ((8, 16, 1), (8, 32, 1), (8, 16, 0), (4, 32, 1), (1, 16, 1)):
            with self.subTest(index=index, address=address, hashed=hashed):
                result, count = self.simulate(index, address, hashed)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn(f'PASS local_history vectors={count}', result.stdout)
                print(f'PASS small loop model index={index} address={address} hash={hashed} vectors={count}')

    def test_runtime_mutants(self):
        mutations = {
            'unqualified_override': ('wire loop_use=loop_fetch_match && loop_confidence[loop_fetch_index][1];', 'wire loop_use=loop_fetch_match;'),
            'wrong_direction': ('loop_use ? loop_direction[loop_fetch_index]', 'loop_use ? !loop_direction[loop_fetch_index]'),
            'off_by_one': ("(loop_count[loop_update_index]+{{(LOOP_COUNT_BITS-1){1'b0}},1'b1})<loop_trip[loop_update_index]", "loop_count[loop_update_index]<loop_trip[loop_update_index]"),
            'accept_forward': ('update_conditional && update_target<update_pc', 'update_conditional'),
            'ignore_overflow': ("if (loop_count[loop_update_index]=={LOOP_COUNT_BITS{1'b1}})", "if (1'b0)"),
            'frozen_trip': ('loop_trip[loop_update_index]<=loop_count[loop_update_index];', 'loop_trip[loop_update_index]<=0;'),
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name):
                result, count = self.simulate(mutation=mutation)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('FAIL local_history', result.stdout + result.stderr)
                print('PASS small loop runtime rejection: ' + name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
