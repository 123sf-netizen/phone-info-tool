import subprocess
import unittest
from pathlib import Path


class SalesDisplayTest(unittest.TestCase):
    def test_discontinued_price_hidden_and_status_source_escaped(self):
        html = (Path(__file__).resolve().parents[2] / 'index.html').read_text(encoding='utf-8')
        start = html.index('function escapeMarkup(')
        end = html.index('function filter()', start)
        javascript = """
const document={querySelector:()=>null}, window={scrollTo:()=>{}};
let detailActive=true, detailOrigin={}, page='home', activeBrand=null, phoneImages={}, content={innerHTML:''};
const closeBrand=()=>{}, batteryTypical=x=>x;
let phones=[{id:1,name:'test',status:'停售',battery:'1000mAh',charge:'10W',
salesStatusSource:{region:'<b>地区</b>',channel:'官网',url:'https://example.com',checkedAt:'2026-01-01'},
launchPrice:{currency:'CNY',amount:1234,variant:'8GB',type:'历史价格',region:'地区',url:'https://example.com',checkedAt:'2026-01-01'}}];
""" + html[start:end] + """
detail(1);
if(content.innerHTML.includes('¥1234') || !content.innerHTML.includes('&lt;b&gt;地区&lt;/b&gt;')) process.exit(1);
phones[0].status='在售'; detail(1);
if(!content.innerHTML.includes('¥1234')) process.exit(2);
phones[0].launchPrice.variant='<img src=x>'; phones[0].launchPrice.url='javascript:alert(1)'; detail(1);
if(content.innerHTML.includes('<img src=x>') || !content.innerHTML.includes('&lt;img src=x&gt;') || content.innerHTML.includes('javascript:alert')) process.exit(3);
"""
        result = subprocess.run(['node'], input=javascript.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
