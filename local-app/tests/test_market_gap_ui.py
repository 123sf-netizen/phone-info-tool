import subprocess,unittest
from pathlib import Path
class MarketGapUiTest(unittest.TestCase):
 def test_filter_and_stale_results(self):
  h=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8');code=h[h.index('// MARKET_GAPS_BEGIN'):h.index('// MARKET_GAPS_END')]
  js=r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:'',children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)},addEventListener(){},scrollIntoView(){}});let token={value:'x'};const document={createElement:()=>({children:[],append(...x){this.children.push(...x)}})};let release;function fetch(){return new Promise(r=>release=r)}
CODE
(async()=>{
 marketGapRows=[{id:1,name:'A',status:'未录入',sales_status:'在售',record_count:0},{id:2,name:'B',status:'可展示',record_states:['可展示','已过期'],sales_status:'在售'}];byId('marketGapFilter').value='已过期';renderMarketGaps();if(byId('marketGapList').children.length!==1||!byId('marketGapList').children[0].children[0].textContent.includes('B'))throw Error('filter');
 const pending=refreshMarketGaps();token.value='';release({ok:true,json:async()=>({'机型':[],'机型数':0,'未录入快照':0,'状态统计':{},'说明':''})});if(await pending!==false||marketGapRows.length!==2)throw Error('stale overwrite');
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
