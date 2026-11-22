"""将最新备份恢复到隔离的临时 MySQL；绝不连接或修改现有数据库。"""
import secrets
import subprocess
import sys
import time
from pathlib import Path
from backup_schema import REQUIRED_TABLES, missing_tables, parse_table_counts, parse_table_checksums
from backup_checksum import verify_checksum

ROOT = Path(__file__).resolve().parent
backups = sorted((ROOT / 'storage' / 'backups').glob('phoneguide-*.sql'), key=lambda p: p.stat().st_mtime)
if not backups:
    sys.exit('没有找到数据库备份，请先运行备份数据库。')
backup = backups[-1]
try:
    checksum_status = verify_checksum(backup)
except (OSError, UnicodeError) as exc:
    sys.exit('摘要文件读取失败：' + str(exc))
if checksum_status in ('invalid', 'mismatch'):
    sys.exit('备份摘要无效或不匹配，已停止恢复测试。')
if checksum_status == 'missing':
    print('该备份没有摘要文件，无法校验文件是否发生变化。')
else:
    print('备份 SHA-256 摘要校验通过。')
name = 'phoneguide-restore-check-' + secrets.token_hex(8)
password = secrets.token_hex(24)
started = False
try:
    run = subprocess.run(['docker', 'run', '--rm', '-d', '--name', name, '--network', 'none',
                          '-e', 'MYSQL_ROOT_PASSWORD=' + password, '-e', 'MYSQL_DATABASE=phoneguide',
                          'mysql:8.4'], capture_output=True, text=True, timeout=60)
    if run.returncode:
        raise RuntimeError('隔离容器无法启动：' + run.stderr.strip())
    started = True
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        result = subprocess.run(['docker', 'exec', name, 'sh', '-c',
                                 'mysql -h 127.0.0.1 -uroot -p"$MYSQL_ROOT_PASSWORD" phoneguide -N -e "SELECT 1"'],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            break
        time.sleep(2)
    else:
        raise RuntimeError('隔离 MySQL 启动超时')
    with backup.open('rb') as source:
        result = subprocess.run(['docker', 'exec', '-i', name, 'sh', '-c',
                                 'exec mysql -uroot -p"$MYSQL_ROOT_PASSWORD" phoneguide'],
                                stdin=source, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError('恢复备份失败：' + result.stderr.decode('utf-8', errors='replace')[-1000:])
    result = subprocess.run(['docker', 'exec', name, 'sh', '-c',
                             'exec mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" phoneguide -e "SHOW TABLES"'],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('无法检查备份中的数据表')
    missing = missing_tables(result.stdout)
    if missing:
        raise RuntimeError('备份缺少当前应用所需的数据表：' + '、'.join(missing))
    query = ' UNION ALL '.join("SELECT '" + table + "', COUNT(*) FROM `" + table + "`" for table in sorted(REQUIRED_TABLES))
    result = subprocess.run(['docker', 'exec', name, 'sh', '-c',
                             'exec mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" phoneguide -e "$1"', 'sh', query],
                            capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('恢复后的数据表数量检查失败')
    try:
        counts = parse_table_counts(result.stdout)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    print(f'备份恢复检查通过：{backup.name}，恢复机型 {counts["phones"]} 款。')
    print('各表记录数量：' + '，'.join(f'{table}={counts[table]}' for table in sorted(counts)))
    # Counts detect additions and deletions, not edits; the live database may change during this check.
    live = subprocess.run(['docker', 'compose', '-p', 'chaxun', 'exec', '-T', 'mysql', 'sh', '-c',
                           'exec mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" phoneguide -e "$1"', 'sh', query],
                          cwd=ROOT, capture_output=True, text=True, timeout=30)
    if live.returncode:
        print('当前数据库无法读取，未能比较记录数量。')
    else:
        try:
            current = parse_table_counts(live.stdout)
            differences = [f'{table}：备份 {counts[table]}，当前 {current[table]}'
                           for table in sorted(counts) if counts[table] != current[table]]
            print('与当前数据库记录数量不同：' + '；'.join(differences) if differences
                  else '各表记录数量与当前数据库一致。')
        except ValueError:
            print('当前数据库数量结果不完整，未能比较。')
    print('数量一致不代表内容一致；比较期间数据库可能发生变化。')
    checksum_query = 'CHECKSUM TABLE ' + ', '.join('`' + table + '`' for table in sorted(REQUIRED_TABLES))
    isolated = subprocess.run(['docker', 'exec', name, 'sh', '-c',
                               'exec mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" phoneguide -e "$1"', 'sh', checksum_query],
                              capture_output=True, text=True, timeout=60)
    current_result = subprocess.run(['docker', 'compose', '-p', 'chaxun', 'exec', '-T', 'mysql', 'sh', '-c',
                                     'exec mysql -N -uroot -p"$MYSQL_ROOT_PASSWORD" phoneguide -e "$1"', 'sh', checksum_query],
                                    cwd=ROOT, capture_output=True, text=True, timeout=60)
    if isolated.returncode or current_result.returncode:
        print('表内容校验未完成，请确认当前数据库可访问。')
    else:
        try:
            restored_checksums = parse_table_checksums(isolated.stdout)
            current_checksums = parse_table_checksums(current_result.stdout)
            changed = [table for table in sorted(REQUIRED_TABLES) if restored_checksums[table] != current_checksums[table]]
            print('表内容校验不同：' + '、'.join(changed) if changed else '各表内容校验值与当前数据库一致。')
        except ValueError:
            print('表内容校验未完成：结果不完整或存储引擎不支持。')
    print('表校验值并非逐条比较或加密证明；检查期间数据变化可能造成差异。未核对图片或资料真实性。')
except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
    print(f'检查失败：{exc}', file=sys.stderr)
    sys.exit(1)
finally:
    if started:
        stopped = subprocess.run(['docker', 'stop', '--time', '2', name], capture_output=True, text=True)
        if stopped.returncode:
            print(f'临时容器未能自动停止：{name}；请检查 Docker Desktop。', file=sys.stderr)
