import json,subprocess,sys,unittest
from pathlib import Path
from datetime import date,datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from gaps import classify,china_today,valid_evidence
from editing import update_field
class EvidenceConsistencyTest(unittest.TestCase):
 def test_china_midnight_and_checked_date(self):
  self.assertEqual(china_today(datetime(2026,11,20,15,59,tzinfo=timezone.utc)),date(2026,11,20))
  self.assertEqual(china_today(datetime(2026,11,20,16,0,tzinfo=timezone.utc)),date(2026,11,21))
  evidence={'status':'厂商官方核实','url':'https://example.com','region':'中国大陆','checkedAt':'2026-11-21'}
  self.assertTrue(valid_evidence(evidence,date(2026,11,21)))
  self.assertFalse(valid_evidence({**evidence,'checkedAt':'2026-11-22'},date(2026,11,21)))
  with patch('editing.china_today',return_value=date(2026,11,21)):
   result=update_field({'ip':None},'ip','IP68',None,None,evidence);self.assertEqual(result['ip'],'IP68')
   with self.assertRaises(ValueError):update_field({'ip':None},'ip','IP68',None,None,{**evidence,'checkedAt':'2026-11-22'})
   with self.assertRaises(ValueError):update_field({'ip':None},'ip','IP68',None,None,{**evidence,'url':'https://user@example.com'})
 def test_python_and_js_classify_same_evidence(self):
  good={'status':'厂商官方核实','url':'https://example.com/spec','region':'中国大陆','checkedAt':'2024-01-01'}
  cases=[('IP68',good),('IP68',None),('待补充',good),('IP68',{**good,'status':'资料冲突'}),('IP68',{**good,'url':'javascript:alert(1)'}),('IP68',{**good,'url':'https://user@example.com'}),('IP68',{**good,'url':'https://example.com:99999/'}),('IP68',{**good,'url':'https://exa mple.com/'}),('IP68',{**good,'url':'https://example.com/invalid path'}),('IP68',{**good,'url':'https://%65xample.com/spec'}),('IP68',{**good,'region':'  '}),('IP68',{**good,'checkedAt':'2024-02-30'}),('IP68',{**good,'checkedAt':'2999-01-01'}),('IP68（待确认）',good)]
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');code=h[h.index('// FIELD_EVIDENCE_BEGIN'):h.index('// FIELD_EVIDENCE_END')]
  js=code+'\nconst cases='+json.dumps(cases,ensure_ascii=False)+';process.stdout.write(JSON.stringify(cases.map(([v,e])=>fieldEvidenceStatus(v,e))));'
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
  self.assertEqual(json.loads(r.stdout.decode()),[classify(value,evidence) for value,evidence in cases])
 def test_release_and_price_reject_untrustworthy_metadata(self):
  from release_gaps import release_state
  from price_gaps import price_state
  source={'status':'厂商官方核实','region':'中国大陆','url':'https://example.com','checkedAt':'2024-01-01'}
  self.assertEqual(release_state({'releaseDate':'2020-01-01','releaseSource':source}),'厂商官方核实')
  self.assertEqual(release_state({'releaseDate':'2999-01-01','releaseSource':source}),'日期不完整或待核实')
  self.assertEqual(release_state({'releaseDate':'2020-01','releaseSource':source}),'日期不完整或待核实')
  self.assertEqual(release_state({'releaseDate':'2020-01-01','releaseDateLabel':'开售日期','releaseSource':source}),'其他日期，发布日期待核实')
  self.assertEqual(release_state({'releaseDate':'2020-01-01','releaseSource':{**source,'url':'https://user@example.com'}}),'来源或核实状态待核实')
  price={**source,'amount':'1000','currency':'CNY','variant':'8GB','type':'历史发布价格'}
  self.assertEqual(price_state(price),'厂商官方核实')
  self.assertEqual(price_state({**price,'url':'https://example.com:99999/'}),'记录或来源待核实')

 def test_frontend_date_uses_beijing_midnight(self):
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');code=h[h.index('// FIELD_EVIDENCE_BEGIN'):h.index('// FIELD_EVIDENCE_END')]
  js=code+"\nDate.now=()=>Date.parse('2026-11-20T16:00:00Z');if(!validFieldDate('2026-11-21')||validFieldDate('2026-11-22'))process.exit(1);"
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
