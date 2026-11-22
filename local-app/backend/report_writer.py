import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def write_report(directory, report):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    document = {'生成时间UTC': datetime.now(timezone.utc).isoformat(), '报告': report}
    fd, name = tempfile.mkstemp(prefix='.gaps-', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
        os.replace(name, directory / '最新缺口报告.json')
    finally:
        if os.path.exists(name):
            os.unlink(name)
