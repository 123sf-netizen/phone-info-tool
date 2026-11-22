"""只返回本地文件和已登记机型均匹配的背面参考图。"""
import hashlib
import json
from pathlib import Path, PurePosixPath


def available_references(manifest, image_root, phones):
    data = json.loads(Path(manifest).read_text(encoding='utf-8'))
    if data.get('version') != 1 or not isinstance(data.get('references'), list):
        raise ValueError('参考图清单格式无效')
    return filter_references(data['references'], image_root, phones)


def resolve_image(image_root, address):
    root = Path(image_root).resolve()
    if not isinstance(address, str) or not address.startswith('images/') or any(c in address for c in ('\\', '%', '?', '#')):
        raise ValueError('仅支持 images 目录内的本地图片')
    relative = PurePosixPath(address).parts
    if '..' in relative or len(relative) < 2:
        raise ValueError('图片路径无效')
    path = root.joinpath(*relative[1:]).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError('图片不存在或超出图片目录')
    return path


def inspect_reference_file(image_root, address):
    path = resolve_image(image_root, address)
    with path.open('rb') as file:
        head = file.read(12)
        if not (head.startswith(b'\x89PNG\r\n\x1a\n') or head.startswith(b'\xff\xd8\xff')
                or (head.startswith(b'RIFF') and head[8:12] == b'WEBP')):
            raise ValueError('仅支持 PNG、JPEG 或 WebP 图片')
        file.seek(0)
        return hashlib.file_digest(file, 'sha256').hexdigest()


def filter_references(records, image_root, phones):
    names = {p['id']: p['name'] for p in phones}
    output = []
    for row in records:
        if not isinstance(row, dict) or names.get(row.get('phoneId')) != row.get('phoneName'):
            continue
        address = row.get('image')
        try:
            path = resolve_image(image_root, address)
            with path.open('rb') as file:
                digest = hashlib.file_digest(file, 'sha256').hexdigest()
        except (OSError, ValueError):
            continue
        if digest != row.get('sha256'):
            continue
        if not all(isinstance(row.get(key), str) and row[key] for key in ('region', 'color', 'source', 'checkedAt')):
            continue
        output.append({**{key: row[key] for key in ('phoneId', 'phoneName', 'image', 'region', 'color', 'source', 'checkedAt')},
                       'sourceStatus': row.get('sourceStatus', '待核实')})
    return output
