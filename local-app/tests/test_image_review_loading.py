import subprocess
import unittest
from pathlib import Path


class ImageReviewLoadingTest(unittest.TestCase):
    def test_preview_loading_must_be_reconfirmed(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8-sig')
        start = html.index("document.getElementById('inspectImage').onclick=")
        end = html.index("document.getElementById('saveImageReview').onclick=", start)
        code = html[start:end]
        script = r'''
const els={};const document={getElementById:id=>els[id]||(els[id]={value:'',checked:false,disabled:false,style:{},removeAttribute(){},naturalWidth:0})};
let imageRows=[{id:1,name:'Test',address:'images/test.png',status:'本地文件存在',visual_status:'已核实',review:{loads:true}}],selectedImage=null;
CODE
const get=id=>document.getElementById(id);get('imagePhoneId').value='1';get('inspectImage').onclick();
if(!get('imageLoads').disabled||get('imageLoads').checked)throw Error('旧加载状态不应自动确认');
get('imagePreview').naturalWidth=100;get('imagePreview').onload();if(get('imageLoads').disabled)throw Error('加载成功后仍不可确认');
get('imageLoads').checked=true;get('imagePreview').onerror();if(!get('imageLoads').disabled||get('imageLoads').checked)throw Error('失败未清除');
get('imagePreview').onload();get('imageLoads').checked=true;get('imagePhoneId').oninput();if(!get('imageLoads').disabled||get('imageLoads').checked)throw Error('切换未清除');
'''.replace('CODE', code)
        result = subprocess.run(['node'], input=script.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
