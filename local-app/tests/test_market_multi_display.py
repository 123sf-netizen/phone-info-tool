import subprocess,unittest
from pathlib import Path
class MarketMultiDisplayTest(unittest.TestCase):
 def test_variants_collapsed_expired_and_discontinued_hidden(self):
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');code=h[h.index('function escapeMarkup('):h.index('function filter()',h.index('function escapeMarkup('))]
  js=r'''
const document={querySelector:()=>null},window={scrollTo:()=>{}};let detailActive=true,detailOrigin={},page='home',activeBrand=null,phoneImages={},content={innerHTML:''};const closeBrand=()=>{},batteryTypical=x=>x;
const q=(v,t)=>({amount:'100',currency:'CNY',variant:v,region:'中国',channel:'官网',url:'https://example.com',observedAt:new Date(Date.now()-t).toISOString()});
let phones=[{id:1,name:'A',status:'在售',salesStatusSource:{region:'中国',channel:'官网'},battery:'1',charge:'1',marketQuotes:[q('8GB',0),q('12GB',0),q('过期',86400001)]}];
CODE
detail(1);if(!content.innerHTML.includes('8GB')||!content.innerHTML.includes('12GB')||content.innerHTML.includes('过期')||!content.innerHTML.includes('<details class="price-variants">')||!content.innerHTML.includes('非实时'))throw Error('collapsed or expiration');phones[0].status='停售';detail(1);if(content.innerHTML.includes('8GB')||content.innerHTML.includes('12GB'))throw Error('discontinued');
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True,timeout=10);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
