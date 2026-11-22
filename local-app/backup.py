"""将本机 MySQL 导出为独立备份，不修改正在使用的数据。"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from backup_checksum import digest_file

ROOT = Path(__file__).resolve().parent
DEST = ROOT / 'storage' / 'backups'
DEST.mkdir(parents=True, exist_ok=True)
target = DEST / f"phoneguide-{datetime.now():%Y%m%d-%H%M%S-%f}.sql"
fd, name = tempfile.mkstemp(prefix='.backup-', suffix='.tmp', dir=DEST)
try:
    with os.fdopen(fd, 'wb') as output:
        result = subprocess.run(
            ['docker', 'compose', 'exec', '-T', 'mysql', 'sh', '-c',
             'exec mysqldump --user=root --password="$MYSQL_ROOT_PASSWORD" --single-transaction --quick --default-character-set=utf8mb4 phoneguide'],
            cwd=ROOT, stdout=output, check=False)
    if result.returncode or Path(name).stat().st_size == 0:
        raise RuntimeError('数据库导出失败，请确认 Docker Desktop 和数据库容器正在运行')
    checksum = digest_file(name)
    os.replace(name, target)
    sidecar = target.with_suffix(target.suffix + '.sha256')
    try:
        sidecar.write_text(checksum + '\n', encoding='ascii')
    except OSError:
        print('备份已保存，但摘要文件写入失败；请重新备份。', file=sys.stderr)
        sys.exit(1)
    print(f'备份已保存：{target}')
    print('请同时备份项目根目录 images 和新增图片目录，并将备份复制到其他磁盘。')
except (OSError, RuntimeError) as error:
    Path(name).unlink(missing_ok=True)
    print(f'备份失败：{error}', file=sys.stderr)
    sys.exit(1)
