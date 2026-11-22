"""只读盘点原型的主图引用；不把文件存在当作画面验收。"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit


def load_image_map(path):
    text = Path(path).read_text(encoding='utf-8')
    match = re.search(r'const phoneImages=(\{.*?\});', text, re.S)
    if not match:
        raise ValueError('无法读取原型的主图索引')
    data = json.loads(match.group(1))
    if not isinstance(data, dict):
        raise ValueError('主图索引格式无效')
    return data


def audit_images(phones, image_map, root):
    root = Path(root).resolve()
    rows, hashes = [], {}
    for phone in phones:
        address = image_map.get(str(phone['id']), '')
        item = {'id': phone['id'], 'name': phone['name'], 'address': address,
                'visual_status': '未验收', 'status': '缺少地址'}
        if isinstance(address, str) and address:
            parsed = urlsplit(address)
            if parsed.scheme in ('http', 'https') and parsed.netloc:
                item['status'] = '外链未检查加载'
            elif not parsed.scheme and not parsed.netloc and address.startswith('images/'):
                path = (root / address[len('images/'):]).resolve()
                if not path.is_relative_to(root):
                    item['status'] = '路径无效'
                elif path.is_file():
                    try:
                        with path.open('rb') as stream:
                            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                        item['status'] = '本地文件存在'
                        item['sha256'] = digest
                        hashes.setdefault(digest, []).append(phone['id'])
                    except OSError:
                        item['status'] = '本地文件不可读取'
                else:
                    item['status'] = '本地文件缺失'
            else:
                item['status'] = '路径无效'
        rows.append(item)
    duplicates = [ids for ids in hashes.values() if len(ids) > 1]
    return {'机型数': len(phones), '状态统计': dict(Counter(row['status'] for row in rows)),
            '重复文件候选': duplicates, '机型': rows,
            '说明': '仅检查原型主图地址与本地文件；外链加载、画面、型号、配色及其他图片均未验收。重复文件仅为候选，需人工判断。'}
