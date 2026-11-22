import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import scheduled_sources as s
from official_check import SourceCheckError

class ScheduledSourcesTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.now=datetime(2026,11,20,tzinfo=timezone.utc)
  self.phones=[{'id':1,'name':'A','ip':'待补充','specUrl':'https://www.mi.com/test'}]
 def test_typical_battery_candidate_is_unverified_and_conflicts_are_not_proposed(self):
  phones=[{'id':1,'name':'A','specUrl':'https://www.mi.com/test'}]
  checker=Mock(side_effect=lambda url,fields:{'snippets_by_field':{f:['典型容量：5000mAh'] if f=='battery' else [] for f in fields}})
  original=json.dumps(phones,ensure_ascii=False)
  s.run_once(self.tmp.name,phones,self.now,checker)
  battery=next(r for r in s.read_state(self.tmp.name)['records'] if r['field']=='battery')
  self.assertEqual(battery['candidate']['value'],'5000mAh（典型值）')
  self.assertEqual(battery['candidate']['status'],'待核实')
  self.assertEqual(json.dumps(phones,ensure_ascii=False),original)
  phones[0]['specFieldSources']={'battery':{'status':'资料冲突'}}
  s.run_once(self.tmp.name,phones,self.now+timedelta(days=8),checker)
  battery=[r for r in s.read_state(self.tmp.name)['records'] if r['field']=='battery'][-1]
  self.assertNotIn('candidate',battery)
 def test_shared_page_is_fetched_once_and_fields_remain_separate(self):
  before=json.dumps(self.phones,ensure_ascii=False)
  checker=Mock(side_effect=lambda url, fields:{'snippets_by_field':{f:([f+'线索'] if f=='battery' else []) for f in fields}})
  first=s.run_once(self.tmp.name,self.phones,self.now,checker)
  records=s.read_state(self.tmp.name)['records']
  self.assertEqual(checker.call_count,1);self.assertEqual(first['field_count'],11)
  self.assertEqual(len(records),11);self.assertEqual(records[0]['outcome'],'发现关键词')
  self.assertTrue(any(r['outcome']=='未提取到关键词' for r in records))
  self.assertIsNone(s.run_once(self.tmp.name,self.phones,self.now+timedelta(minutes=10),checker))
  self.assertIsNone(s.run_once(self.tmp.name,self.phones,self.now+timedelta(hours=1),checker))
  self.assertEqual(checker.call_count,1);self.assertEqual(json.dumps(self.phones,ensure_ascii=False),before)
 def test_different_sources_and_phones_are_not_combined(self):
  phones=[{'id':1,'name':'A','specUrl':'https://www.mi.com/spec','specFieldSources':{'ip':{'url':'https://www.mi.com/ip'}}},{'id':2,'name':'B','specUrl':'https://www.mi.com/spec'}]
  checker=Mock(side_effect=lambda url,fields:{'snippets_by_field':{f:[] for f in fields}})
  s.run_once(self.tmp.name,phones,self.now,checker)
  self.assertEqual(checker.call_count,1)
  records=s.read_state(self.tmp.name)['records']
  self.assertTrue(all(r['phone_id']==1 and r['url']==records[0]['url'] for r in records))
  self.assertEqual(len(set(r['field'] for r in records)),len(records))
 def test_failed_and_interrupted_attempts_observe_cooldown(self):
  checker=Mock(side_effect=RuntimeError('连接失败'))
  item=s.run_once(self.tmp.name,self.phones,self.now,checker)
  self.assertEqual(item['outcome'],'检查失败');self.assertEqual(item['error'],'连接失败')
  later=[{'id':2,'name':'B','specUrl':'https://www.mi.com/test'}]
  checker.side_effect=KeyboardInterrupt()
  with self.assertRaises(KeyboardInterrupt):s.run_once(self.tmp.name,later,self.now+timedelta(minutes=31),checker)
  self.assertEqual(s.read_state(self.tmp.name)['records'][-1]['outcome'],'检查中断或尚未完成')
  self.assertIsNone(s.run_once(self.tmp.name,later,self.now+timedelta(minutes=32),checker))
 def test_failure_types_use_separate_cooldowns(self):
  base={'phone_id':1,'field':'ip','url':'https://www.mi.com/test','attempted_at':self.now.isoformat(),'outcome':'检查失败'}
  def available(record,after):return any(c[2]=='ip' for c in s.eligible_candidates(self.phones,[record],self.now+after))
  for kind,delay in [('network',timedelta(hours=6)),('server_error',timedelta(hours=6)),('not_found',timedelta(days=30)),('blocked',timedelta(days=7)),('rate_limited',timedelta(days=7)),('other',timedelta(days=7))]:
   with self.subTest(kind=kind):
    record={**base,'error_kind':kind};self.assertFalse(available(record,delay-timedelta(seconds=1)));self.assertTrue(available(record,delay))
  interrupted={**base,'outcome':'检查中断或尚未完成'}
  self.assertFalse(available(interrupted,timedelta(hours=5)));self.assertTrue(available(interrupted,timedelta(hours=6)))
  legacy={**base};self.assertFalse(available(legacy,timedelta(days=6)));self.assertTrue(available(legacy,timedelta(days=7)))
  checker=Mock(side_effect=SourceCheckError('network','官网连接失败或超时'))
  result=s.run_once(self.tmp.name,self.phones,self.now,checker)
  self.assertEqual(result['error_kind'],'network');self.assertEqual(result['next_retry_at'],(self.now+timedelta(hours=6)).isoformat())
  self.assertTrue(all(r['error_kind']=='network' for r in s.read_state(self.tmp.name)['records']))

 def test_page_change_requires_same_model_and_source(self):
  checker=Mock(side_effect=lambda url,fields:{'snippets_by_field':{f:[] for f in fields},'page_hash':'a'*64,'resolved_url':url})
  first=s.run_once(self.tmp.name,self.phones,self.now,checker)
  self.assertEqual(first['page_change'],'首次有效检查')
  second=s.run_once(self.tmp.name,self.phones,self.now+timedelta(days=8),checker)
  self.assertEqual(second['page_change'],'页面文字未变化')
  checker.side_effect=lambda url,fields:{'snippets_by_field':{f:[] for f in fields},'page_hash':'b'*64,'resolved_url':url}
  third=s.run_once(self.tmp.name,self.phones,self.now+timedelta(days=16),checker)
  self.assertEqual(third['page_change'],'页面文字有变化')
  checker.side_effect=lambda url,fields:{'snippets_by_field':{f:[] for f in fields},'page_hash':'b'*64,'resolved_url':url+'/new'}
  fourth=s.run_once(self.tmp.name,self.phones,self.now+timedelta(days=24),checker)
  self.assertEqual(fourth['page_change'],'页面地址变化')
  checker.side_effect=lambda url,fields:{'snippets_by_field':{f:[] for f in fields},'page_hash':None,'resolved_url':url}
  fifth=s.run_once(self.tmp.name,self.phones,self.now+timedelta(days=32),checker)
  self.assertEqual(fifth['page_change'],'页面未提取到文字，无法比较')
  other=[{'id':2,'name':'B','specUrl':'https://www.mi.com/test'}]
  checker.side_effect=lambda url,fields:{'snippets_by_field':{f:[] for f in fields},'page_hash':'b'*64,'resolved_url':url}
  sixth=s.run_once(self.tmp.name,other,self.now+timedelta(days=33),checker)
  self.assertEqual(sixth['page_change'],'首次有效检查')

 def test_per_field_snippet_changes_and_filtering(self):
  current={'battery':['电池 5000mAh'], 'screen':[]}
  checker=Mock(side_effect=lambda url,fields:{'snippets_by_field':{f:current.get(f,[]) for f in fields},'page_hash':'a'*64,'resolved_url':url})
  first=s.run_once(self.tmp.name,self.phones,self.now,checker)
  self.assertEqual(first['field'],'battery');self.assertEqual(first['field_change'],'首次提取字段摘录')
  current['screen']=['屏幕 120Hz']
  s.run_once(self.tmp.name,self.phones,self.now+timedelta(days=8),checker)
  records=s.read_state(self.tmp.name)['records'];second=records[-11:];by_field={r['field']:r for r in second}
  self.assertEqual(by_field['battery']['field_change'],'字段摘录未变化')
  self.assertEqual(by_field['screen']['field_change'],'字段摘录有变化')
  self.assertEqual(by_field['battery']['previous_field_at'],self.now.isoformat())
  self.assertEqual(by_field['battery']['previous_snippets'],['电池 5000mAh'])
  self.assertEqual(by_field['screen']['previous_snippets'],[])
  self.assertEqual(by_field['battery']['previous_resolved_url'],'https://www.mi.com/test')
  current['battery']=['电池 5500mAh'];current['screen']=[]
  s.run_once(self.tmp.name,self.phones,self.now+timedelta(days=16),checker)
  records=s.read_state(self.tmp.name)['records'];latest={r['field']:r for r in records[-11:]}
  self.assertEqual(latest['battery']['field_change'],'字段摘录有变化')
  self.assertEqual(latest['screen']['field_change'],'本次未提取到字段摘录')
  self.assertEqual(latest['battery']['previous_snippets'],['电池 5000mAh'])
  self.assertEqual(latest['battery']['snippets'],['电池 5500mAh'])
  self.assertEqual(latest['screen']['previous_snippets'],['屏幕 120Hz'])
  page=s.official_records_page(records,field_change='字段摘录有变化')
  self.assertTrue(all(r['field_change']=='字段摘录有变化' for r in page['records']))
  old={'phone_id':55,'field':'ip','url':'https://www.mi.com/spec','attempted_at':self.now.isoformat()}
  self.assertEqual(s.official_records_page([old],field_change='未记录字段比较')['total'],1)
  with self.assertRaises(ValueError):s.official_records_page(records,field_change='unsupported')

 def test_report_pagination_is_stable_with_appends_and_detects_rotation(self):
  records=[{'phone_id':i,'phone_name':f'手机{i}','field':'ip','label':'防护','url':'https://www.mi.com/x','attempted_at':self.now.isoformat(),'outcome':'检查失败' if i%2 else '发现关键词'} for i in range(120)]
  first=s.official_records_page(records,limit=50)
  self.assertEqual(len(first['records']),50);self.assertEqual(first['total'],120)
  later=[*records,{'phone_id':999,'phone_name':'新机','field':'ip','url':'https://www.mi.com/x','attempted_at':self.now.isoformat(),'outcome':'发现关键词'}]
  second=s.official_records_page(later,before=first['next_cursor'],limit=50)
  self.assertEqual([r['phone_id'] for r in second['records']],list(range(69,19,-1)))
  self.assertFalse(set(r['phone_id'] for r in first['records']) & set(r['phone_id'] for r in second['records']))
  filtered=s.official_records_page(records,limit=10,keyword='手机1',outcome='检查失败')
  self.assertTrue(all('手机1' in r['phone_name'] and r['outcome']=='检查失败' for r in filtered['records']))
  with self.assertRaises(LookupError):s.official_records_page(records[:10],before=first['next_cursor'])
  with self.assertRaises(ValueError):s.official_records_page(records,before='bad')
  with self.assertRaises(ValueError):s.official_records_page(records,limit=101)
  with self.assertRaises(ValueError):s.official_records_page(records,outcome='不支持')

 def test_invalid_report_not_overwritten_and_unsafe_url_skipped(self):
  path=Path(self.tmp.name)/s.FILE;path.write_text('bad',encoding='utf8')
  with self.assertRaises(ValueError):s.run_once(self.tmp.name,self.phones,self.now)
  self.assertEqual(path.read_text(encoding='utf8'),'bad')
  self.assertIsNone(s.pick_candidate([{'id':2,'specUrl':'http://127.0.0.1'}],[],self.now))
if __name__=='__main__':unittest.main()

