"""Compile explicit eight-class percentage keyframes to a 10 Hz demo ROM.
Input JSON: [{"time":0,"pct":[0,0,0,0,100,0,0,0]}, ...].
Values are displayed as supplied with linear interpolation, not predictions.
"""
import argparse
import json
import math
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
CLASSES = ['clarinet','distorted_guitar','female_voice','flute','piano','tenor_sax','trumpet','violin']
def compile_curve(points):
    if not points or points[0]['time'] != 0:
        raise ValueError('First keyframe must start at zero seconds')
    previous = -1
    for p in points:
        t = p['time']
        if not math.isfinite(t) or t <= previous or len(p['pct']) != 8:
            raise ValueError('Strictly increasing finite times and eight percentages required')
        if any(not math.isfinite(x) or x < 0 or x > 100 for x in p['pct']):
            raise ValueError('Percentages must be finite and within 0..100')
        previous = t
    count = math.ceil(points[-1]['time'] * 10) + 1
    if count > 4096: raise ValueError('Maximum duration is 409.5 seconds')
    words = []
    k = 0
    for i in range(count):
        t = i / 10
        while k+1 < len(points) and t >= points[k+1]['time']: k += 1
        a = points[k]
        b = points[min(k+1,len(points)-1)]
        f = 0 if a is b else min(1,(t-a['time'])/(b['time']-a['time']))
        values = [round(x+(y-x)*f) for x,y in zip(a['pct'],b['pct'])]
        words.append(sum(x << (8*j) for j,x in enumerate(values)))
    return words
if __name__ == '__main__':
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('json_file',type=Path); args=ap.parse_args()
    points=json.loads(args.json_file.read_text(encoding='utf-8-sig'))
    words=compile_curve(points)
    (ROOT/'src/ui/demo_confidence.hex').write_text(''.join(f'{w:016x}\n' for w in words+[words[-1]]*(4096-len(words))),encoding='ascii')
    import re
    p=ROOT/'src/ui/demo_confidence_player.v'
    p.write_text(re.sub(r'parameter SAMPLE_COUNT = \d+',f'parameter SAMPLE_COUNT = {len(words)}',p.read_text(encoding='utf-8')),encoding='utf-8')
    print(f'{len(words)} samples, 10 Hz, {CLASSES}; ready for new build')
