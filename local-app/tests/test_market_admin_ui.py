import subprocess,unittest
from pathlib import Path
class MarketAdminTest(unittest.TestCase):
 def test_save_keeps_later_edits_and_sends_expected_value(self):
  h=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8');code=h[h.index('let marketEditSlot=null;'):h.index("byId('addHistoricalPrice').onclick")]
  js=r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:'',disabled:false});let marketGapLoaded=false,token={value:'secret'},editingTarget='phones',editingPhone={id:7},sent=null,resolveRequest;
byId('phoneId').value='7';function fetch(url,opts){sent={url,body:JSON.parse(opts.body)};return new Promise(r=>resolveRequest=r)}
CODE
(async()=>{
 byId('marketAmount').value='1234';byId('marketCurrency').value='CNY';byId('marketVariant').value='8GB';byId('marketRegion').value='中国大陆';byId('marketChannel').value='官网';byId('marketUrl').value='https://example.com';byId('marketObserved').value='2026-11-20T10:00';
 let pending=byId('saveMarketQuote').onclick();if(sent.body.expected_quote!==null||sent.body.expected_quotes!==null||sent.body.slot!==null||sent.body.variant!=='8GB'||!sent.body.observed_at.endsWith('Z'))throw Error('request');
 byId('marketVariant').value='后续输入';resolveRequest({ok:true,json:async()=>({legacy:null,quotes:[{amount:'1234',variant:'8GB'}]})});await pending;
 if(byId('marketVariant').value!=='后续输入'||!byId('marketMessage').textContent.includes('保留'))throw Error('lost later edit');
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
 def test_select_existing_quote_and_preserve_legacy_slot(self):
  h=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8');code=h[h.index('let marketEditSlot=null;'):h.index("byId('addHistoricalPrice').onclick")]
  js=r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:'',disabled:false,children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)}});const document={createElement(){return {children:[],append(...v){this.children.push(...v)}}}};let token={value:'secret'},marketGapLoaded=false,editingTarget='phones',editingPhone={id:7,marketQuote:{variant:'8GB',currency:'CNY',amount:'100',region:'中国',channel:'官网',url:'https://example.com',observedAt:'2026-11-20T02:00:00Z'},marketQuotes:[{variant:'12GB',currency:'CNY',amount:'200',region:'中国',channel:'官网',url:'https://example.com',observedAt:'2026-11-20T03:00:00Z'}]};
CODE
showMarketQuote();if(byId('marketRecords').children.length!==2)throw Error('records');byId('marketRecords').children[1].children[0].onclick();if(marketEditSlot!=='0'||byId('marketVariant').value!=='12GB'||!byId('marketObserved').value)throw Error('edit selection');byId('cancelMarketEdit').onclick();if(marketEditSlot!==null||byId('marketVariant').value!=='')throw Error('reset');
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
