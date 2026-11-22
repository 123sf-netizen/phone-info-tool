"""在内存 SQLite 中验证反馈流程，不连接或修改正式数据库。"""
import unittest
from unittest.mock import patch, mock_open

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
import app


class FeedbackTests(unittest.TestCase):
    def setUp(self):
        self.previous_engine = app.engine
        app.engine = create_engine('sqlite://')
        app.metadata.create_all(app.engine)

    def tearDown(self):
        app.engine.dispose()
        app.engine = self.previous_engine

    def test_market_quote_visibility_conflict_and_history(self):
        from datetime import datetime, timezone, timedelta
        from pydantic import ValidationError
        now=datetime.now(timezone.utc)
        phone={'id':91,'name':'测试机','status':'在售','salesStatusSource':{'region':'中国大陆','channel':'官网'}}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=91,name='测试机',brand='B',data=phone))
        data=dict(amount='1234.50',currency='CNY',variant='8GB+256GB',region='中国大陆',channel='官网',url='https://example.com/product',observed_at=now,expected_quote=None)
        edit=app.MarketPriceEdit(**data)
        result=app.admin_update_market_quote(91,edit)
        self.assertEqual(result['quote']['amount'],'1234.50')
        self.assertEqual(app.admin_phone(91)['marketQuote'],result['quote'])
        self.assertEqual(app.get_phone(91)['marketQuote'],result['quote'])
        self.assertEqual(app.admin_phone_history(91, limit=100)[0]['field'],'marketQuote')
        with self.assertRaises(HTTPException) as error: app.admin_update_market_quote(91,edit)
        self.assertEqual(error.exception.status_code,409)
        quote=result['quote']; item={**phone,'marketQuote':quote}
        self.assertIsNotNone(app.public_market_quote(item,now+timedelta(hours=23)))
        self.assertIsNone(app.public_market_quote(item,now+timedelta(hours=24)))
        self.assertIsNone(app.public_market_quote({**item,'status':'停售'},now))
        self.assertIsNone(app.public_market_quote({**item,'salesStatusSource':{'region':'其他地区','channel':'官网'}},now))
        self.assertIsNone(app.public_market_quote({**item,'status':'销售状态待核实'},now))
        self.assertIsNone(app.public_market_quote({**item,'marketQuote':{**quote,'url':'javascript:evil'}},now))
        with self.assertRaises(ValidationError):app.MarketPriceEdit(**{**data,'observed_at':now+timedelta(days=1)})
        with self.assertRaises(ValidationError):app.MarketPriceEdit(**{**data,'url':'http://example.com'})

    def test_multiple_market_quotes_compatibility_and_expiry(self):
        from datetime import datetime, timezone, timedelta
        now=datetime.now(timezone.utc)
        legacy={'amount':'100','currency':'CNY','variant':'8GB','region':'中国大陆','channel':'官网','url':'https://example.com','observedAt':now.isoformat()}
        phone={'id':92,'name':'多版本','status':'在售','salesStatusSource':{'region':'中国大陆','channel':'官网'},'marketQuote':legacy}
        with app.engine.begin() as c:c.execute(app.phones.insert().values(id=92,name='多版本',brand='B',data=phone))
        values=dict(amount='200',currency='CNY',variant='12GB',region='中国大陆',channel='官网',url='https://example.com',observed_at=now,expected_quote=legacy,expected_quotes=None,slot=None)
        result=app.admin_save_market_quotes(92,app.MarketQuotesEdit(**values))
        self.assertEqual(len(result['quotes']),1)
        self.assertEqual(len(app.get_phone(92)['marketQuotes']),2)
        with self.assertRaises(HTTPException) as e:app.admin_save_market_quotes(92,app.MarketQuotesEdit(**values))
        self.assertEqual(e.exception.status_code,409)
        with self.assertRaises(HTTPException) as e:app.admin_save_market_quotes(92,app.MarketQuotesEdit(**{**values,'expected_quotes':result['quotes']}))
        self.assertEqual(e.exception.status_code,409)
        edit={**values,'slot':'0','amount':'250','expected_quotes':result['quotes']}
        updated=app.admin_save_market_quotes(92,app.MarketQuotesEdit(**edit))
        self.assertEqual(updated['quotes'][0]['amount'],'250')
        self.assertEqual(updated['legacy'],legacy)
        mixed={**phone,'marketQuotes':[{**updated['quotes'][0],'observedAt':(now-timedelta(days=1)).isoformat()}]}
        self.assertEqual(len(app.public_market_quotes(mixed,now)),1)
        self.assertEqual(app.market_quote_report([mixed],now)['机型'][0]['record_states'],['可展示','已过期'])
        self.assertEqual(app.public_market_quotes({**mixed,'status':'停售'},now),[])
        with self.assertRaises(HTTPException) as e:app.admin_update_market_quote(92,app.MarketPriceEdit(**{k:v for k,v in values.items() if k not in ('slot','expected_quotes')}))
        self.assertEqual(e.exception.status_code,409)

    def test_market_gap_report_matches_public_rules(self):
        from datetime import datetime, timedelta, timezone
        now=datetime.now(timezone.utc)
        base={'id':1,'name':'A','status':'在售','salesStatusSource':{'region':'中国大陆','channel':'官网'}}
        quote={'amount':'123.00','currency':'CNY','variant':'8GB','region':'中国大陆','channel':'官网','url':'https://example.com/','observedAt':now.isoformat()}
        items=[base,{**base,'id':2,'marketQuote':quote},{**base,'id':3,'marketQuote':{**quote,'observedAt':(now-timedelta(days=1)).isoformat()}},{**base,'id':4,'status':'停售'}, {**base,'id':5,'marketQuote':{**quote,'channel':'其他'}}]
        report=app.market_quote_report(items,now)
        self.assertEqual(report['机型数'],5);self.assertEqual(report['未录入快照'],2)
        self.assertEqual([r['status'] for r in report['机型']],['未录入','可展示','已过期','停售隐藏','地区或渠道不匹配'])
        for item in items:
            self.assertEqual(app.public_market_quote(item,now) is not None,app.classify_market_quote(item,now)=='可展示')
        with app.engine.begin() as connection:
            for item in items:connection.execute(app.phones.insert().values(id=item['id'],name='测试'+str(item['id']),brand='B',data=item))
        self.assertEqual(app.admin_market_quote_gaps()['机型数'],5)

    def test_scheduled_official_endpoint_pagination_and_bad_filter(self):
        rows=[{'phone_id':i,'phone_name':'测试'+str(i),'field':'ip','label':'防护','url':'https://www.mi.com/x','attempted_at':'2026-11-20T00:00:00+00:00','outcome':'检查失败'} for i in range(3)]
        with patch.object(app,'read_official_check_state',return_value={'last_attempt':None,'records':rows}):
            page=app.admin_scheduled_official(before=None,limit=2,keyword='',outcome='',field_change='')
            self.assertEqual([r['phone_id'] for r in page['records']],[2,1]);self.assertEqual(page['total'],3)
            next_page=app.admin_scheduled_official(before=page['next_cursor'],limit=2,keyword='',outcome='',field_change='')
            self.assertEqual([r['phone_id'] for r in next_page['records']],[0])
            with self.assertRaises(HTTPException) as error:app.admin_scheduled_official(before='0'*64,limit=2,keyword='',outcome='',field_change='')
            self.assertEqual(error.exception.status_code,409)
            with self.assertRaises(HTTPException) as error:app.admin_scheduled_official(before=None,limit=2,keyword='',outcome='unsupported',field_change='')
            self.assertEqual(error.exception.status_code,422)

    def test_backend_date_validation_uses_china_calendar_day(self):
        from datetime import date
        from pydantic import ValidationError
        with patch.object(app,'china_today',return_value=date(2026,11,21)):
            record=app.ResearchRequest(status='查找中',region='中国大陆',scope='官网',checked_at='2026-11-21')
            self.assertEqual(record.checked_at,date(2026,11,21))
            with self.assertRaises(ValidationError):
                app.ResearchRequest(status='查找中',region='中国大陆',scope='官网',checked_at='2026-11-22')
            sale=app.SalesStatusEdit(value='在售',expected_value=None,expected_evidence=None,region='中国大陆',channel='官网',url='https://example.com',checked_at='2026-11-21')
            self.assertEqual(sale.checked_at,date(2026,11,21))

    def test_online_vision_requires_consent_and_configuration(self):
        import base64
        image = base64.b64encode(b'\xff\xd8\xfftest').decode()
        with patch.dict(app.os.environ, {'ONLINE_VISION_ENABLED':'0', 'GOOGLE_VISION_API_KEY':''}):
            self.assertFalse(app.online_vision_status()['enabled'])
            with self.assertRaises(HTTPException) as error:
                app.online_vision(app.OnlineVisionRequest(image=image, consent=False))
            self.assertEqual(error.exception.status_code, 400)
            with self.assertRaises(HTTPException) as error:
                app.online_vision(app.OnlineVisionRequest(image=image, consent=True))
            self.assertEqual(error.exception.status_code, 503)
        with patch.dict(app.os.environ, {'ONLINE_VISION_ENABLED':'1', 'GOOGLE_VISION_API_KEY':'test'}), \
             patch.object(app, 'allow_online_request', return_value=True), \
             patch.object(app, 'search_google', return_value={'pages': [], 'labels': []}) as search:
            result = app.online_vision(app.OnlineVisionRequest(image=image, consent=True))
            self.assertEqual(result, {'pages': [], 'labels': []})
            search.assert_called_once()

    def test_feedback_request_id_prevents_duplicates_and_reuse(self):
        request_id = 'f12df826-0742-4951-9df1-f965ce791234'
        item = app.FeedbackRequest(type='问题反馈', text='测试反馈', request_id=request_id)
        first = app.submit_feedback(item)
        self.assertEqual(app.submit_feedback(item), first)
        self.assertEqual(len(app.admin_feedback(limit=10)), 1)
        with self.assertRaises(HTTPException) as error:
            app.submit_feedback(app.FeedbackRequest(type='问题反馈', text='不同内容', request_id=request_id))
        self.assertEqual(error.exception.status_code, 409)
        self.assertEqual(len(app.admin_feedback(limit=10)), 1)
        with self.assertRaises(ValidationError):
            app.FeedbackRequest(type='问题反馈', text='测试', request_id='not-a-uuid')

    def test_feedback_cursor_paginates_without_repeating_rows(self):
        for index in range(5):
            app.submit_feedback(app.FeedbackRequest(type='问题反馈', text=f'测试 {index}'))
        first = app.admin_feedback(limit=2)
        self.assertEqual([row['id'] for row in first], [5, 4])
        second = app.admin_feedback(limit=2, before_id=first[-1]['id'])
        self.assertEqual([row['id'] for row in second], [3, 2])
        third = app.admin_feedback(limit=2, before_id=second[-1]['id'])
        self.assertEqual([row['id'] for row in third], [1])
        self.assertEqual(app.admin_feedback(limit=2, before_id=1), [])
        with self.assertRaises(HTTPException) as error:
            app.admin_feedback(limit=2, before_id=0)
        self.assertEqual(error.exception.status_code, 422)

    def test_status_round_trip_preserves_content(self):
        feedback_id = app.submit_feedback(app.FeedbackRequest(type='问题反馈', text='测试反馈'))['id']
        self.assertEqual(app.admin_feedback(limit=10)[0]['status'], '待处理')
        app.admin_feedback_status(feedback_id, app.FeedbackStatusRequest(status='处理中'))
        app.admin_feedback_status(feedback_id, app.FeedbackStatusRequest(status='已处理'))
        row = app.admin_feedback(limit=10)[0]
        self.assertEqual(row['status'], '已处理')
        self.assertEqual(row['text'], '测试反馈')

    def test_back_reference_requires_review_and_can_be_disabled(self):
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data={'id': 1, 'name': '测试机'}))
        payload = {'address': 'images/back.png', 'sha256': 'a' * 64, 'region': '中国大陆',
                   'color': '白色', 'source_url': 'https://example.com', 'source_status': '厂商官方核实', 'checked_at': '2026-01-01'}
        with self.assertRaises(HTTPException) as exc:
            app.admin_add_back_reference(1, app.BackReferenceCreate(**payload))
        self.assertEqual(exc.exception.status_code, 422)
        payload.update(model_match=True, color_match=True, back_only=True, full_body=True, no_watermark=True, loads=True)
        item = app.BackReferenceCreate(**payload)
        with patch.object(app, 'inspect_reference_file', return_value='b' * 64):
            with self.assertRaises(HTTPException) as exc:
                app.admin_add_back_reference(1, item)
            self.assertEqual(exc.exception.status_code, 409)
        with patch.object(app, 'inspect_reference_file', return_value='a' * 64), \
             patch('builtins.open', mock_open(read_data='{"version":1,"references":[]}')):
            added = app.admin_add_back_reference(1, item)
            with self.assertRaises(HTTPException) as exc:
                app.admin_add_back_reference(1, item)
            self.assertEqual(exc.exception.status_code, 409)
        with patch.object(app, 'available_references', return_value=[]), \
             patch.object(app, 'filter_references', side_effect=lambda refs, root, phones: refs):
            self.assertEqual(len(app.recognition_references()), 1)
            app.admin_set_back_reference_state(added['id'], app.BackReferenceState(active=False, expected_active=True))
            self.assertEqual(app.recognition_references(), [])
            with self.assertRaises(HTTPException) as exc:
                app.admin_set_back_reference_state(added['id'], app.BackReferenceState(active=True, expected_active=True))
            self.assertEqual(exc.exception.status_code, 409)
        with patch.object(app, 'filter_references', return_value=[]):
            with self.assertRaises(HTTPException) as exc:
                app.admin_set_back_reference_state(added['id'], app.BackReferenceState(active=True, expected_active=False))
            self.assertEqual(exc.exception.status_code, 409)
        with patch.object(app, 'filter_references', return_value=[{}]):
            app.admin_set_back_reference_state(added['id'], app.BackReferenceState(active=True, expected_active=False))
        with app.engine.connect() as connection:
            self.assertEqual(len(list(connection.execute(app.back_reference_log.select()))), 3)

    def test_release_date_edit_records_evidence_and_rejects_stale(self):
        phone = {'id': 1, 'name': '测试机', 'releaseDate': '2020-01-01',
                 'releaseSource': {'status': '待核实', 'note': '原始说明'}}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        edit = app.ReleaseEdit(value='2021-02-03', expected_value='2020-01-01',
                               expected_evidence=phone['releaseSource'], status='厂商官方核实',
                               region='中国大陆', url='https://example.com', checked_at='2026-01-01')
        result = app.admin_update_release('phones', 1, edit)
        self.assertEqual(result['value'], '2021-02-03')
        self.assertEqual(app.get_phone(1)['releaseSource']['note'], '原始说明')
        self.assertEqual(app.admin_phone_history(1, limit=10)[0]['field'], 'releaseDate')
        with self.assertRaises(HTTPException) as exc:
            app.admin_update_release('phones', 1, edit)
        self.assertEqual(exc.exception.status_code, 409)
        with self.assertRaises(ValidationError):
            app.ReleaseEdit(value='2021-02-03', expected_value=None, expected_evidence=None,
                            status='待核实', region='中国大陆', url='https://example.com', checked_at='2026-01-01')

    def test_release_gap_classification_and_label_update(self):
        source = {'status': '可靠渠道核实', 'region': '中国大陆', 'url': 'https://example.com', 'checkedAt': '2026-01-01'}
        phone = {'id': 1, 'name': '测试机', 'releaseDate': '2020-01-01',
                 'releaseDateLabel': '开售日期', 'releaseSource': source}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        report = app.admin_release_gaps()
        self.assertEqual(report['未完成机型'][0]['status'], '其他日期，发布日期待核实')
        self.assertEqual(report['未完成机型'][0]['evidence'], source)
        edit = app.ReleaseEdit(value='2019-12-30', expected_value='2020-01-01', expected_evidence=source,
                               expected_label='开售日期', status='厂商官方核实', region='中国大陆',
                               url='https://example.com', checked_at='2026-01-02')
        result = app.admin_update_release('phones', 1, edit)
        self.assertEqual(result['label'], '发布日期')
        self.assertEqual(app.get_phone(1)['releaseDateLabel'], '发布日期')
        self.assertEqual(app.admin_release_gaps()['未完成机型'], [])
        self.assertEqual(app.admin_phone_history(1, limit=10)[0]['before']['label'], '开售日期')

    def test_release_gap_does_not_trust_incomplete_or_invalid_sources(self):
        source = {'status': '厂商官方核实', 'region': '中国大陆', 'url': 'https://example.com', 'checkedAt': '2026-01-01'}
        rows = [{'id': 1, 'name': '缺失'},
                {'id': 2, 'name': '月份', 'releaseDate': '2020-01', 'releaseSource': source},
                {'id': 3, 'name': '无效来源', 'releaseDate': '2020-01-01', 'releaseSource': {**source, 'url': 'invalid'}},
                {'id': 4, 'name': '冲突', 'releaseDate': '2020-01-01', 'releaseSource': {**source, 'status': '资料冲突'}}]
        result = app.release_report(rows)
        self.assertEqual({x['status'] for x in result['未完成机型']},
                         {'缺失', '日期不完整或待核实', '来源或核实状态待核实', '资料冲突'})

    def test_sales_status_tracks_source_and_preserves_price_history(self):
        phone = {'id': 1, 'name': '测试机', 'status': '销售状态待核实',
                 'launchPrice': {'amount': 1000, 'type': '历史发布价'}}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        edit = app.SalesStatusEdit(value='停售', expected_value='销售状态待核实', expected_evidence=None,
                                   region='中国大陆', channel='厂商官网', url='https://example.com',
                                   checked_at='2026-01-01')
        app.admin_update_sales_status(1, edit)
        item = app.get_phone(1)
        self.assertEqual(item['status'], '停售')
        self.assertEqual(item['salesStatusSource']['channel'], '厂商官网')
        self.assertEqual(item['launchPrice'], phone['launchPrice'])
        self.assertEqual(app.admin_phone_history(1, limit=10)[0]['field'], 'status')
        with self.assertRaises(HTTPException) as exc:
            app.admin_update_sales_status(1, edit)
        self.assertEqual(exc.exception.status_code, 409)
        with self.assertRaises(ValidationError):
            app.SalesStatusEdit(value='停售', expected_value=None, expected_evidence=None,
                                region='中国大陆', channel=' ', url='https://example.com', checked_at='2026-01-01')

    def test_historical_prices_append_without_overwriting_and_detect_stale(self):
        phone = {'id': 1, 'name': '测试机', 'status': '停售'}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        def payload(variant, primary=None, variants=None):
            return app.HistoricalPriceAdd(amount='1999.50', currency='CNY', variant=variant,
                type='历史发布价格', status='厂商官方核实', region='中国大陆',
                url='https://example.com', checked_at='2026-01-01',
                expected_primary=primary, expected_variants=variants)
        first = app.admin_add_historical_price(1, payload('8GB+128GB'))
        self.assertEqual(first['primary']['amount'], 1999.5)
        with self.assertRaises(HTTPException) as exc:
            app.admin_add_historical_price(1, payload('12GB+256GB'))
        self.assertEqual(exc.exception.status_code, 409)
        with self.assertRaises(HTTPException) as exc:
            app.admin_add_historical_price(1, payload(' 8GB+128GB ', first['primary']))
        self.assertEqual(exc.exception.status_code, 409)
        second = app.admin_add_historical_price(1, payload('12GB+256GB', first['primary']))
        self.assertEqual(second['primary'], first['primary'])
        self.assertEqual(second['variants'][0]['variant'], '12GB+256GB')
        self.assertEqual(app.get_phone(1)['status'], '停售')
        self.assertEqual(len(app.admin_phone_history(1, limit=10)), 2)
        with self.assertRaises(ValidationError):
            app.HistoricalPriceAdd(amount='1.234', currency='CNY', variant='8GB', type='历史发布价格',
                status='厂商官方核实', region='中国大陆', url='https://example.com', checked_at='2026-01-01',
                expected_primary=None, expected_variants=None)

    def test_historical_price_edit_preserves_other_versions_and_checks_stale(self):
        primary = {'variant': '8GB+128GB', 'region': '中国大陆', 'amount': 1000, 'note': '保留的原始备注'}
        variants = [{'variant': '12GB+256GB', 'region': '中国大陆', 'amount': 2000}]
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data={
                'id': 1, 'name': '测试机', 'status': '停售', 'launchPrice': primary, 'launchPriceVariants': variants}))
        def payload(variant, expected_primary=primary, expected_variants=variants):
            return app.HistoricalPriceAdd(amount='1099', currency='CNY', variant=variant,
                type='历史发布价格', status='可靠渠道核实', region='中国大陆', url='https://example.com',
                checked_at='2026-01-01', expected_primary=expected_primary, expected_variants=expected_variants)
        with self.assertRaises(HTTPException) as exc:
            app.admin_edit_historical_price(1, 'primary', payload('12GB+256GB'))
        self.assertEqual(exc.exception.status_code, 409)
        result = app.admin_edit_historical_price(1, 'primary', payload('8GB+128GB'))
        self.assertEqual(result['primary']['amount'], 1099)
        self.assertEqual(result['primary']['note'], '保留的原始备注')
        self.assertEqual(result['variants'], variants)
        self.assertEqual(app.get_phone(1)['status'], '停售')
        self.assertEqual(app.admin_phone_history(1, limit=10)[0]['before']['primary'], primary)
        with self.assertRaises(HTTPException) as exc:
            app.admin_edit_historical_price(1, '0', payload('12GB+256GB'))
        self.assertEqual(exc.exception.status_code, 409)
        modified = app.admin_edit_historical_price(1, '0', payload('12GB+256GB', result['primary'], variants))
        self.assertEqual(modified['variants'][0]['amount'], 1099)
        self.assertEqual(modified['primary'], result['primary'])
        with self.assertRaises(HTTPException):
            app.admin_edit_historical_price(1, '../0', payload('12GB+256GB'))

    def test_price_inventory_counts_record_coverage_not_real_world_variants(self):
        verified = {'amount': 1000, 'currency': 'AED', 'variant': '8GB', 'region': '阿联酋',
                    'type': '历史发布价格', 'url': 'https://example.com', 'checkedAt': '2026-01-01', 'status': '可靠渠道核实'}
        conflict = {**verified, 'variant': '12GB', 'status': '资料冲突'}
        phones = [{'id': 1, 'name': '无价格'}, {'id': 2, 'name': '单条', 'launchPrice': verified},
                  {'id': 3, 'name': '多条', 'status': '停售', 'launchPrice': verified, 'launchPriceVariants': [conflict]},
                  {'id': 4, 'name': '其他版本无主价', 'launchPriceVariants': [verified]}]
        report = app.price_report(phones)
        self.assertEqual(report['机型记录覆盖'], {'未登记价格': 1, '仅一条记录': 2, '多条记录': 1})
        self.assertEqual(report['价格记录状态']['资料冲突'], 1)
        self.assertTrue(report['机型'][2]['discontinued'])
        self.assertIn('缺少主价格', report['机型'][3]['issues'])
        record = app.HistoricalPriceAdd(amount='1000', currency='AED', variant='8GB', type='历史发布价格',
            status='可靠渠道核实', region='阿联酋', url='https://example.com', checked_at='2026-01-01',
            expected_primary=None, expected_variants=None)
        self.assertEqual(record.currency, 'AED')

    def test_draft_release_survives_verified_publication(self):
        candidate = {'id': 12, 'name': '旧机', 'brand': 'B'}
        with patch.object(app, 'load_seed', return_value=[candidate]):
            app.admin_stage_legacy(12)
        edit = app.ReleaseEdit(value='2020-01-02', expected_value=None, expected_evidence=None,
                               status='可靠渠道核实', region='中国大陆', url='https://example.com', checked_at='2026-01-01')
        app.admin_update_release('legacy-drafts', 12, edit)
        self.assertEqual(app.admin_legacy_draft_history(12, limit=10)[0]['field'], 'releaseDate')
        app.admin_publish_legacy(12, app.PublishRequest(confirmed=True))
        self.assertEqual(app.get_phone(12)['releaseDate'], '2020-01-02')
        with self.assertRaises(HTTPException) as exc:
            app.admin_update_release('legacy-drafts', 12, edit)
        self.assertEqual(exc.exception.status_code, 409)

    def test_rejects_unknown_and_invalid(self):
        with self.assertRaises(ValidationError):
            app.FeedbackStatusRequest(status='乱填')
        with self.assertRaises(ValidationError):
            app.FeedbackRequest(type='问题反馈', text='  ')
        with self.assertRaises(HTTPException) as exc:
            app.admin_feedback_status(999, app.FeedbackStatusRequest(status='已处理'))
        self.assertEqual(exc.exception.status_code, 404)

    def test_image_review_requires_checks_and_rejects_changed_image(self):
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data={'id': 1, 'name': '测试机'}))
        payload = {'address': 'images/a.png', 'sha256': 'abc', 'status': '已核实',
                   'region': '中国大陆', 'color': '黑色', 'source_url': 'https://example.com',
                   'checked_at': '2026-01-01'}
        with self.assertRaises(HTTPException) as exc:
            app.admin_image_review(1, app.ImageReviewRequest(**payload))
        self.assertEqual(exc.exception.status_code, 422)
        payload.update(model_match=True, color_match=True, full_body=True, no_watermark=True, loads=True)
        current = {'机型': [{'address': 'images/a.png', 'sha256': 'changed', 'status': '本地文件存在'}]}
        with patch.object(app, 'load_image_map', return_value={}), patch.object(app, 'audit_images', return_value=current):
            with self.assertRaises(HTTPException) as exc:
                app.admin_image_review(1, app.ImageReviewRequest(**payload))
            self.assertEqual(exc.exception.status_code, 409)
            current['机型'][0]['sha256'] = 'abc'
            result = app.admin_image_review(1, app.ImageReviewRequest(**payload))
            self.assertEqual(result['status'], '已核实')
            with app.engine.connect() as connection:
                self.assertEqual(len(list(connection.execute(app.image_review_log.select()))), 1)

    def test_legacy_preview_only_lists_absent_ids_without_writing(self):
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='现有', brand='A', data={'id': 1, 'name': '现有'}))
        legacy = [{'id': 1, 'name': '现有', 'brand': 'A'},
                  {'id': 2, 'name': '旧机', 'brand': 'B', 'ip': '暂无数据'}]
        with patch.object(app, 'load_seed', return_value=legacy):
            rows = app.admin_legacy_candidates()
        self.assertEqual([r['id'] for r in rows], [2])
        self.assertEqual(rows[0]['fields']['ip'], '暂无数据')
        self.assertIn('不能视为已验证', rows[0]['warning'])
        with app.engine.connect() as connection:
            self.assertEqual(len(list(connection.execute(app.phones.select()))), 1)

    def test_legacy_staging_preserves_raw_data_without_publishing(self):
        candidate = {'id': 12, 'name': '旧机', 'brand': 'B', 'price': 123,
                     'specFieldSources': {'ip': {'status': '待核实'}}}
        with patch.object(app, 'load_seed', return_value=[candidate]):
            self.assertEqual(app.admin_stage_legacy(12)['status'], '待审核')
            self.assertTrue(app.admin_legacy_candidates()[0]['staged'])
            with self.assertRaises(HTTPException) as exc:
                app.admin_stage_legacy(12)
            self.assertEqual(exc.exception.status_code, 409)
        with app.engine.connect() as connection:
            self.assertEqual(list(connection.execute(app.phones.select())), [])
            saved = connection.execute(app.legacy_drafts.select()).first()
            self.assertEqual(saved.data, candidate)

    def test_legacy_staging_rejects_existing_name(self):
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='旧机', brand='B', data={'id': 1}))
        with patch.object(app, 'load_seed', return_value=[{'id': 2, 'name': '旧机', 'brand': 'B'}]):
            with self.assertRaises(HTTPException) as exc:
                app.admin_stage_legacy(2)
        self.assertEqual(exc.exception.status_code, 409)

    def test_draft_list_search_progress_and_excludes_published(self):
        candidates = [{'id': 12, 'name': '测试甲', 'brand': 'B', 'ip': 'IP53'},
                      {'id': 13, 'name': '测试乙', 'brand': 'B'}]
        with patch.object(app, 'load_seed', return_value=candidates):
            app.admin_stage_legacy(12)
            app.admin_stage_legacy(13)
        rows = app.admin_legacy_drafts(keyword='测试')
        self.assertEqual({row['id'] for row in rows}, {12, 13})
        first = next(row for row in rows if row['id'] == 12)
        self.assertFalse(first['ready'])
        self.assertEqual(first['blocked_count'], 1)
        self.assertEqual(first['missing_count'], 10)
        self.assertEqual([row['id'] for row in app.admin_legacy_drafts(keyword='甲')], [12])
        app.admin_publish_legacy(13, app.PublishRequest(confirmed=True))
        self.assertEqual([row['id'] for row in app.admin_legacy_drafts(keyword='')], [12])

    def test_legacy_draft_edit_is_logged_and_stays_unpublished(self):
        candidate = {'id': 12, 'name': '旧机', 'brand': 'B', 'ip': '暂无数据'}
        evidence = {'status': '待核实', 'url': 'https://example.com',
                    'region': '中国大陆', 'checkedAt': '2026-01-01'}
        with patch.object(app, 'load_seed', return_value=[candidate]):
            app.admin_stage_legacy(12)
        edit = app.FieldEdit(field='ip', value='IP53 待核实', expected_value='暂无数据',
                             expected_evidence=None, evidence=evidence)
        app.admin_update_legacy_draft(12, edit)
        self.assertEqual(app.admin_legacy_draft(12)['ip'], 'IP53 待核实')
        self.assertEqual(app.admin_legacy_draft_history(12, limit=10)[0]['before']['value'], '暂无数据')
        with self.assertRaises(HTTPException) as exc:
            app.get_phone(12)
        self.assertEqual(exc.exception.status_code, 404)
        with self.assertRaises(HTTPException) as exc:
            app.admin_update_legacy_draft(12, edit)
        self.assertEqual(exc.exception.status_code, 409)

    def test_legacy_publication_blocks_unverified_and_omits_unverified_media_price(self):
        draft = {'id': 12, 'name': '旧机', 'brand': 'B', 'ip': 'IP53',
                 'price': 123, 'launchPrice': {'amount': 123}, 'releaseDate': '2022-01-01'}
        with patch.object(app, 'load_seed', return_value=[draft]):
            app.admin_stage_legacy(12)
        self.assertFalse(app.admin_legacy_publish_check(12)['ready'])
        with self.assertRaises(HTTPException) as exc:
            app.admin_publish_legacy(12, app.PublishRequest(confirmed=True))
        self.assertEqual(exc.exception.status_code, 409)
        evidence = {'status': '可靠渠道核实', 'url': 'https://example.com',
                    'region': '中国大陆', 'checkedAt': '2026-01-01'}
        edit = app.FieldEdit(field='ip', value='IP53', expected_value='IP53',
                             expected_evidence=None, evidence=evidence)
        app.admin_update_legacy_draft(12, edit)
        self.assertTrue(app.admin_legacy_publish_check(12)['ready'])
        app.admin_publish_legacy(12, app.PublishRequest(confirmed=True))
        item = app.get_phone(12)
        self.assertEqual(item['ip'], 'IP53')
        self.assertIsNone(item['price'])
        self.assertNotIn('launchPrice', item)
        self.assertNotIn('releaseDate', item)
        self.assertTrue(item['suppressLegacyImage'])
        with self.assertRaises(HTTPException) as exc:
            app.admin_update_legacy_draft(12, edit)
        self.assertEqual(exc.exception.status_code, 409)

    def test_legacy_publication_requires_explicit_confirmation(self):
        with self.assertRaises(HTTPException) as exc:
            app.admin_publish_legacy(12, app.PublishRequest())
        self.assertEqual(exc.exception.status_code, 422)

    def test_restored_image_requires_current_complete_review(self):
        item = {'id': 12, 'name': '旧机', 'brand': 'B', 'suppressLegacyImage': True}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=12, name='旧机', brand='B', data=item))
        current = {'机型': [{'id': 12, 'address': 'images/a.png', 'sha256': 'abc', 'status': '本地文件存在'}]}
        review = {'address': 'images/a.png', 'sha256': 'abc', 'status': '已核实',
                  'model_match': True, 'color_match': True, 'full_body': True, 'no_watermark': True, 'loads': True}
        with patch.object(app, 'load_image_map', return_value={}), patch.object(app, 'audit_images', return_value=current):
            self.assertNotIn('verifiedImage', app.get_phone(12))
            with app.engine.begin() as connection:
                connection.execute(app.image_review.insert().values(phone_id=12, record=review))
            self.assertEqual(app.get_phone(12)['verifiedImage'], 'images/a.png')
            self.assertEqual(app.list_phones(keyword='', brand='')[0]['verifiedImage'], 'images/a.png')
            current['机型'][0]['sha256'] = 'changed'
            self.assertNotIn('verifiedImage', app.get_phone(12))
            current['机型'][0]['sha256'] = 'abc'
            current['机型'][0]['status'] = '本地文件缺失'
            self.assertNotIn('verifiedImage', app.get_phone(12))
            current['机型'][0]['status'] = '本地文件存在'
            with app.engine.begin() as connection:
                connection.execute(app.image_review.update().values(record={**review, 'status': '不合格'}))
            self.assertNotIn('verifiedImage', app.get_phone(12))

    def test_restored_image_fails_closed_when_index_unavailable(self):
        item = {'id': 12, 'name': '旧机', 'suppressLegacyImage': True, 'verifiedImage': 'images/stale.png'}
        with app.engine.connect() as connection, patch.object(app, 'load_image_map', side_effect=OSError):
            self.assertNotIn('verifiedImage', app.apply_reviewed_images(connection, [item])[0])

    def test_research_log_is_per_field_and_does_not_change_data(self):
        phone = {'id': 1, 'name': '测试机', 'ip': None}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        item = app.ResearchRequest(status='本次未找到公开资料', region='中国大陆',
                                   scope='官网规格页未列防护等级', checked_at='2026-01-01',
                                   source_url='https://example.com')
        app.admin_research_add('phones', 1, 'ip', item)
        self.assertEqual(app.admin_research_list('phones', 1, 'ip')[0]['scope'], item.scope)
        self.assertEqual(app.admin_research_list('phones', 1, 'battery'), [])
        self.assertEqual(app.get_phone(1), phone)
        with self.assertRaises(HTTPException):
            app.admin_research_list('phones', 1, 'invalid')
        with self.assertRaises(HTTPException):
            app.admin_research_add('phones', 999, 'ip', item)
        with self.assertRaises(ValidationError):
            app.ResearchRequest(status='本次未找到公开资料', region='  ', scope='官网', checked_at='2026-01-01')

    def test_date_and_price_research_appear_in_respective_inventories(self):
        phone = {'id': 1, 'name': '测试机'}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        date_search = app.ResearchRequest(status='本次未找到公开资料', region='中国大陆',
            scope='官网未列发布日期', checked_at='2026-01-01')
        price_search = app.ResearchRequest(status='资料冲突', region='中国大陆',
            scope='8GB+128GB 版本两个来源不一致', checked_at='2026-01-02')
        app.admin_research_add('phones', 1, 'releaseDate', date_search)
        app.admin_research_add('phones', 1, 'launchPrice', price_search)
        self.assertEqual(app.admin_research_list('phones', 1, 'releaseDate')[0]['scope'], date_search.scope)
        self.assertEqual(app.admin_release_gaps()['未完成机型'][0]['research']['status'], date_search.status)
        self.assertEqual(app.admin_price_gaps()['机型'][0]['research']['scope'], price_search.scope)
        self.assertEqual(app.get_phone(1), phone)

    def test_legacy_date_and_price_research_survive_publication(self):
        candidate = {'id': 12, 'name': '旧机', 'brand': 'B'}
        with patch.object(app, 'load_seed', return_value=[candidate]):
            app.admin_stage_legacy(12)
        search = app.ResearchRequest(status='查找中', region='中国大陆', scope='官网查询', checked_at='2026-01-01')
        for field in ('releaseDate', 'launchPrice'):
            app.admin_research_add('legacy-drafts', 12, field, search)
        app.admin_publish_legacy(12, app.PublishRequest(confirmed=True))
        self.assertEqual(app.admin_release_gaps()['未完成机型'][0]['research']['target'], 'legacy-drafts')
        self.assertEqual(app.admin_price_gaps()['机型'][0]['research']['target'], 'legacy-drafts')

    def test_gap_report_exposes_existing_value_and_field_evidence(self):
        evidence = {'status': '待核实', 'url': 'https://example.com/spec', 'region': '中国大陆', 'checkedAt': '2026-01-01'}
        phone = {'id': 1, 'name': '测试机', 'ip': 'IP68', 'specFieldSources': {'ip': evidence}}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        fields = app.admin_gaps()['未完成机型'][0]['fields']
        ip = next(x for x in fields if x['field'] == '防护等级')
        self.assertEqual(ip['status'], '待核实')
        self.assertEqual(ip['value'], 'IP68')
        self.assertEqual(ip['evidence'], evidence)
        self.assertIsNone(next(x for x in fields if x['field'] == '电池容量')['evidence'])
        self.assertEqual(app.get_phone(1), phone)

    def test_gap_report_shows_latest_research_without_changing_gap_status(self):
        phone = {'id': 1, 'name': '测试机', 'ip': None}
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=1, name='测试机', brand='测试', data=phone))
        first = app.ResearchRequest(status='查找中', region='中国大陆', scope='厂商官网', checked_at='2026-01-01')
        last = app.ResearchRequest(status='本次未找到公开资料', region='中国大陆', scope='官网规格页未列', checked_at='2026-01-02')
        app.admin_research_add('phones', 1, 'ip', first)
        app.admin_research_add('phones', 1, 'ip', last)
        fields = app.admin_gaps()['未完成机型'][0]['fields']
        ip = next(x for x in fields if x['field'] == '防护等级')
        self.assertEqual(ip['status'], '缺失')
        self.assertEqual(ip['research']['scope'], '官网规格页未列')
        self.assertIsNone(next(x for x in fields if x['field'] == '电池容量')['research'])

    def test_research_history_continues_after_legacy_publication(self):
        draft = {'id': 12, 'name': '待审核机', 'brand': 'B'}
        item = app.ResearchRequest(status='本次未找到公开资料', region='中国大陆',
                                   scope='官网未列', checked_at='2026-01-01')
        with patch.object(app, 'load_seed', return_value=[draft]):
            app.admin_stage_legacy(12)
        app.admin_research_add('legacy-drafts', 12, 'ip', item)
        app.admin_publish_legacy(12, app.PublishRequest(confirmed=True))
        history = app.admin_research_list('phones', 12, 'ip')
        self.assertEqual(history[0]['target'], 'legacy-drafts')
        ip = next(f for f in app.admin_gaps()['未完成机型'][0]['fields'] if f['field'] == '防护等级')
        self.assertEqual(ip['research']['scope'], '官网未列')
        with self.assertRaises(HTTPException) as exc:
            app.admin_research_add('legacy-drafts', 12, 'ip', item)
        self.assertEqual(exc.exception.status_code, 409)
        new = app.ResearchRequest(status='查找中', region='中国大陆', scope='查看厂商客服', checked_at='2026-01-02')
        app.admin_research_add('phones', 12, 'ip', new)
        self.assertEqual([r['target'] for r in app.admin_research_list('phones', 12, 'ip')], ['phones', 'legacy-drafts'])
        ip = next(f for f in app.admin_gaps()['未完成机型'][0]['fields'] if f['field'] == '防护等级')
        self.assertEqual(ip['research']['scope'], '查看厂商客服')

    def test_unrelated_draft_research_not_attached_to_published_phone(self):
        with app.engine.begin() as connection:
            connection.execute(app.phones.insert().values(id=12, name='已发布', brand='B', data={'id': 12, 'name': '已发布'}))
            connection.execute(app.legacy_drafts.insert().values(phone_id=12, name='不同的草稿', data={'id': 12}))
        item = app.ResearchRequest(status='查找中', region='中国大陆', scope='旧草稿', checked_at='2026-01-01')
        app.admin_research_add('legacy-drafts', 12, 'ip', item)
        self.assertEqual(app.admin_research_list('phones', 12, 'ip'), [])
        ip = next(f for f in app.admin_gaps()['未完成机型'][0]['fields'] if f['field'] == '防护等级')
        self.assertIsNone(ip['research'])


if __name__ == '__main__':
    unittest.main()
