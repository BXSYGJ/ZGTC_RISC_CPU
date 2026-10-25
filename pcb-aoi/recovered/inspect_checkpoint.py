import importlib.util
import json
import os
import sys
from pathlib import Path
import yaml

os.environ.setdefault('YOLO_OFFLINE','true')
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

from ultralytics import YOLO


if __name__ == '__main__':
    try:
        root = Path(sys.argv[1]).resolve()
        report = Path(sys.argv[2]).resolve()
        weights = root / 'worktrees/algorithm-ai/runs/detect/pcb_defects/weights/best.pt'
        model = YOLO(str(weights))
        training_file = root / 'worktrees/algorithm-ai/algorithm/core/train.py'
        spec = importlib.util.spec_from_file_location('recovered_train',training_file)
        train = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(train)
        counts = train.validate_training_inputs(train.PRETRAINED_MODEL,train.DATA_CONFIG)
        result = {
            'weights':str(weights),'checkpoint_load':'PASS',
            'model_type':type(model.model).__name__,'task':model.task,'names':model.names,
            'total_parameters':sum(p.numel() for p in model.model.parameters()),
            'model_yaml':model.model.yaml,'checkpoint_version':model.ckpt.get('version'),
            'checkpoint_date':model.ckpt.get('date'),'checkpoint_epoch':model.ckpt.get('epoch'),
            'train_args':model.ckpt.get('train_args'),'train_metrics':model.ckpt.get('train_metrics'),
            'training_input_validation':{'result':'PASS','config':str(train.DATA_CONFIG),'resolved_dataset_root':str(train.resolve_dataset_path('../../../../datasets7.15现场增强后/pcb_defects')),'counts':counts},
        }
        report.write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str),encoding='utf-8-sig')
        report.with_suffix('.txt').write_text(str(model.model),encoding='utf-8-sig')
        definition = root / 'model-definition' / 'pcb_detector.yaml'
        definition.parent.mkdir(parents=True,exist_ok=True)
        definition.write_text(yaml.safe_dump(model.model.yaml,allow_unicode=True,sort_keys=False),encoding='utf-8-sig')
        print(json.dumps({k:v for k,v in result.items() if k not in ['train_args','train_metrics']},ensure_ascii=False,indent=2,default=str))
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        raise
