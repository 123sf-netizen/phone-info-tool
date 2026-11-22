import subprocess
import unittest
from pathlib import Path


class BackMatchingTests(unittest.TestCase):
    def test_distance_only_accepts_similar_nonblank_images(self):
        html = (Path(__file__).resolve().parents[2] / 'index.html').read_text(encoding='utf-8')
        start = html.index('// BACK_IMAGE_MATCH_BEGIN')
        end = html.index('// BACK_IMAGE_MATCH_END', start)
        code = html[start:end] + '''
const a={gray:Array.from({length:256},(_,i)=>i%2?230:20),variance:1000};
const same={gray:a.gray.slice(),variance:1000};
const brighter={gray:a.gray.map(x=>x+20),variance:1000};
const overexposed={gray:a.gray.map(x=>x+50),variance:1000};
const different={gray:a.gray.map(x=>255-x),variance:1000};
const blank={gray:Array(256).fill(255),variance:0};
const masked={gray:a.gray.map((x,i)=>i<128?x:255-x),variance:1000,mask:Array.from({length:256},(_,i)=>i<128)};
const tooSmall={...masked,mask:Array.from({length:256},(_,i)=>i<127)};
if(backImageDistance(a,same)!==0 || backImageDistance(brighter,a)!==0 || backImageDistance(overexposed,a)!==Infinity || backImageDistance(a,different)<=12 || backImageDistance(a,blank)!==Infinity || backImageDistance(a,masked)!==0 || backImageDistance(a,tooSmall)!==Infinity)process.exit(1);
'''
        result = subprocess.run(['node'], input=code.encode('utf-8'), capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))


if __name__ == '__main__':
    unittest.main()
