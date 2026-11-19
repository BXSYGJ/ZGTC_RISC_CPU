"""Play selected demo segments on NICEHCK and compare captured PCM with golden.

Example: python scripts/diagnose_live_pcm.py --classes 3,0,6,2 --label after
Endpoint volume/mute are preserved. Every diagnostic lock is released in finally.
The page-order restoration is a diagnostic comparison, never compensation
applied to the model or the played signal. Existing captures are never overwritten.
"""
from pathlib import Path
import sys,json,time,argparse,datetime
import numpy as np
from scipy.io import wavfile
import serial
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'scripts'))
import audio_player as ap
import diag_dump as dd
import diag_spectrum as ds
import golden_pipeline as gp
def read_completed_pcm(ser,status):
    """Completed half has 6144 padding bytes after its valid PCM samples."""
    half=1-(status['win']&1)
    raw=ds.read_ddr_robust(ser,dd.PCM_LASE+half*dd.PCM_WIN_STRIDE,dd.PCM_WIN_BYTES)
    return half,raw


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--wav',type=Path,default=Path('D:/0000/111/001/Pango/InstRec/data/demo/demo_90s_8class.wav'))
    parser.add_argument('--classes',default='3,0,6,2')
    parser.add_argument('--label',default='capture')
    parser.add_argument('--device-hint',default='NICEHCK')
    parser.add_argument('--port',default='COM5')
    parser.add_argument('--settle',type=float,default=9.0)
    parser.add_argument('--gain-db',type=float,default=0.0)
    args=parser.parse_args(argv)
    if not args.label.replace('_','').replace('-','').isalnum():
        parser.error('label must contain only letters, digits, underscores or hyphens')
    classes=[int(v) for v in args.classes.split(',')]
    if not classes or any(v<0 or v>7 for v in classes):
        parser.error('classes must be comma separated numbers 0..7')
    timeline=json.loads(args.wav.with_suffix('.timeline.json').read_text(encoding='utf-8'))
    segments={row['class_idx']:row for row in timeline['segments']}
    out=root/'reports'/('live_pcm_'+args.label+'_'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir(exist_ok=False)
    sr,source=wavfile.read(args.wav)
    if sr!=48000 or source.dtype!=np.int16 or source.ndim!=1:
        parser.error('source must be 48kHz mono signed 16-bit PCM')
    print('DEVICE',ap.list_render_devices(args.device_hint),flush=True)
    print('REPORT',out,flush=True)
    tables=gp.load_mel_tables(root/'scripts/outputs/mel_tables_48k.json')
    contract=gp.load_layer_contract(root/'scripts/outputs/medley_48k/layer_contract.json')
    weights=gp.load_weights_from_image(contract,root/'scripts/outputs/medley_48k/weights_image.bin')
    rec=contract.get('quant_stub_input_contract',contract)
    def golden(pcm):
        g=gp.run_mel_pipeline(pcm,tables,inv_s_in=int(rec['inv_s_in']),zp_in=int(rec['zp_in']))
        n=gp.npu_forward(g['feat'],contract,tables['exp_lut'],weights=weights)
        return {'top1':int(n['top1']),'logits':[int(v) for v in n['logits']]}
    rows=[]
    for category in classes:
        sec=segments[category]['start']+2.0
        print('START class',category,flush=True)
        unit=source[int(sec*sr):int(sec*sr)+132096]
        player=ap.StreamingPlayer(unit,device_hint=args.device_hint,gain_db=args.gain_db).start()
        try:
            with serial.Serial(args.port,115200,timeout=.3) as ser:
                try:
                    ser.write(b'X');time.sleep(.1);ser.write(b'U')
                    time.sleep(args.settle)
                    ser.write(b'L');time.sleep(.8)
                    status=dd.read_status(ser)
                    logits=dd.read_logits(ser)
                    half,raw=read_completed_pcm(ser,status)
                    (out/f'class{category}.raw').write_bytes(raw)
                finally:
                    ser.write(b'U');time.sleep(.1)
                    final_status=dd.read_status(ser)
        finally:
            player.stop()
        pcm=np.frombuffer(raw,'<i2').copy()
        fixed=pcm.reshape(-1,16)[:,::-1].reshape(-1).copy()
        row={'class':category,'source_start_seconds':sec,'status':status,'half':half,
             'board_logits':logits,'board_top1':int(np.argmax(logits)),
             'golden_captured':golden(pcm),'golden_page_order_restored':golden(fixed),
             'pcm_std':float(pcm.astype(float).std()),'player':player.stats(),'final_status':final_status}
        rows.append(row)
        (out/'class_captures.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        print(json.dumps(row),flush=True)

    return 0 if all(r['board_logits']==r['golden_captured']['logits'] and r['board_top1']==r['class'] for r in rows) else 1


if __name__ == '__main__':
    raise SystemExit(main())
