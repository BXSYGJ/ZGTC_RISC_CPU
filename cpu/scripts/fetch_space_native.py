import hashlib
import re


SIGNALS=('ex_fire_without_irq','ex_fire_with_irq','id_fire_with_irq','fetch_accept_space')


def inspect_fetch_control_boundaries(native):
    modules=re.findall(r'\bmodule\s+rv32_core\b[\s\S]*?\bendmodule\b',native)
    if len(modules)!=1:
        raise ValueError('Ambiguous native CPU module')
    core=modules[0]
    records=[]
    for signal in SIGNALS:
        aliases=re.findall(r'assign\s+'+signal+r'\s*=\s*([^;]+);',core)
        if len(aliases)>1:
            raise ValueError('Ambiguous fetch control alias: '+signal)
        target=aliases[0].strip() if aliases else signal
        hierarchy=[target]
        region=core
        for depth in range(4):
            drivers=re.findall(r'GTP_LUT[1-6](?:D|CARRY)?\s+[^;]*\.(?:Z|Z5|COUT)\s*\('+re.escape(target)+r'\s*\)[^;]*;',region)
            if drivers:
                break
            connections=re.findall(r'\.'+re.escape(target)+r'\s*\(([^)]+)\)',native)
            if len(connections)!=1:
                break
            target=connections[0].strip()
            if target in hierarchy:
                raise ValueError('Cyclic fetch control hierarchy: '+signal)
            hierarchy.append(target)
            region=native
        consumers=re.findall(r'\.I[0-5]\s*\('+signal+r'\)',core)
        if len(drivers)!=1 or not consumers:
            raise ValueError('Missing active fetch control boundary: '+signal)
        records.append(dict(signal=signal,hierarchy=hierarchy,alias=target,driver_sha256=hashlib.sha256(drivers[0].encode()).hexdigest().upper(),consumers=len(consumers)))
    return records
