import subprocess,unittest
from pathlib import Path
class OfficialSnippetDraftTest(unittest.TestCase):
 def test_explicit_fill_guards_dirty_conflict_and_session(self):
  h=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8');code=h[h.index('// OFFICIAL_SNIPPETS_BEGIN'):h.index('// OFFICIAL_SNIPPETS_END')]
  js=r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:'',children:[],replaceChildren(){this.children=[]},append(...x){this.children.push(...x)},addEventListener(){},focus(){}});
const document={createElement:tag=>({tag,children:[],append(...x){this.children.push(...x)}})};let editingPhone={id:1,battery:'旧值',specFieldSources:{battery:{status:'厂商官方核实',url:'https://www.mi.com/old',region:'中国大陆',checkedAt:'2026-11-20'}}},editingTarget='phones',token={value:'secret'};
function setBaseline(){byId('phoneId').value='1';byId('field').value='battery';byId('newValue').value='旧值';byId('sourceUrl').value='https://www.mi.com/old';byId('conflictUrl').value='';byId('region').value='中国大陆';byId('checkedAt').value='2026-11-20';byId('evidenceStatus').value='厂商官方核实'}
CODE
setBaseline();renderOfficialSnippets(editingPhone,'battery','https://www.mi.com/new',['电池 5000mAh <b>原文</b>'],'secret');let row=byId('officialSnippets').children[0];if(row.children[1].textContent!==' 电池 5000mAh <b>原文</b>')throw Error('unsafe quote rendering');row.children[0].onclick();
if(byId('newValue').value!=='电池 5000mAh <b>原文</b>'||byId('sourceUrl').value!=='https://www.mi.com/new'||byId('evidenceStatus').value!=='待核实'||byId('region').value||byId('checkedAt').value)throw Error('fill');
setBaseline();byId('newValue').value='未保存修改';row.children[0].onclick();if(byId('newValue').value!=='未保存修改'||!byId('editStatus').textContent.includes('未保存'))throw Error('dirty overwrite');
setBaseline();editingPhone.specFieldSources.battery.status='资料冲突';row.children[0].onclick();if(byId('newValue').value!=='旧值'||!byId('editStatus').textContent.includes('资料冲突'))throw Error('conflict overwrite');
setBaseline();token.value='changed';row.children[0].onclick();if(byId('newValue').value!=='旧值'||!byId('editStatus').textContent.includes('口令'))throw Error('session mismatch');
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
