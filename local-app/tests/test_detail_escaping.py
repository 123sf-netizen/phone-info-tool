import subprocess
import unittest
from pathlib import Path


class DetailEscapingTests(unittest.TestCase):
    def test_user_data_is_text_and_unsafe_links_are_blocked(self):
        html = (Path(__file__).resolve().parents[2] / 'index.html').read_text(encoding='utf-8')
        cards = html[html.index('function cards(list)'):html.index('function toggle(id)')]
        detail = html[html.index('function escapeMarkup('):html.index('function filter()')]
        js = r"""
const location={href:'http://localhost/'};
const content={innerHTML:'',textContent:''},document={querySelector:()=>null};
const window={scrollY:0,scrollTo(){}},page='search',activeBrand='';
let detailOrigin=null,detailActive=false;function closeBrand(){}
const payload='<svg/onload=alert(1)>',phoneImages={1:'javascript:alert(1)'};
const phones=[{id:1,name:payload,brand:'test',chip:payload,screen:payload,battery:payload,charge:payload,camera:payload,front:payload,weight:payload,ip:payload,system:payload,storage:payload,updates:payload,source:payload,specRegion:payload,specUrl:'javascript:alert(1)',tags:[payload],releaseSource:{region:payload,url:'javascript:alert(1)',checkedAt:payload}}];
CODE
const card=cards(phones);detail(1);const pageHtml=content.innerHTML;
if(card.includes(payload)||pageHtml.includes(payload)||card.includes('src="javascript:')||pageHtml.includes('href="javascript:')||!pageHtml.includes('&lt;svg/onload=alert(1)&gt;')||!pageHtml.includes('href="#"'))process.exit(1);
""".replace('CODE', cards + detail)
        result = subprocess.run(['node'], input=js.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_brand_cards_escape_user_content(self):
        html = (Path(__file__).resolve().parents[2] / 'index.html').read_text(encoding='utf-8')
        brand = html[html.index('function renderBrand()'):html.index('function closeBrand()')]
        helpers = html[html.index('function escapeMarkup('):html.index('function detail(id)')]
        js = r"""
const location={href:'http://localhost/'},payload='<svg/onload=alert(1)>',activeBrand='test',brandGroups={test:['test']};
const phones=[{id:1,name:payload,brand:'test',chip:payload,screen:payload,status:payload}],phoneImages={1:'javascript:alert(1)'};
const nodes={'#brandSearch':{value:''},'#brandSeries':{value:''},'#brandResults':{innerHTML:''}};
const document={querySelector:key=>nodes[key]};function brandLabel(){return 'test'}function seriesOf(){return ''}
CODE
renderBrand();const out=nodes['#brandResults'].innerHTML;
if(out.includes(payload)||out.includes('src="javascript:')||!out.includes('&lt;svg/onload=alert(1)&gt;'))process.exit(1);
""".replace('CODE', helpers + brand)
        result = subprocess.run(['node'], input=js.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))

    def test_home_skips_missing_featured_models_and_escapes_content(self):
        html = (Path(__file__).resolve().parents[2] / 'index.html').read_text(encoding='utf-8')
        start = html.index('function render(){')
        render = html[start:html.index('}render();', start) + 1]
        helpers = html[html.index('function escapeMarkup('):html.index('function detail(id)')]
        js = r"""
const location={href:'http://localhost/',protocol:'http:'},payload='<svg/onload=alert(1)>';
const document={getElementById:()=>null},content={innerHTML:''},page='home';
const window={showcaseItems:[{id:1,subtitle:payload},{id:2,subtitle:'missing'}]},phones=[{id:1,name:payload}],phoneImages={1:'javascript:alert(1)'};
CODE
render();const out=content.innerHTML;
if(out.includes(payload)||out.includes('src="javascript:')||out.includes('missing')||!out.includes('&lt;svg/onload=alert(1)&gt;'))process.exit(1);
""".replace('CODE', helpers + render)
        result = subprocess.run(['node'], input=js.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
