import subprocess,unittest
from pathlib import Path
class ScheduledActionsTests(unittest.TestCase):
 def test_supported_attempts_offer_drafts_and_clear_blocks_stale(self):
  html=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8')
  code=html[html.index('// SCHEDULED_OFFICIAL_UI_BEGIN'):html.index("byId('loadScheduledReport').onclick")]
  js=r'''
const nodes={};const byId=id=>nodes[id]||(nodes[id]={value:'',textContent:'',children:[],options:[],replaceChildren(){this.children=[]},addEventListener(ev,fn){this.listener=fn}});
let token={value:'secret'},captured=[],check;
function showGapSourceActions(items,sequence,opts){captured=items;check=opts.isValid}
let response={notice:'待确认',records:[{phone_id:1,phone_name:'A',field:'battery',label:'电池',url:'https://www.mi.com',outcome:'发现关键词',page_change:'页面文字有变化',field_change:'字段摘录有变化',next_retry_at:'2026-11-22T00:00:00+00:00',previous_field_at:'2026-11-01',previous_snippets:['旧电池'],snippets:['新电池']},{phone_id:2,phone_name:'B',label:'电池',url:'https://www.mi.com',field:'battery',outcome:'检查失败',error:'网络不可用'},{phone_id:3,field:'unknown',outcome:'发现关键词'}]};
async function fetch(){return {ok:true,json:async()=>response}}
byId('field').options=[{value:'battery'}];
CODE
(async()=>{await byId('loadScheduledOfficial').onclick();if(captured.length!==2||captured[0].id!==1||captured[1].failure!=='网络不可用'||!check()||(!byId('scheduledOfficial').textContent.includes('页面文字有变化')||!byId('scheduledOfficial').textContent.includes('字段摘录有变化')||!byId('scheduledOfficial').textContent.includes('旧电池')||!byId('scheduledOfficial').textContent.includes('新电池')||!byId('scheduledOfficial').textContent.includes('最早重试')))throw Error('selection');byId('clear').listener();if(check())throw Error('cleared session is valid');})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
 def test_page_append_and_filter_change(self):
  html=(Path(__file__).resolve().parents[1]/'admin.html').read_text(encoding='utf8')
  code=html[html.index('// SCHEDULED_OFFICIAL_UI_BEGIN'):html.index('// SCHEDULED_OFFICIAL_UI_END')]
  js=r'''
const nodes={};const byId=id=>nodes[id]||(nodes[id]={value:'',textContent:'',children:[],options:[],hidden:false,replaceChildren(){this.children=[]},addEventListener(ev,fn){this.listener=fn}});
let token={value:'secret'},captured=[];function showGapSourceActions(items){captured=items}
const row=id=>({phone_id:id,phone_name:'手机'+id,field:'ip',label:'防护',url:'https://www.mi.com',attempted_at:'2026-11-20',outcome:'发现关键词',snippets:[]});let urls=[];
async function fetch(url){urls.push(url);let n=urls.length;return {ok:true,json:async()=>({notice:'待确认',records:[row(n)],total:2,next_cursor:n===1?'a'.repeat(64):null})}}
byId('field').options=[{value:'ip'}];
CODE
(async()=>{await byId('loadScheduledOfficial').onclick();if(captured.length!==1||byId('moreScheduledOfficial').hidden)throw Error('first page');await byId('moreScheduledOfficial').onclick();if(captured.length!==2||!urls[1].includes('before=')||!byId('moreScheduledOfficial').hidden)throw Error('append');scheduledOfficialCursor='a'.repeat(64);byId('officialKeyword').value='新筛选';await byId('moreScheduledOfficial').onclick();if(urls.length!==2||!byId('scheduledOfficial').textContent.includes('筛选条件已改变'))throw Error('changed filters');})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
