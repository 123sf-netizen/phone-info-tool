import subprocess, unittest
from pathlib import Path
class EditorRaceTest(unittest.TestCase):
 def test_late_responses_cannot_replace_latest_target(self):
  html=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8')
  code=html[html.index('// EDITOR_LOAD_BEGIN'):html.index('// EDITOR_LOAD_END')]
  js=r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:''});let editorLoadSequence=0,editingPhone=null,editingTarget=null,token={value:'secret'};function showField(){} function showRelease(){} function showSalesStatus(){} function showPrices(){}
let waits=[];function fetch(url){return new Promise(resolve=>waits.push({url,resolve}))}
CODE
(async()=>{
 byId('phoneId').value='1';let old=byId('readDraft').onclick();let fresh=byId('readPhone').onclick();
 waits[1].resolve({ok:true,json:async()=>({id:1,name:'已发布'})});await fresh;
 waits[0].resolve({ok:true,json:async()=>({id:1,name:'旧草稿'})});await old;
 if(editingTarget!=='phones'||editingPhone.name!=='已发布')throw Error('stale draft overwrote phone');
 let pending=byId('readDraft').onclick();byId('phoneId').value='2';editorLoadSequence++;
 waits[2].resolve({ok:true,json:async()=>({id:1,name:'错误机型'})});await pending;if(editingPhone!==null)throw Error('id changed');
 byId('phoneId').value='2';pending=byId('readPhone').onclick();token.value='changed';waits[3].resolve({ok:true,json:async()=>({id:2,name:'旧口令'})});await pending;if(editingPhone!==null)throw Error('token changed');
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
