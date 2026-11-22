import subprocess,unittest
from pathlib import Path
class SourceStopTest(unittest.TestCase):
 def test_stop_keeps_completed_results(self):
  html=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8')
  code=html[html.index('// BATCH_SOURCE_BEGIN'):html.index("byId('exportGaps').onclick")]
  js=r'''
let e={};const byId=id=>e[id]||(e[id]={value:'',textContent:'',disabled:false,children:[],options:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)},addEventListener(){}});
const document={createElement:()=>({append(){}})};const token={value:'secret'},gapLoaded=true,gapRows=[{id:1,name:'A',fields:[{field:'电池'},{field:'屏幕'}]}];
function filterGaps(rows){return rows}function gapCsvCell(x){return JSON.stringify(String(x??''))}
let requestNo=0,release;async function fetch(){requestNo++;if(requestNo===2)await new Promise(r=>release=r);return {ok:true,json:async()=>({url:'https://www.mi.com',checked_at:'2026-11-20',snippets:['线索']})}}
byId('gapSourceStart').value='1';byId('field').options=[{textContent:'电池',value:'battery'},{textContent:'屏幕',value:'screen'}];
CODE
(async()=>{const pending=byId('checkGapSources').onclick();while(requestNo<2)await new Promise(r=>setTimeout(r,0));byId('stopGapSources').onclick();release();await pending;if(gapSourceLatest.length!==1||byId('gapSourceActions').children.length!==1)throw Error('completed result lost');if(requestNo!==2)throw Error('unexpected request');})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
