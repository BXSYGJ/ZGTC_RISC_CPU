"""Extend a frozen CoreMark checker's clock list for one supported PLL target.

Preserve every CRC, counter, timer, configuration and minimum-duration check.
The accepted upstream checker is never edited.
"""
import ast
from run_selected_clock import CLOCKS
from create_redirect_optimization import replace_once


def adapt(code, clock):
    if clock not in CLOCKS:
        raise ValueError('Unsupported selected PLL target')
    tree=ast.parse(code)
    matches=[node for node in ast.walk(tree) if isinstance(node,ast.Compare)
             and isinstance(node.left,ast.Name) and node.left.id=='frequency'
             and len(node.ops)==1 and isinstance(node.ops[0],ast.NotIn)
             and len(node.comparators)==1 and isinstance(node.comparators[0],ast.Tuple)]
    if len(matches)!=1:
        raise ValueError('Expected one explicit frequency allowlist')
    node=matches[0].comparators[0]
    values=ast.literal_eval(node)
    if any(type(value) is not int for value in values):
        raise ValueError('Unexpected clock allowlist entries')
    if clock in values:
        return code
    result=replace_once(code,ast.get_source_segment(code,node),repr(tuple(sorted((*values,clock)))))
    compile(result,'selected-CoreMark-checker','exec')
    return result


def prepare(path, clock):
    original=path.read_text(encoding='utf-8-sig')
    changed=adapt(original,clock)
    if changed!=original:
        before=path.with_name('original_check_coremark.py')
        if before.exists():
            raise ValueError('Original checker snapshot already exists')
        before.write_bytes(path.read_bytes())
        path.write_text(changed,encoding='utf-8')
