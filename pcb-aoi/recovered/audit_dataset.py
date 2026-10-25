import collections
import hashlib
import json
import math
import os
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath

from PIL import Image
import yaml

sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

def digest_file(file):
    with Path(file).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def audit(archive_path, output_root):
    archive_before = digest_file(archive_path)
    verified = []
    with zipfile.ZipFile(archive_path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'ZIP CRC failure: {bad}')
        seen = set()
        for entry in archive.infolist():
            relative = PurePosixPath(entry.filename)
            if relative.is_absolute() or '..' in relative.parts or any(':' in p for p in relative.parts):
                raise ValueError(f'Invalid archive path: {relative}')
            if stat.S_ISLNK(entry.external_attr >> 16):
                raise ValueError(f'Archive contains a symbolic link: {relative}')
            target = output_root.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(output_root.resolve()):
                raise ValueError(f'Archive path leaves destination: {relative}')
            if entry.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            key = str(target).casefold()
            if key in seen:
                raise ValueError(f'Duplicate archive entry: {relative}')
            seen.add(key)
            original = archive.read(entry)
            original_hash = hashlib.sha256(original).hexdigest()
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if digest_file(target) != original_hash:
                    raise ValueError(f'Destination exists with different content: {target}')
            else:
                target.write_bytes(original)
            copied_hash = digest_file(target)
            if copied_hash != original_hash:
                raise ValueError(f'Extracted content differs: {relative}')
            verified.append({'relative_path':relative.as_posix(),'bytes':len(original),'sha256':original_hash})

    dataset_root = output_root / 'datasets7.15现场增强后' / 'pcb_defects'
    config = yaml.safe_load((dataset_root / 'dataset.yaml').read_text(encoding='utf-8-sig'))
    classes = (dataset_root / 'classes.txt').read_text(encoding='utf-8-sig').splitlines()
    preparation = json.loads((dataset_root / 'dataset_preparation_report.json').read_text(encoding='utf-8-sig'))
    image_extensions = {'.jpg','.jpeg','.png','.bmp','.tif','.tiff','.webp'}
    image_files = sorted(p for p in dataset_root.rglob('*') if p.is_file() and p.suffix.lower() in image_extensions)
    bad_images = []
    image_hashes = {}
    for image in image_files:
        try:
            with Image.open(image) as opened:
                opened.verify()
        except Exception as exc:
            bad_images.append({'file':str(image),'error':str(exc)})
        image_hashes[image] = digest_file(image)
    grouped = collections.Counter(str(p.parent.relative_to(dataset_root)).replace(os.sep,'/') for p in image_files)
    splits = {}
    invalid_labels = []
    for split in ['train','val','test']:
        image_dir = dataset_root / 'images' / split
        label_dir = dataset_root / 'labels' / split
        images = sorted(p for p in image_dir.glob('*') if p.suffix.lower() in image_extensions and p.is_file())
        labels = sorted(label_dir.glob('*.txt'))
        if not images and not labels:
            continue
        image_stems = {p.stem for p in images}
        label_stems = {p.stem for p in labels}
        object_counts = collections.Counter()
        formats = collections.Counter()
        empty = []
        for label in labels:
            lines = label.read_text(encoding='utf-8-sig').splitlines()
            if not any(line.strip() for line in lines):
                empty.append(label.name)
            for number,line in enumerate(lines,1):
                if not line.strip():
                    continue
                try:
                    fields = line.split()
                    class_id = int(fields[0])
                    coords = [float(v) for v in fields[1:]]
                    if not 0 <= class_id < len(classes):
                        raise ValueError('Class id out of range')
                    if not all(math.isfinite(v) and 0 <= v <= 1 for v in coords):
                        raise ValueError('Coordinates are not finite normalized values')
                    if len(coords) == 4:
                        if coords[2] <= 0 or coords[3] <= 0:
                            raise ValueError('Nonpositive box width or height')
                        formats['bbox'] += 1
                    elif len(coords) >= 6 and len(coords) % 2 == 0:
                        formats['polygon'] += 1
                    else:
                        raise ValueError('Unexpected coordinate count')
                    object_counts[class_id] += 1
                except Exception as exc:
                    invalid_labels.append({'file':str(label.relative_to(dataset_root)),'line':number,'error':str(exc)})
        hashes = collections.defaultdict(list)
        for image in images:
            hashes[image_hashes[image]].append(image.name)
        splits[split] = {'images':len(images),'labels':len(labels),'missing_labels':sorted(image_stems-label_stems),'orphan_labels':sorted(label_stems-image_stems),'empty_labels':empty,'objects_by_class_id':dict(sorted(object_counts.items())),'annotation_formats':dict(formats),'unique_image_bytes':len(hashes),'duplicate_image_groups':[v for v in hashes.values() if len(v)>1]}

    train_hashes = {image_hashes[p] for p in image_files if p.parent == dataset_root/'images'/'train'}
    val_hashes = {image_hashes[p] for p in image_files if p.parent == dataset_root/'images'/'val'}
    overlap = train_hashes & val_hashes
    archive_after = digest_file(archive_path)
    if archive_before != archive_after:
        raise ValueError('Archive changed during extraction')
    result = {
        'archive':str(archive_path),'archive_bytes':archive_path.stat().st_size,'archive_sha256':archive_before,
        'original_archive_unchanged':True,'zip_crc':'PASS','extracted_files':len(verified),
        'extracted_uncompressed_bytes':sum(v['bytes'] for v in verified),
        'all_extracted_sha256_match_zip_entries':True,'dataset_root':str(dataset_root),
        'dataset_yaml_original':config,'classes':classes,'images_total_including_field_and_backups':len(image_files),
        'unique_image_bytes_all_folders':len(set(image_hashes.values())),
        'image_directories':dict(sorted(grouped.items())), 'unreadable_images':bad_images,
        'splits':splits,'invalid_main_split_annotations':invalid_labels,
        'train_val_exact_byte_overlap_count':len(overlap),
        'train_val_exact_byte_overlap_examples':[[str(p.relative_to(dataset_root)).replace(os.sep,'/') for p in image_files if image_hashes[p] == h and p.parent.name in {'train','val'}] for h in sorted(overlap)[:20]],
        'preparation_report_top_level_keys':list(preparation),
        'preparation_report_summary':{k:v for k,v in preparation.items() if not isinstance(v,list) or len(v)<15},
        'structural_checks_pass':not bad_images and not invalid_labels and all(not s['missing_labels'] and not s['orphan_labels'] for s in splits.values()),
        'cloud_folder_completeness':'This verifies the supplied archive contents; the full cloud folder listing was not compared.'
    }
    return result, verified


if __name__ == '__main__':
    try:
        archive = Path(sys.argv[1]).resolve()
        destination = Path(sys.argv[2]).resolve()
        report_path = Path(sys.argv[3]).resolve()
        result, manifest = audit(archive,destination)
        report_path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8-sig')
        report_path.with_name('dataset-file-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8-sig')
        summary = {k:result[k] for k in ['archive','archive_sha256','original_archive_unchanged','zip_crc','extracted_files','all_extracted_sha256_match_zip_entries','dataset_root','images_total_including_field_and_backups','image_directories','train_val_exact_byte_overlap_count','structural_checks_pass']}
        summary['splits'] = {k:{'images':v['images'],'labels':v['labels'],'empty_labels':len(v['empty_labels']),'missing_labels':len(v['missing_labels']),'orphan_labels':len(v['orphan_labels'])} for k,v in result['splits'].items()}
        print(json.dumps(summary,ensure_ascii=False,indent=2))
    except Exception as exc:
        print(json.dumps({'error':str(exc)},ensure_ascii=False),file=sys.stderr)
        raise
