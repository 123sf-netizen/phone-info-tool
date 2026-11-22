import subprocess,unittest
from pathlib import Path
class SourceExportTest(unittest.TestCase):
 def test_csv_escapes_and_preserves_failures(self):
  html=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8')
  cell=html[html.index('function gapCsvCell('):html.index('function gapCsv(')]
  block=html[html.index('function gapSourceCsv('):html.index('// BATCH_SOURCE_END')]
  js=cell+block+r'''
let text=gapSourceCsv([{id:1,name:'=cmd',label:'屏幕',url:'https://x',time:'2026',snippets:['a,"b"\nsecond']},{id:2,name:'B',label:'电池',error:'网络异常'}]);
if(!text.startsWith('\ufeff')||!text.includes("'=cmd")||!text.includes('""b""')||!text.includes('网络异常')||!text.includes('未取得线索'))throw Error('CSV content or escaping');
'''
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
