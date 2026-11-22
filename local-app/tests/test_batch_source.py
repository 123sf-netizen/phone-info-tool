import subprocess
import unittest
from pathlib import Path

class BatchSourceTests(unittest.TestCase):
    def test_batch_limit_offset_failures_and_cancel(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8')
        code = html[html.index('// BATCH_SOURCE_BEGIN'):html.index('// BATCH_SOURCE_END')]
        js = code + r'''
(async()=>{
 const options=[{textContent:'屏幕',value:'screen'},{textContent:'电池',value:'battery'}];
 const rows=[{id:1,name:'A',fields:[{field:'屏幕'},{field:'电池'}]},{id:2,name:'B',fields:[{field:'屏幕'}]}];
 const batch=buildGapSourceBatch(rows,options,2,1);
 if(batch.length!==2||batch[0].field!=='battery'||batch[1].id!==2)throw Error('offset/limit');
 let calls=0,stopped=false;
 const fetcher=async()=>{calls++; return calls===1?{ok:true,json:async()=>({url:'https://www.mi.com/',checked_at:'today',snippets:['线索']})}:{ok:false,json:async()=>({detail:'无来源'})}};
 const result=await checkGapSourceBatch(batch,'secret',fetcher,()=>stopped,()=>{});
 if(result.length!==2||result[0].snippets[0]!=='线索'||result[1].error!=='无来源')throw Error('results');
 if(!formatGapSourceResults(result).includes('未取得线索'))throw Error('error display');
 calls=0; await checkGapSourceBatch(batch,'secret',fetcher,()=>stopped,(done)=>{if(done.length===1)stopped=true});
 if(calls!==1)throw Error('cancel');
})().catch(e=>{console.error(e);process.exit(1)});
'''
        result=subprocess.run(['node'], input=js.encode('utf8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf8', errors='replace'))

if __name__ == '__main__': unittest.main()
