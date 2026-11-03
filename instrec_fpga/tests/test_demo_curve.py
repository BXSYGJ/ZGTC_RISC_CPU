import sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from set_demo_curve import compile_curve

def test_interpolation_and_final_endpoint():
    words=compile_curve([{'time':0,'pct':[100,0,0,0,0,0,0,0]},
                         {'time':0.2,'pct':[0,0,0,0,0,0,0,100]}])
    assert words == [100, 50+(50<<56), 100<<56]

@pytest.mark.parametrize('points', [[], [{'time':1,'pct':[0]*8}],
    [{'time':0,'pct':[101]*8}], [{'time':0,'pct':[0]*7}],
    [{'time':0,'pct':[0]*8},{'time':410,'pct':[0]*8}]])
def test_bad_curve_rejected(points):
    with pytest.raises(ValueError): compile_curve(points)
