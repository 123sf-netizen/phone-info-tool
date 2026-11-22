import subprocess
import unittest
from pathlib import Path


class InitialLoadingTests(unittest.TestCase):
    def test_delayed_data_preserves_active_view(self):
        html = (Path(__file__).resolve().parents[2] / 'index.html').read_text(encoding='utf-8')
        start = html.index('let initialViewTouched=false;')
        end = html.index('</script>', start)
        code = r"""
const vm=require('node:vm');
async function scenario(touched){
  let resolveData, rendered=0;const listeners={}, notices=[];
  const ctx={location:{protocol:'http:'},phones:[],phoneImages:{},
    document:{addEventListener:(name,fn)=>listeners[name]=fn,createElement:()=>({setAttribute(){},style:{}}),body:{append:n=>notices.push(n)}},
    fetch:()=>new Promise(resolve=>{resolveData=resolve}),render:()=>rendered++};
  vm.runInNewContext(SOURCE,ctx);
  if(touched)listeners.input();
  resolveData({ok:true,json:async()=>[{id:5,name:'test'}]});
  await new Promise(resolve=>setImmediate(resolve));
  if(ctx.phones.length!==1)throw Error('data not loaded');
  if(touched&&(rendered!==0||notices.length!==1||notices[0].id!=='database-update-notice'))throw Error('active view was not protected');
  if(!touched&&(rendered!==1||notices.length!==0))throw Error('initial view not refreshed');
}
(async()=>{await scenario(true);await scenario(false)})().catch(e=>{console.error(e);process.exit(1)});
""".replace('SOURCE', repr(html[start:end]))
        result = subprocess.run(['node'], input=code.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
