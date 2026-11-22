import subprocess
import unittest
from pathlib import Path


class ReleaseGapUiTest(unittest.TestCase):
    def test_save_preserves_later_edits_and_refreshes(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8-sig')
        start = html.index("byId('saveRelease').onclick=")
        code = html[start:html.index('\n', start)]
        script = r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:'',disabled:false});
let token={value:'secret'},editingPhone={id:1},editingTarget='phones',releaseGapLoaded=true,refreshes=0,resolveFetch;
function showRelease(){throw Error('不应覆盖后续输入')}
async function refreshReleaseGaps(){refreshes++}
function fetch(){return new Promise(r=>resolveFetch=r)}
CODE
(async()=>{byId('phoneId').value='1';byId('releaseDate').value='2020-01-01';const pending=byId('saveRelease').onclick();byId('releaseDate').value='2021-01-01';resolveFetch({ok:true,json:async()=>({value:'2020-01-01',label:'发布日期',evidence:{}})});await pending;if(refreshes!==1||byId('releaseDate').value!=='2021-01-01'||!byId('releaseMessage').textContent.includes('保留'))throw Error('保存或刷新状态错误')})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE', code)
        result = subprocess.run(['node'], input=script.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_export_filtered_rows_and_escape_formulas(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8-sig')
        cell = html[html.index('function gapCsvCell('):html.index('\n', html.index('function gapCsvCell('))]
        code = html[html.index('let releaseGapRows=[]'):html.index('\n', html.index('let releaseGapRows=[]'))]
        script = cell + '\n' + code + r'''
const rows=[{id:1,name:'=bad',status:'缺失',label:'发布日期',value:'',evidence:{status:'待核实',url:'https://example.com',region:'中国大陆',checkedAt:'2026-11-20'},research:{status:'查找中',scope:'含逗号,引号"',region:'中国大陆',checked_at:'2026-11-21'}},{id:2,name:'other',status:'资料冲突'}];
const out=releaseGapsCsv(filteredReleaseGaps(rows,'bad','缺失'));
if(!out.startsWith('\ufeff')||!out.includes('"\'=bad"')||!out.includes('含逗号,引号""')||!out.includes('https://example.com')||!out.includes('2026-11-20')||out.includes('other')||!out.endsWith('\r\n'))process.exit(1);
'''
        result = subprocess.run(['node'], input=script.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_refresh_ignores_stale_response(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8')
        code = html[html.index('// RELEASE_REFRESH_BEGIN'):html.index('// RELEASE_REFRESH_END')]
        script = r'''
const els={};const byId=id=>els[id]||(els[id]={textContent:'',addEventListener(){}});
let token={value:'secret'},releaseGapSequence=0,releaseGapLoaded=false,releaseGapRows=[{id:1}];
function renderReleaseGaps(){}let resolveFetch;function fetch(){return new Promise(r=>resolveFetch=r)}
CODE
(async()=>{const pending=refreshReleaseGaps();token.value='';resolveFetch({ok:true,json:async()=>({'未完成机型':[],'机型数':0,'状态统计':{},'说明':''})});if(await pending!==false||releaseGapRows.length!==1)throw Error('旧结果覆盖了清单')})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE', code)
        result = subprocess.run(['node'], input=script.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_filters_and_count(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8')
        code = html[html.index('let releaseGapRows=[]'):html.index('\n', html.index('let releaseGapRows=[]'))]
        script = r'''
const els={};const byId=id=>els[id]||(els[id]={value:'',textContent:'',children:[],replaceChildren(){this.children=[]},append(x){this.children.push(x)}});
const document={createElement:()=>({children:[],append(...x){this.children.push(...x)}})};
function gapEvidenceNode(){return {}}
CODE
releaseGapRows=[{id:1,name:'Alpha',status:'缺失'},{id:2,name:'Beta',status:'资料冲突'},{id:3,name:'Alpine',status:'资料冲突'}];
byId('releaseGapKeyword').value='al';byId('releaseGapFilter').value='资料冲突';renderReleaseGaps();
if(byId('releaseGapList').children.length!==1||!byId('releaseGapList').children[0].children[0].textContent.includes('Alpine')||byId('releaseGapCount').textContent!=='符合条件：1 款')throw Error('筛选或计数错误');
'''.replace('CODE', code)
        result = subprocess.run(['node'], input=script.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()

