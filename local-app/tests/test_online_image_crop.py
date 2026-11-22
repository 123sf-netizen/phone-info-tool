import subprocess,unittest
from pathlib import Path
class OnlineImageTest(unittest.TestCase):
 def test_rotation_crop_and_full_image(self):
  html=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8')
  code=html[html.index('// ONLINE_IMAGE_BEGIN'):html.index('// ONLINE_IMAGE_END')]
  js=r'''
const canvases=[];const document={createElement(tag){if(tag!=='canvas')throw Error('bad');const c={width:0,height:0,calls:[],getContext(){return {translate:(...a)=>c.calls.push(['translate',...a]),rotate:(...a)=>c.calls.push(['rotate',...a]),drawImage:(...a)=>c.calls.push(['draw',...a])}},toDataURL(){return 'data:image/jpeg;base64,aGVsbG8='}};canvases.push(c);return c}};
CODE
const bitmap={width:1200,height:800};
if(buildOnlineImage(bitmap,1,{x:40,y:60,w:80,h:120},{width:320,height:480})!=='aGVsbG8=')throw Error('data');
if(canvases[0].width!==800||canvases[0].height!==1200||canvases[1].width!==200||canvases[1].height!==300)throw Error('rotation or crop size');
let crop=canvases[1].calls[0];if(crop[2]!==100||crop[3]!==150)throw Error('crop origin');
buildOnlineImage(bitmap,0,null,{width:480,height:320});if(canvases[3].width!==1200||canvases[3].height!==800)throw Error('whole image');
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True)
  self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
