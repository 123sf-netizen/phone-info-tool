import subprocess,unittest
from pathlib import Path
class FieldEvidenceTest(unittest.TestCase):
 def test_status_sources_dates_and_escaping(self):
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');helper=h[h.index('function escapeMarkup('):h.index('function safeSalesUrl(')];code=h[h.index('// FIELD_EVIDENCE_BEGIN'):h.index('// FIELD_EVIDENCE_END')]
  js=r'''
HELPER
CODE
const good={status:'厂商官方核实',url:'https://example.com/spec',region:'中国大陆',checkedAt:'2024-01-01'};
if(fieldEvidenceStatus('5000mAh',good)!=='厂商官方核实')throw Error('verified');
if(fieldEvidenceStatus('5000mAh',null)!=='待核实')throw Error('filled not verified');
if(fieldEvidenceStatus('待补充',good)!=='缺失')throw Error('missing');
if(fieldEvidenceStatus('5000mAh',{...good,status:'资料冲突'})!=='资料冲突')throw Error('conflict');
for(const e of [{...good,url:'javascript:alert(1)'},{...good,region:''},{...good,checkedAt:'2024-02-30'},{...good,checkedAt:'2999-01-01'}])if(fieldEvidenceStatus('5000',e)!=='待核实')throw Error('bad evidence');
const out=renderFieldEvidence({battery:'5000',specFieldSources:{battery:{...good,region:'<img onerror=alert(1)>',conflictingUrl:'javascript:alert(2)'}}},'battery','5000','电池');
if(out.includes('<img')||!out.includes('&lt;img')||out.includes('javascript:')||!out.includes('查看来源'))throw Error('unsafe html');
const battery=renderFieldEvidence({battery:'5000mAh（典型值）；版本待核实',specFieldSources:{battery:good}},'battery','5000mAh（典型值）','电池');if(!battery.includes('记录：待核实'))throw Error('raw battery uncertainty hidden');
const rated=renderFieldEvidence({battery:'额定 5000mAh',specFieldSources:{battery:good}},'battery','典型容量待核实','电池');if(!rated.includes('记录：待核实'))throw Error('typical unknown');
const date=renderFieldEvidence({releaseDate:'2024-01-01',releaseSource:good},'releaseDate','2024-01-01','发布日期');if(!date.includes('厂商官方核实'))throw Error('release source');
const incomplete=renderFieldEvidence({releaseDate:'2024-01',releaseSource:good},'releaseDate','2024-01','发布日期');if(!incomplete.includes('记录：待核实'))throw Error('incomplete date');
const salesDate=renderFieldEvidence({releaseDate:'2024-01-01',releaseSource:good},'releaseDate','2024-01-01','开售日期');if(!salesDate.includes('记录：待核实'))throw Error('sale date misidentified as release');
'''.replace('HELPER',helper).replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
