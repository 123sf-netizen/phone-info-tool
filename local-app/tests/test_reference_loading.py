import subprocess,unittest
from pathlib import Path
class ReferenceLoadingTest(unittest.TestCase):
 def test_failed_references_not_misreported_as_compared(self):
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');code=h[h.index('// BACK_CANDIDATES_BEGIN'):h.index('// BACK_CANDIDATES_END')]
  js=r'''
const location={protocol:'http:'};let closed=0,requests=0;const refs=[{image:'ok',phoneId:1},{image:'second',phoneId:1},{image:'missing',phoneId:2},{image:'bad',phoneId:3}];
async function fetch(url){requests++;if(url==='/api/recognition/references')return {ok:true,json:async()=>refs};if(url==='/missing')return {ok:false};return {ok:true,blob:async()=>url}}
async function createImageBitmap(blob){if(blob==='/bad')throw Error('bad');return {id:blob,close(){closed++}}}
function backImageFeatures(b){return {variance:b.blank?0:1000,gray:[]}}function backTrimUniformBorder(){return null}function backReferenceFeatures(b){return backImageFeatures(b)}function backImageDistance(){return 1}
CODE
(async()=>{let result=await findBackCandidates({});if(result.count!==2||result.total!==4||result.failed!==2||result.results.length!==1||closed!==2)throw Error('partial failures or duplicate models');requests=0;result=await findBackCandidates({blank:true});if(!result.invalidSample||result.count!==0||requests!==1)throw Error('blank sample');})().catch(e=>{console.error(e);process.exit(1)});
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
