import subprocess
import unittest
from pathlib import Path


class MallTests(unittest.TestCase):
    def test_validity_filter_and_escaping(self):
        html = (Path(__file__).resolve().parents[2] / 'index.html').read_text(encoding='utf-8')
        code = html[html.index('// MALL_BEGIN'):html.index('// MALL_END')]
        helpers = html[html.index('function escapeMarkup('):html.index('// FIELD_EVIDENCE_BEGIN')]
        helpers += html[html.index('function fieldSourceUrl('):html.index('function validFieldDate(')]
        helpers += html[html.index('function usableMarketQuote('):html.index('function renderMarketQuoteCard(')]
        helpers += html[html.index('function batteryTypical('):html.index('function toggle(', html.index('function batteryTypical('))]
        script = r'''
const location={href:'http://localhost/',protocol:'http:'},phoneImages={};
HELPERS
CODE
const quote={observedAt:new Date().toISOString(),region:'中国大陆',channel:'官网',variant:'12GB',currency:'CNY',amount:'1000',url:'https://example.com/shop'};
const phone={id:1,name:'<phone>',status:'在售',salesStatusSource:{region:'中国大陆',channel:'官网'},marketQuotes:[quote]};
if(mallRows([phone],'PHONE').length!==1||mallRows([{...phone,status:'停售'}]).length||mallRows([{...phone,marketQuotes:[{...quote,url:'javascript:evil'}]}]).length||mallRows([{...phone,marketQuotes:[{...quote,observedAt:'2020-01-01T00:00:00Z'}]}]).length)throw Error('筛选错误');
const html=mallCards(mallRows([phone]));if(!html.includes('&lt;phone&gt;')||!html.includes('https://example.com/shop')||html.includes('<phone>'))throw Error('输出错误');
const known={id:5,name:'Xiaomi 17 Ultra',chip:'<chip>',battery:'6800mAh（典型值）；6600mAh（额定值）'};const linked=mallRows([known]);const card=mallCards(linked);if(linked.length!==1||!card.includes('product_id=22422')||!card.includes('处理器：&lt;chip&gt;')||!card.includes('电池：6800mAh（典型值）')||card.includes('6600mAh')||card.includes('价格与库存以渠道为准'))throw Error('商品信息显示错误');
if(mallRows([{...known,status:'停售'}]).length||mallRows([{...known,name:'其他型号'}]).length)throw Error('型号或停售过滤失败');
'''.replace('HELPERS', helpers).replace('CODE', code)
        result = subprocess.run(['node'], input=script.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
