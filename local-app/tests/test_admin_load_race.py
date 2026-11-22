import subprocess
import unittest
from pathlib import Path


class AdminLoadRaceTests(unittest.TestCase):
    def test_clearing_token_rejects_inflight_load(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8')
        start = html.index('let adminLoadSequence=0;')
        end = html.index('let editingPhone=', start)
        js = r"""
const vm=require('node:vm');
const controls={};function element(id){return controls[id]||(controls[id]={value:'',textContent:'',replaceChildren(){}})}
const token={value:'secret'},status={textContent:''},pending=[],saved=[];
const document={getElementById:element},sessionStorage={setItem:(...args)=>saved.push(args),removeItem(){}};
let gapLoaded=true,gapRefreshSequence=0,feedbackSequence=0,feedbackRows=[],feedbackHasMore=false,gapRows=[],releaseGapRows=[],priceGapRows=[];
function renderGaps(){throw Error('stale gap data displayed')}function setFeedbackFirstPage(){throw Error('stale feedback displayed')}
function fetch(){return new Promise(resolve=>pending.push(resolve))}
CODE
(async()=>{const running=element('load').onclick();element('clear').onclick();
const fake={ok:true,json:async()=>({'机型数':1,'状态统计':{},'说明':'x','未完成机型':[]})};pending.forEach(resolve=>resolve(fake));await running;
if(saved.length||token.value!=='')throw Error('cleared token restored');})();
""".replace('CODE', html[start:end])
        result = subprocess.run(['node'], input=js.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
