"""备份本地图片并校验归档；不联网、不修改原图。"""
import hashlib
import json
import os
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / 'images'
DEST = ROOT / 'storage' / 'backups'
MANIFEST = 'manifest.json'


def make_backup(source: Path, target: Path):
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError('图片目录不存在')
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.images-', suffix='.tmp', dir=target.parent)
    os.close(fd)
    try:
        entries = []
        with zipfile.ZipFile(temp, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in sorted(source.rglob('*')):
                if path.is_symlink():
                    raise ValueError(f'图片目录包含符号链接：{path.relative_to(source)}')
                if not path.is_file():
                    continue
                relative = path.relative_to(source).as_posix()
                digest = hashlib.sha256()
                size = 0
                with path.open('rb') as stream, archive.open('images/' + relative, 'w') as output:
                    while chunk := stream.read(1024 * 1024):
                        digest.update(chunk)
                        size += len(chunk)
                        output.write(chunk)
                entries.append({'path': relative, 'bytes': size, 'sha256': digest.hexdigest()})
            archive.writestr(MANIFEST, json.dumps({'version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                                                    'files': entries}, ensure_ascii=False, indent=2))
        if not entries:
            raise ValueError('图片目录为空，未生成备份')
        verify_backup(Path(temp))
        os.replace(temp, target)
        return len(entries)
    finally:
        Path(temp).unlink(missing_ok=True)


def verify_backup(path: Path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or names.count(MANIFEST) != 1:
            raise ValueError('备份包含重复条目或缺少清单')
        manifest = json.loads(archive.read(MANIFEST))
        if manifest.get('version') != 1 or not isinstance(manifest.get('files'), list) or not manifest['files']:
            raise ValueError('备份清单无效')
        expected = {MANIFEST}
        for item in manifest['files']:
            relative = item['path']
            parts = relative.split('/')
            if not relative or any(part in ('', '.', '..') for part in parts) or '\\' in relative:
                raise ValueError('备份中包含无效路径')
            name = 'images/' + relative
            if name in expected:
                raise ValueError('备份清单包含重复路径')
            expected.add(name)
            digest = hashlib.sha256()
            size = 0
            with archive.open(name) as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
                    size += len(chunk)
            if size != item['bytes'] or digest.hexdigest() != item['sha256']:
                raise ValueError(f'文件校验失败：{relative}')
        if set(names) != expected:
            raise ValueError('备份内容与清单不一致')
        return len(manifest['files'])


def compare_with_source(path: Path, source: Path):
    """先验证归档，再只读比较本地目录；不证明图片的型号和内容正确。"""
    verify_backup(path)
    source = source.resolve(strict=True)
    if not source.is_dir():
        raise ValueError('图片目录不存在')
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read(MANIFEST))
    backed_up = {item['path']: item['sha256'] for item in manifest['files']}
    current = {}
    for file in sorted(source.rglob('*')):
        if file.is_symlink():
            raise ValueError(f'图片目录包含符号链接：{file.relative_to(source)}')
        if not file.is_file():
            continue
        digest = hashlib.sha256()
        with file.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
        current[file.relative_to(source).as_posix()] = digest.hexdigest()
    return {
        '新增': sorted(current.keys() - backed_up.keys()),
        '当前缺少': sorted(backed_up.keys() - current.keys()),
        '内容变化': sorted(name for name in current.keys() & backed_up.keys() if current[name] != backed_up[name]),
    }


def main():
    try:
        if len(sys.argv) == 2 and sys.argv[1] == '--verify':
            backups = sorted(DEST.glob('phoneguide-images-*.zip'), key=lambda p: p.stat().st_mtime)
            if not backups:
                raise ValueError('没有找到图片备份')
            backup = backups[-1]
            print(f'图片备份完整性检查通过：{backup.name}，共 {verify_backup(backup)} 个文件。')
            try:
                differences = compare_with_source(backup, SOURCE)
                for label, names in differences.items():
                    print(f'{label}：{len(names)} 个' + ('；' + '、'.join(names[:10]) if names else ''))
                    if len(names) > 10:
                        print(f'  仅显示前 10 个，共 {len(names)} 个。')
                print('比较基于文件内容摘要；远程图片、型号配色和画面真实性未检查。')
            except (OSError, ValueError) as exc:
                print(f'当前图片目录比较未完成：{exc}')
        elif len(sys.argv) == 1:
            target = DEST / f'phoneguide-images-{datetime.now():%Y%m%d-%H%M%S-%f}.zip'
            print(f'图片备份已保存：{target}，共 {make_backup(SOURCE, target)} 个文件。')
            print('该备份只包含本地 images 目录，不包含远程图片和数据库；请另行备份数据库并复制到其他磁盘。')
        else:
            raise ValueError('用法：image_backup.py [--verify]')
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        print(f'图片备份操作失败：{exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
