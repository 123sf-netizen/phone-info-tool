import subprocess, unittest
from pathlib import Path
class ResearchSaveTest(unittest.TestCase):
 def test_save_refresh_and_preserve_concurrent_edits(self):
  html=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8')
  code=html[html.index('// RESEARCH_SAVE_BEGIN'):html.index('// RESEARCH_SAVE_END')]
  js=r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:'',disabled:false});let token={value:'test'},context='/api/admin/research/phones/1/ip',refreshes=0;
function researchContext(){return context} async function refreshGapList(){refreshes++;return true}
let onSend=()=>{},fail=false;async function fetch(){onSend();if(fail)throw new TypeError('offline');return {ok:true}}
CODE
(async()=>{
 const fill=()=>{byId('researchStatus').value='查找中';byId('researchRegion').value='中国大陆';byId('researchScope').value='官网';byId('researchUrl').value='https://x';byId('researchDate').value='2026-11-20'};
 fill();await byId('saveResearch').onclick();if(byId('researchRegion').value||refreshes!==1)throw Error('clear or refresh');
 fill();onSend=()=>{byId('researchScope').value='新的输入'};await byId('saveResearch').onclick();if(byId('researchScope').value!=='新的输入'||refreshes!==2)throw Error('lost edit');
 fill();onSend=()=>{context='/api/admin/research/phones/2/ip'};await byId('saveResearch').onclick();if(!byId('researchRegion').value)throw Error('lost switched form');
 fill();onSend=()=>{};fail=true;await byId('saveResearch').onclick();if(!byId('researchMessage').textContent.includes('结果未知')||!byId('researchRegion').value)throw Error('uncertain save');
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
