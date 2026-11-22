import subprocess,unittest
from pathlib import Path
class PhotoChoiceTest(unittest.TestCase):
 def test_choice_routes_to_camera_or_library_and_escape(self):
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');code=h[h.index('// PHOTO_CHOICE_BEGIN'):h.index('// PHOTO_CHOICE_END')]
  js=r'''
const nodes={};let focused=0;function elem(tag){return {tag,style:{},children:[],attrs:{},setAttribute(k,v){this.attrs[k]=v},addEventListener(k,f){this[k]=f},append(...xs){this.children.push(...xs)},remove(){if(this.id)delete nodes[this.id]},focus(){focused++},click(){this.clicked=(this.clicked||0)+1}}}
const document={activeElement:{focus(){focused++}},createElement:elem,getElementById(id){return nodes[id]||null},body:{append(x){nodes[x.id]=x}}};nodes['photo-model-input']=elem('input');nodes['photo-library-input']=elem('input');
CODE
openPhotoSearch();let dialog=nodes['photo-choice-dialog'],buttons=dialog.children[0].children.slice(2);if(dialog.attrs.role!=='dialog'||buttons.length!==3)throw Error('dialog');buttons[0].onclick();if(nodes['photo-model-input'].clicked!==1||nodes['photo-library-input'].clicked)throw Error('camera');
openPhotoSearch();dialog=nodes['photo-choice-dialog'];dialog.children[0].children[3].onclick();if(nodes['photo-library-input'].clicked!==1)throw Error('library');
openPhotoSearch();dialog=nodes['photo-choice-dialog'];dialog.keydown({key:'Escape',preventDefault(){}});if(nodes['photo-choice-dialog'])throw Error('escape');
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
 def test_candidates_can_reuse_file_for_cropping(self):
  h=(Path(__file__).resolve().parents[2]/'index.html').read_text(encoding='utf8');code=h[h.index('function showBackCandidates('):h.index('// BACK_CANDIDATES_BEGIN')]
  js=r'''
let overlay,opened=null;const document={createElement(tag){return {tag,style:{},children:[],append(...x){this.children.push(...x)},remove(){this.removed=true},focus(){}}},body:{append(x){overlay=x}}};async function showBackCrop(file){opened=file}function alert(){};
CODE
const file={name:'photo'};showBackCandidates([],{},file);const box=overlay.children[0],retry=box.children.find(x=>x.textContent==='重新框选或在线搜索');if(!retry)throw Error('retry missing');retry.onclick();if(opened!==file||!overlay.removed)throw Error('file not reused');
'''.replace('CODE',code)
  r=subprocess.run(['node'],input=js.encode('utf8'),capture_output=True);self.assertEqual(r.returncode,0,r.stderr.decode('utf8',errors='replace'))
if __name__=='__main__':unittest.main()
