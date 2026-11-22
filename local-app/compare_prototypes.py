"""比较现有和旧版原型，仅输出差异，不修改任何原型或数据库。"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend'))
from seed import compare, load_seed


def main():
    current = load_seed(ROOT.parent / 'index.html')
    legacy = load_seed(ROOT.parent / '旧版查询工具.html')
    report = compare(legacy, current)
    report['说明'] = 'seed_only 为旧版独有机型；旧版可能缺少后续核实资料，不能直接视为最新数据。'
    target = ROOT / 'storage' / '原型机型差异.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(target)
    print(f"旧版 {report['seed_count']} 款，当前 {report['database_count']} 款；旧版独有 {len(report['seed_only'])} 款，当前独有 {len(report['database_only'])} 款。")
    print(f'报告：{target}')


if __name__ == '__main__':
    main()
