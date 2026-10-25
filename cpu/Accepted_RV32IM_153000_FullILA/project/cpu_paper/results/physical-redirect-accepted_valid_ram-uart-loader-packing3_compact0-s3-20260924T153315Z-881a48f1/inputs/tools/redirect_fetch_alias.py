"""Prove and remap only a direct scalar fetch_complete alias for the v27 ILA.

The native inserter must still report all 42 data and 33 trigger channels. This
helper does not validate or waive any channel; the frozen validator does that.
"""
import hashlib
import re

CANONICAL = 'board/soc/core/fetch_complete'
FIC = r'(?m)^Project\.unit<0>\.dataChannel<40>=([^\r\n]+)'
OUTPUT = r'(?m)^(Data Channel 40:\s*)(\S+)([^\S\r\n]*)$'


def require(value, message):
    if not value:
        raise ValueError(message)


def prove(netlist, probe):
    available = re.findall(r'^\d+\s*:\s*(\S+)\s+\S+\s*$', probe, re.M)
    require(available.count(CANONICAL) <= 1, 'Ambiguous fetch_complete probe')
    # Strip comments so a textual example cannot serve as electrical evidence.
    clean = re.sub(r'/\*.*?\*/|//[^\r\n]*', '', netlist, flags=re.S)
    modules = re.findall(r'\bmodule rv32_core\b(.*?)\bendmodule\b', clean, re.S)
    require(len(modules) == 1, 'CPU module missing or ambiguous')
    core = modules[0]
    scalar_wire = len(re.findall(r'\bwire\s+fetch_complete\s*;', core)) == 1
    scalar_output = len(re.findall(r'\boutput\s+fetch_complete\s*[,)]', core)) == 1
    aliases = re.findall(r'\bassign\s+([A-Za-z_]\w*)\s*=\s*fetch_complete\s*;', core)
    # ADS may list both scalar output aliases before flattening, then retain
    # only the assigned output during ILA insertion. Prefer the proven alias
    # in that precise form; a probed internal wire keeps the historical path.
    if available.count(CANONICAL) == 1 and (not scalar_output or not aliases):
        return None
    require(scalar_wire or scalar_output, 'fetch_complete must be a scalar wire or output')
    require(len(aliases) == 1, 'Missing or ambiguous direct fetch_complete alias')
    alias = aliases[0]
    require(alias != 'fetch_complete', 'Self alias is not a proof')
    # Only accept the synthesizer scalar output-port form encountered here.
    require(len(re.findall(r'\boutput\s+' + re.escape(alias) + r'\s*[,)]', core)) == 1,
            'Alias must be a scalar output port')
    assignments = re.findall(r'\bassign\s+' + re.escape(alias) + r'\s*=([^;]*);', core)
    require(len(assignments) == 1 and assignments[0].strip() == 'fetch_complete',
            'Alias has ambiguous assignment')
    actual = 'board/soc/core/' + alias
    require(available.count(actual) == 1, 'Alias missing or ambiguous in native probe')
    proof = dict(actual=actual, canonical=CANONICAL,
                proof='Unique scalar output with direct assign to fetch_complete in rv32_core',
                assignment='assign ' + alias + ' = fetch_complete;',
                netlist_text_sha256=hashlib.sha256(netlist.encode('utf-8')).hexdigest(),
                probe_text_sha256=hashlib.sha256(probe.encode('utf-8')).hexdigest())
    if available.count(CANONICAL) == 1:
        proof['canonical_output_present_before_flattening'] = True
    return proof


def prepare(netlist, probe, fic):
    selected = re.findall(FIC, fic)
    require(selected == [CANONICAL], 'Unexpected template fetch_complete channel')
    proof = prove(netlist, probe)
    if proof is None:
        return fic, None
    return re.sub(FIC, lambda _: 'Project.unit<0>.dataChannel<40>=' + proof['actual'], fic), proof


def normalize(netlist, probe, fic, output, proof):
    require(prove(netlist, probe) == proof, 'Fetch alias proof changed')
    if proof is None:
        return fic, output, {}
    actual = proof['actual']
    require(re.findall(FIC, fic) == [actual], 'Native FIC lost fetch_complete alias')
    channels = re.findall(OUTPUT, output)
    require(len(channels) == 1 and channels[0][1] == actual,
            'Native inserter did not verify fetch_complete alias as data channel 40')
    canonical_fic = re.sub(FIC, lambda _: 'Project.unit<0>.dataChannel<40>=' + CANONICAL, fic)
    canonical_output = re.sub(OUTPUT, lambda m: m[1] + CANONICAL + m[3], output)
    return canonical_fic, canonical_output, {actual: CANONICAL}
