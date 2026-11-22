import subprocess,unittest
from pathlib import Path
class MarketDisplayTest(unittest.TestCase):
 def test_fresh_and_expired_quotes_and_escaping(self):
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');code=h[h.index('function escapeMarkup('):h.index('function filter()',h.index('function escapeMarkup('))]
  js=r'''
const document={querySelector:()=>null},window={scrollTo:()=>{}};let detailActive=true,detailOrigin={},page='home',activeBrand=null,phoneImages={},content={innerHTML:''};const closeBrand=()=>{},batteryTypical=x=>x;
let phones=[{id:1,name:'A',status:'在售',salesStatusSource:{region:'中国',channel:'官网'},battery:'1',charge:'1',marketQuote:{amount:'123.00',currency:'CNY',variant:'<test>',region:'中国',channel:'官网',url:'https://example.com',observedAt:new Date().toISOString()}}];
CODE
if(!usableMarketQuote(phones[0]))throw Error('fresh');detail(1);if(!content.innerHTML.includes('¥123.00')||content.innerHTML.includes('<test>')||!content.innerHTML.includes('&lt;test&gt;')||!content.innerHTML.includes('非实时'))throw Error('display');
phones[0].status='停售';detail(1);if(content.innerHTML.includes('¥123.00'))throw Error('discontinued');phones[0].status='在售';phones[0].marketQuote.observedAt=new Date(Date.now()-86400000).toISOString();detail(1);if(content.innerHTML.includes('¥123.00'))throw Error('expired');
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True,timeout=10);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
