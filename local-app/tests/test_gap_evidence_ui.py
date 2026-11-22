import subprocess
import unittest
from pathlib import Path


class GapEvidenceUiTests(unittest.TestCase):
    def test_evidence_links_and_missing_state(self):
        html = (Path(__file__).resolve().parents[1] / 'admin.html').read_text(encoding='utf-8')
        start = html.index('// GAP_EVIDENCE_BEGIN')
        end = html.index('// GAP_EVIDENCE_END', start)
        js = r"""
const document={createElement:tag=>({tag,textContent:'',children:[],append(...nodes){this.children.push(...nodes)}}),createTextNode:text=>({tag:'text',textContent:text})};
CODE
let missing=gapEvidenceNode({evidence:null});if(!missing.textContent.includes('未登记'))process.exit(1);
let old=gapEvidenceNode({});if(!old.textContent.includes('接口未提供'))process.exit(2);
let bad=gapEvidenceNode({evidence:{status:'待核实',url:'javascript:alert(1)'}});if(bad.children.some(x=>x.tag==='a')||!bad.children.some(x=>x.textContent.includes('链接无效')))process.exit(3);
let good=gapEvidenceNode({evidence:{status:'待核实',region:'中国大陆',checkedAt:'2026-01-01',url:'https://example.org/spec'}});let link=good.children.find(x=>x.tag==='a');if(!link||link.href!=='https://example.org/spec'||link.rel!=='noopener noreferrer'||!good.textContent.includes('待核实'))process.exit(4);
""".replace('CODE', html[start:end])
        result = subprocess.run(['node'], input=js.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
