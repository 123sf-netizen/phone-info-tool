import subprocess
import unittest
from pathlib import Path


class GapExportTests(unittest.TestCase):
    def test_filtered_csv_escapes_formulas_quotes_and_research(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8')
        start = html.index('function filterGaps(')
        end = html.index('// GAP_CSV_END', start)
        js = html[start:end] + r"""
const rows=[{id:7,name:'=evil',fields:[{field:'屏幕',status:'缺失',value:'原值',evidence:{status:'待核实',url:'https://example.org/spec',region:'中国大陆',checkedAt:'2026-01-02'},research:{status:'查找中',region:'中国大陆',scope:'查看, "官网"',source_url:'https://example.com',checked_at:'2026-11-20'}},{field:'电池容量',status:'待核实',research:null}]}];
const selected=filterGaps(rows,'','缺失','','');
const out=gapCsv(selected);
if(!out.startsWith('\ufeff') || !out.includes(String.fromCharCode(34,39)+'=evil'+String.fromCharCode(34)) || !out.includes('https://example.com') || !out.includes('https://example.org/spec') || !out.includes('原值') || out.includes('电池容量') || !out.endsWith('\r\n'))process.exit(1);
if(gapCsvCell('  +1')!=="\"'  +1\"")process.exit(2);
"""
        result = subprocess.run(['node'], input=js.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
