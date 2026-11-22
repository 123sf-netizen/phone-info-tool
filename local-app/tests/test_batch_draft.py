import subprocess, unittest
from pathlib import Path
class BatchDraftTest(unittest.TestCase):
 def test_draft_is_explicit_and_protects_user_input(self):
  html=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf-8')
  code=html[html.index('function showGapSourceActions('):html.index("byId('clear').addEventListener",html.index('function showGapSourceActions('))]
  js=r'''
const els={}; const byId=id=>els[id]||(els[id]={value:'',textContent:'',children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)},dispatchEvent(){},scrollIntoView(){}});
const document={createElement:tag=>({tag,children:[],append(...x){this.children.push(...x)}}),createTextNode:text=>({tag:'text',textContent:text})};
let gapSourceSequence=1,editingPhone=null,editingTarget=null;
byId('readPhone').onclick=async()=>{editingPhone={id:Number(byId('phoneId').value)};editingTarget='phones'};
CODE
(async()=>{
 let item={id:12,name:'测试',field:'ip',label:'防护',url:'https://www.mi.com/x',time:'2026-11-20T01:00:00Z',snippets:['IP68']};
 showGapSourceActions([item,{error:'no'}],1);let nodes=byId('gapSourceActions').children;if(nodes.length!==1)throw Error('invalid action');let link=nodes[0].children.find(n=>n.tag==='a');if(!link||link.href!=='https://www.mi.com/x'||link.rel!=='noopener noreferrer')throw Error('source link');
 byId('researchRegion').value='已填'; await nodes[0].children[0].onclick(); if(byId('researchRegion').value!=='已填'||editingPhone)throw Error('existing draft overwritten');
 byId('researchRegion').value='';await nodes[0].children[0].onclick();
 if(byId('researchStatus').value!=='查找中'||byId('researchUrl').value!==item.url||!byId('researchScope').value.includes('待人工')||byId('researchRegion').value!=='')throw Error('draft');
 if(byId('researchDate').value!=='2026-11-20')throw Error('date');
 showGapSourceActions([{...item,url:'javascript:alert(1)'}],1);if(byId('gapSourceActions').children[0].children.some(n=>n.tag==='a'))throw Error('unsafe source link');
 for(const id of ['researchRegion','researchScope','researchUrl','researchDate'])byId(id).value='';showGapSourceActions([{...item,failure:'网络不可用'}],1);await byId('gapSourceActions').children[0].children[0].onclick();if(byId('researchStatus').value!=='查找中'||!byId('researchScope').value.includes('未能判断')||byId('researchScope').value.includes('已读取官网'))throw Error('failure misrepresented');
})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  result=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True)
  self.assertEqual(result.returncode,0,result.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
