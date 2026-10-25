import collections
import hashlib
import json
import importlib.util
import sys
from pathlib import Path

import cv2
import numpy as np
import onnx


def inspect(root):
    weights = root / 'worktrees/algorithm-ai/runs/detect/pcb_defects/weights'
    model_path = weights / 'best.onnx'
    model = onnx.load(str(model_path))
    onnx.checker.check_model(model)
    shapes = lambda values: {v.name: [d.dim_value or d.dim_param for d in v.type.tensor_type.shape.dim] for v in values}
    inputs = shapes(model.graph.input)
    outputs = shapes(model.graph.output)
    input_shape = next(iter(inputs.values()))
    if not all(isinstance(x, int) and x > 0 for x in input_shape):
        raise ValueError(f'Expected fixed input shape; got {input_shape}')
    net = cv2.dnn.readNetFromONNX(str(model_path))
    net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
    net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
    net.setInput(np.zeros(input_shape, dtype=np.float32))
    prediction = net.forward()
    files = {}
    for p in [model_path, weights / 'best.pt', root / 'worktrees/algorithm-ai/yolov8n.pt']:
        files[str(p.relative_to(root)).replace(chr(92), '/')]= {'bytes':p.stat().st_size, 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    result = {
        'root':str(root),
        'onnx_checker':'PASS',
        'producer':model.producer_name,
        'producer_version':model.producer_version,
        'opsets':{op.domain or 'ai.onnx':op.version for op in model.opset_import},
        'metadata':{v.key:v.value for v in model.metadata_props},
        'inputs':inputs,
        'outputs':outputs,
        'operation_counts':dict(collections.Counter(node.op_type for node in model.graph.node)),
        'opencv_version':cv2.__version__,
        'opencv_cpu_zero_input':{'input_shape':input_shape,'output_shape':list(prediction.shape),'all_finite':bool(np.isfinite(prediction).all()),'result':'PASS'},
        'files':files,
    }
    if len(sys.argv) > 3:
        image_path = Path(sys.argv[3]).resolve()
        module_path = root / 'loong_detect/detect_opencv_dnn.py'
        spec = importlib.util.spec_from_file_location('aoi_postprocess', module_path)
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        image = cv2.imread(str(image_path))
        if image is None:
            raise ValueError(f'Image could not be read: {image_path}')
        padded, scale, left, top = helper.letterbox(image, input_shape[-1])
        blob = cv2.dnn.blobFromImage(padded, 1.0 / 255.0, (input_shape[-1], input_shape[-2]), swapRB=True, crop=False)
        net.setInput(blob)
        prediction = net.forward()
        detections = helper.postprocess(prediction, image.shape[:2], scale, left, top, 0.25, 0.45)
        for detection in detections:
            helper.draw_detection(image, detection['bbox'], str(detection['class_id']), detection['confidence'])
        output_image = Path(sys.argv[2]).with_name('verified-inference.jpg')
        if not cv2.imwrite(str(output_image), image):
            raise ValueError('Could not write annotated image')
        result['real_image_inference'] = {'source':str(image_path),'image_shape':list(image.shape),'conf_threshold':0.25,'iou_threshold':0.45,'detections':detections,'annotated_image':str(output_image),'result':'PASS'}
    return result


if __name__ == '__main__':
    try:
        result = inspect(Path(sys.argv[1]).resolve())
        Path(sys.argv[2]).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8-sig')
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        raise
