import os
import json
import secrets
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import JSON, Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, func, select
from sqlalchemy.exc import IntegrityError
from seed import load_seed
from gaps import FIELDS, make_report, china_today, valid_source_url
from report_status import report_status
from editing import legacy_publish_check, prepare_legacy_for_publish, update_field
from images_audit import audit_images, load_image_map
from release_gaps import release_report
from price_gaps import price_report
from back_references import available_references, filter_references, inspect_reference_file
from online_vision import search_google, decode_image, allow_online_request
from official_check import check_source, validate_url
from scheduled_sources import read_state as read_official_check_state, official_records_page, OUTCOMES, FIELD_CHANGES

engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
RESEARCH_FIELDS = {**FIELDS, 'releaseDate': '发布日期', 'launchPrice': '历史价格'}
metadata = MetaData()
phones = Table('phones', metadata,
    Column('id', Integer, primary_key=True),
    Column('name', String(255), nullable=False, index=True),
    Column('brand', String(128), nullable=False, index=True),
    Column('data', JSON, nullable=False))
feedback = Table('feedback', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('type', String(32), nullable=False),
    Column('text', Text, nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
feedback_request = Table('feedback_request', metadata,
    Column('request_id', String(36), primary_key=True),
    Column('feedback_id', Integer, nullable=True))
feedback_state = Table('feedback_state', metadata,
    Column('feedback_id', Integer, primary_key=True),
    Column('status', String(32), nullable=False),
    Column('updated_at', DateTime, nullable=False, server_default=func.current_timestamp()))
image_review = Table('image_review', metadata,
    Column('phone_id', Integer, primary_key=True),
    Column('record', JSON, nullable=False),
    Column('updated_at', DateTime, nullable=False, server_default=func.current_timestamp()))
image_review_log = Table('image_review_log', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('phone_id', Integer, nullable=False, index=True),
    Column('before', JSON), Column('after', JSON, nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
back_reference = Table('back_reference', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('phone_id', Integer, nullable=False, index=True),
    Column('sha256', String(64), nullable=False, unique=True),
    Column('record', JSON, nullable=False),
    Column('active', Integer, nullable=False, default=1),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
back_reference_log = Table('back_reference_log', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('reference_id', Integer, nullable=False, index=True),
    Column('before', JSON), Column('after', JSON, nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
legacy_drafts = Table('legacy_drafts', metadata,
    Column('phone_id', Integer, primary_key=True),
    Column('name', String(255), nullable=False),
    Column('data', JSON, nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
legacy_draft_log = Table('legacy_draft_log', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('phone_id', Integer, nullable=False, index=True),
    Column('field', String(32), nullable=False),
    Column('before', JSON, nullable=False), Column('after', JSON, nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
legacy_publications = Table('legacy_publications', metadata,
    Column('phone_id', Integer, primary_key=True),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
edit_log = Table('edit_log', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('phone_id', Integer, nullable=False, index=True),
    Column('field', String(32), nullable=False),
    Column('before', JSON, nullable=False),
    Column('after', JSON, nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))
research_log = Table('research_log', metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('target', String(32), nullable=False),
    Column('phone_id', Integer, nullable=False, index=True),
    Column('field', String(32), nullable=False),
    Column('record', JSON, nullable=False),
    Column('created_at', DateTime, nullable=False, server_default=func.current_timestamp()))


class FieldEdit(BaseModel):
    field: str
    value: str
    expected_value: str | None = None
    expected_evidence: dict | None
    evidence: dict


class PublishRequest(BaseModel):
    confirmed: bool = False


class BackReferenceCreate(BaseModel):
    address: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(min_length=64, max_length=64)
    region: str = Field(min_length=1, max_length=200)
    color: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=2048)
    source_status: str
    checked_at: date
    model_match: bool = False
    color_match: bool = False
    back_only: bool = False
    full_body: bool = False
    no_watermark: bool = False
    loads: bool = False

    @field_validator('region', 'color')
    @classmethod
    def valid_text(cls, value):
        if not value.strip():
            raise ValueError('地区和配色不能为空')
        return value.strip()

    @field_validator('source_status')
    @classmethod
    def valid_source_status(cls, value):
        if value not in ('厂商官方核实', '可靠渠道核实'):
            raise ValueError('请选择来源可信状态')
        return value

    @field_validator('source_url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip()
        if not valid_source_url(value):
            raise ValueError('来源必须是有效的 HTTP 或 HTTPS 链接')
        return value

    @field_validator('checked_at')
    @classmethod
    def valid_date(cls, value):
        if value > china_today():
            raise ValueError('核对日期不能晚于今天')
        return value


class BackReferenceState(BaseModel):
    active: bool
    expected_active: bool


class ReleaseEdit(BaseModel):
    value: date
    expected_value: str | None
    expected_evidence: dict | None
    expected_label: str | None = None
    status: str
    region: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    checked_at: date

    @field_validator('status')
    @classmethod
    def valid_status(cls, value):
        if value not in ('厂商官方核实', '可靠渠道核实'):
            raise ValueError('发布日期须由官方或可靠渠道核实')
        return value

    @field_validator('region')
    @classmethod
    def valid_region(cls, value):
        if not value.strip():
            raise ValueError('地区版本不能为空')
        return value.strip()

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip()
        if not valid_source_url(value):
            raise ValueError('来源必须是有效的 HTTP 或 HTTPS 链接')
        return value

    @field_validator('checked_at')
    @classmethod
    def valid_date(cls, value):
        if value > china_today():
            raise ValueError('核对日期不能晚于今天')
        return value


class SalesStatusEdit(BaseModel):
    value: str
    expected_value: str | None
    expected_evidence: dict | None
    region: str = Field(min_length=1, max_length=200)
    channel: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    checked_at: date

    @field_validator('value')
    @classmethod
    def valid_value(cls, value):
        if value not in ('销售状态待核实', '在售', '停售'):
            raise ValueError('销售状态无效')
        return value

    @field_validator('region', 'channel')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('地区版本和渠道不能为空')
        return value.strip()

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip()
        if not valid_source_url(value):
            raise ValueError('来源必须是有效的 HTTP 或 HTTPS 链接')
        return value

    @field_validator('checked_at')
    @classmethod
    def valid_checked_at(cls, value):
        if value > china_today():
            raise ValueError('核对日期不能晚于今天')
        return value


class MarketPriceEdit(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str
    variant: str = Field(min_length=1, max_length=200)
    region: str = Field(min_length=1, max_length=200)
    channel: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    observed_at: datetime
    expected_quote: dict | None

    @field_validator('currency')
    @classmethod
    def currency_valid(cls, value):
        if value not in ('CNY', 'HKD', 'AED'): raise ValueError('币种无效')
        return value

    @field_validator('variant', 'region', 'channel')
    @classmethod
    def clean_text(cls, value):
        if not value.strip(): raise ValueError('版本、地区和渠道不能为空')
        return value.strip()

    @field_validator('url')
    @classmethod
    def source_url(cls, value):
        value=value.strip(); parsed=urlparse(value)
        if not valid_source_url(value) or parsed.scheme != 'https':
            raise ValueError('来源必须是有效的 HTTPS 地址')
        return value

    @field_validator('observed_at')
    @classmethod
    def observed_time(cls, value):
        if value.tzinfo is None or value.utcoffset() is None: raise ValueError('采集时间必须含时区')
        value=value.astimezone(timezone.utc)
        if value > datetime.now(timezone.utc): raise ValueError('采集时间不能晚于现在')
        return value


class MarketQuotesEdit(MarketPriceEdit):
    expected_quotes: list | None
    slot: str | None = None

    @field_validator('slot')
    @classmethod
    def valid_slot(cls, value):
        if value is not None and value != 'legacy' and (not value.isascii() or not value.isdigit() or len(value)>3):
            raise ValueError('报价位置无效')
        return value


def market_quote_records(phone):
    records=[]
    if phone.get('marketQuote') is not None: records.append(phone['marketQuote'])
    quotes=phone.get('marketQuotes')
    if quotes is not None:
        if not isinstance(quotes,list) or len(quotes)>20: return records+[None]
        records.extend(quotes)
    return records


def classify_one_market_quote(phone, quote, now=None):
    state=str(phone.get('status') or '')
    if any(word in state for word in ('停售','停产','下架')): return '停售隐藏'
    if not isinstance(quote, dict): return '未录入' if quote is None else '记录无效'
    if state != '在售': return '销售状态待核实'
    sales=phone.get('salesStatusSource')
    if not isinstance(sales, dict) or not all(isinstance(sales.get(k),str) and sales[k].strip() and sales[k].strip()==str(quote.get(k,'')).strip() for k in ('region','channel')):
        return '地区或渠道不匹配'
    try:
        observed=datetime.fromisoformat(quote['observedAt'])
        if observed.tzinfo is None or observed.utcoffset() is None: return '记录无效'
        now=now or datetime.now(timezone.utc); age=now-observed.astimezone(timezone.utc)
        if age < timedelta(0): return '记录无效'
        if not all(isinstance(quote.get(k),str) and quote[k].strip() for k in ('amount','currency','variant','region','channel','url')): return '记录无效'
        parsed=urlparse(quote['url']); value=Decimal(quote['amount'])
        if parsed.scheme!='https' or not valid_source_url(quote['url']) or not value.is_finite() or value<=0 or quote['currency'] not in ('CNY','HKD','AED'): return '记录无效'
        return '已过期' if age >= timedelta(hours=24) else '可展示'
    except (ValueError, TypeError, KeyError, ArithmeticError):
        return '记录无效'


def classify_market_quote(phone, now=None):
    records=market_quote_records(phone)
    if not records: return classify_one_market_quote(phone,None,now)
    statuses=[classify_one_market_quote(phone,record,now) for record in records]
    for state in ('可展示','停售隐藏','销售状态待核实','地区或渠道不匹配','记录无效','已过期'):
        if state in statuses: return state
    return '记录无效'


def public_market_quotes(phone, now=None):
    return [record for record in market_quote_records(phone) if classify_one_market_quote(phone,record,now)=='可展示']


def public_market_quote(phone, now=None):
    records=public_market_quotes(phone,now)
    return records[0] if records else None


def market_quote_report(items, now=None):
    now=now or datetime.now(timezone.utc);rows=[];counts=Counter();missing=0
    for item in items:
        state=classify_market_quote(item,now);counts[state]+=1
        records=market_quote_records(item);missing+=not records
        details=next((r for r in records if isinstance(r,dict)),{})
        rows.append({'id':item['id'],'name':item.get('name',''),'status':state,
                     'sales_status':item.get('status') or '未记录',
                     'variant':details.get('variant'),'region':details.get('region'),
                     'channel':details.get('channel'),'observed_at':details.get('observedAt'),
                     'record_count':len(records),'record_states':[classify_one_market_quote(item,r,now) for r in records]})
    return {'机型数':len(items),'未录入快照':missing,'状态统计':dict(counts),'机型':rows,
            '说明':'只检查已保存的手工快照和展示条件；不联网核实价格、库存或销售状态。'}


def filter_public_prices(items):
    result=[]
    for item in items:
        cleaned={k:v for k,v in item.items() if k not in ('marketQuote','marketQuotes')}
        quotes=public_market_quotes(item)
        if quotes: cleaned['marketQuote']=quotes[0];cleaned['marketQuotes']=quotes
        result.append(cleaned)
    return result


class HistoricalPriceAdd(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=10, decimal_places=2)
    currency: str
    variant: str = Field(min_length=1, max_length=200)
    type: str
    region: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2048)
    checked_at: date
    status: str
    expected_primary: dict | None
    expected_variants: list | None

    @field_validator('currency')
    @classmethod
    def currency_valid(cls, value):
        if value not in ('CNY', 'HKD', 'AED'):
            raise ValueError('币种无效')
        return value

    @field_validator('type')
    @classmethod
    def price_type_valid(cls, value):
        if value not in ('历史发布价格', '历史官方建议零售价'):
            raise ValueError('仅支持历史发布价格或历史官方建议零售价')
        return value

    @field_validator('status')
    @classmethod
    def confidence_valid(cls, value):
        if value not in ('厂商官方核实', '可靠渠道核实'):
            raise ValueError('请确认来源可信状态')
        return value

    @field_validator('variant', 'region')
    @classmethod
    def clean_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('版本和地区不能为空')
        return value

    @field_validator('url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip()
        if not valid_source_url(value):
            raise ValueError('来源必须是有效的 HTTP 或 HTTPS 链接')
        return value

    @field_validator('checked_at')
    @classmethod
    def valid_date(cls, value):
        if value > china_today():
            raise ValueError('核对日期不能晚于今天')
        return value


class ResearchRequest(BaseModel):
    status: str
    region: str = Field(min_length=1, max_length=200)
    scope: str = Field(min_length=1, max_length=1000)
    checked_at: date
    source_url: str = Field(default='', max_length=2048)

    @field_validator('status')
    @classmethod
    def valid_status(cls, value):
        if value not in ('查找中', '本次未找到公开资料', '资料冲突'):
            raise ValueError('无效的查找状态')
        return value

    @field_validator('region', 'scope')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('请填写地区版本和查找范围')
        return value.strip()

    @field_validator('source_url')
    @classmethod
    def valid_source(cls, value):
        value = value.strip()
        if value and not valid_source_url(value):
            raise ValueError('来源必须是 HTTP 或 HTTPS 链接')
        return value

    @field_validator('checked_at')
    @classmethod
    def valid_date(cls, value):
        if value > china_today():
            raise ValueError('查找日期不能晚于今天')
        return value


class ImageReviewRequest(BaseModel):
    address: str = Field(min_length=1, max_length=2048)
    sha256: str | None = None
    status: str
    region: str = Field(min_length=1, max_length=200)
    color: str = Field(min_length=1, max_length=100)
    source_url: str = Field(min_length=1, max_length=2048)
    checked_at: date
    model_match: bool = False
    color_match: bool = False
    full_body: bool = False
    no_watermark: bool = False
    loads: bool = False

    @field_validator('status')
    @classmethod
    def valid_status(cls, value):
        if value not in ('已核实', '待核实', '不合格'):
            raise ValueError('无效的核查状态')
        return value

    @field_validator('region', 'color')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('地区和配色不能为空')
        return value.strip()

    @field_validator('source_url')
    @classmethod
    def source_valid(cls, value):
        if not valid_source_url(value):
            raise ValueError('来源必须是有效的 HTTP 或 HTTPS 链接')
        return value

    @field_validator('checked_at')
    @classmethod
    def date_valid(cls, value):
        if value > china_today():
            raise ValueError('核对日期不能晚于今天')
        return value


class FeedbackRequest(BaseModel):
    type: str
    text: str = Field(max_length=2000)
    request_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

    @field_validator('type')
    @classmethod
    def valid_type(cls, value):
        if value not in ('问题反馈', '功能建议', '其他'):
            raise ValueError('无效的反馈类型')
        return value

    @field_validator('text')
    @classmethod
    def valid_text(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('反馈内容不能为空')
        return value


class FeedbackStatusRequest(BaseModel):
    status: str

    @field_validator('status')
    @classmethod
    def valid_status(cls, value):
        if value not in ('待处理', '处理中', '已处理'):
            raise ValueError('无效的处理状态')
        return value

def import_initial_data():
    data = load_seed('/seed/index.html')
    with engine.begin() as connection:
        if connection.scalar(select(func.count()).select_from(phones)) == 0:
            connection.execute(phones.insert(), [{'id': p['id'], 'name': p['name'], 'brand': p['brand'], 'data': p} for p in data])


@asynccontextmanager
async def lifespan(app):
    metadata.create_all(engine)
    import_initial_data()
    yield
    engine.dispose()


app = FastAPI(title='手机信息查询接口', lifespan=lifespan)


def require_admin(authorization: str = Header(default='')):
    expected = os.environ.get('ADMIN_TOKEN', '')
    supplied = authorization.removeprefix('Bearer ') if authorization.startswith('Bearer ') else ''
    if not expected or not supplied or not secrets.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail='管理口令无效')


@app.get('/api/health')
def health():
    with engine.connect() as connection:
        count = connection.scalar(select(func.count()).select_from(phones))
    return {'status': 'ok', 'phones': count}


@app.get('/api/phones')
def list_phones(keyword: str = Query('', max_length=100), brand: str = Query('', max_length=100)):
    query = select(phones.c.data).order_by(phones.c.id)
    if keyword:
        query = query.where(phones.c.name.contains(keyword, autoescape=True))
    if brand:
        query = query.where(phones.c.brand == brand)
    with engine.connect() as connection:
        items = [row[0] for row in connection.execute(query)]
        return filter_public_prices(apply_reviewed_images(connection, items))


def apply_reviewed_images(connection, items):
    """For restored legacy records, expose only a current, manually reviewed image."""
    items = [{k: v for k, v in p.items() if k != 'verifiedImage'} for p in items]
    hidden = [p for p in items if p.get('suppressLegacyImage')]
    if not hidden:
        return items
    ids = [p['id'] for p in hidden]
    reviews = {r.phone_id: r.record for r in connection.execute(
        select(image_review).where(image_review.c.phone_id.in_(ids)))}
    try:
        rows = audit_images(hidden, load_image_map('/seed/index.html'), '/images')['机型']
    except (OSError, ValueError):
        return items  # Fail closed if the image index cannot be read.
    approved = {}
    for row in rows:
        review = reviews.get(row['id']) or {}
        if (review.get('status') == '已核实'
                and all(review.get(k) is True for k in ('model_match', 'color_match', 'full_body', 'no_watermark', 'loads'))
                and row['status'] in ('本地文件存在', '外链未检查加载')
                and review.get('address') == row['address']
                and review.get('sha256') == row.get('sha256')):
            approved[row['id']] = row['address']
    return [{**p, 'verifiedImage': approved[p['id']]} if p.get('suppressLegacyImage') and p['id'] in approved else p
            for p in items]


@app.get('/api/phones/{phone_id}')
def get_phone(phone_id: int):
    with engine.connect() as connection:
        item = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id))
        if item is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        return filter_public_prices(apply_reviewed_images(connection, [item]))[0]


@app.get('/api/brands')
def list_brands():
    with engine.connect() as connection:
        return list(connection.scalars(select(phones.c.brand).distinct().order_by(phones.c.brand)))


class OnlineVisionRequest(BaseModel):
    image: str = Field(min_length=1, max_length=2796208)
    consent: bool = Field(strict=True)


@app.get('/api/recognition/online-status')
def online_vision_status():
    enabled = os.environ.get('ONLINE_VISION_ENABLED') == '1' and bool(os.environ.get('GOOGLE_VISION_API_KEY'))
    return {'enabled': enabled, 'provider': 'Google Cloud Vision' if enabled else None}


@app.post('/api/recognition/online')
def online_vision(request: OnlineVisionRequest):
    if not request.consent:
        raise HTTPException(status_code=400, detail='请先同意将图片发送至在线识图服务')
    if not online_vision_status()['enabled']:
        raise HTTPException(status_code=503, detail='在线识图尚未配置')
    try:
        decode_image(request.image)
        if not allow_online_request():
            raise HTTPException(status_code=429, detail='请求过于频繁，请稍后重试')
        return search_google(request.image, os.environ.get('GOOGLE_VISION_API_KEY', ''))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get('/api/recognition/references')
def recognition_references():
    with engine.connect() as connection:
        items = list(connection.scalars(select(phones.c.data)))
        manual = list(connection.scalars(select(back_reference.c.record).where(back_reference.c.active == 1)))
    try:
        curated = available_references('/seed/back-references.json', '/images', items)
    except (OSError, ValueError):
        curated = []
    return curated + filter_references(manual, '/images', items)


@app.get('/api/admin/back-references/inspect', dependencies=[Depends(require_admin)])
def admin_inspect_back_reference(address: str = Query(..., min_length=1, max_length=2048)):
    try:
        digest = inspect_reference_file('/images', address)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {'address': address, 'sha256': digest}


@app.get('/api/admin/back-references', dependencies=[Depends(require_admin)])
def admin_back_references():
    with engine.connect() as connection:
        items = list(connection.scalars(select(phones.c.data)))
        rows = list(connection.execute(select(back_reference).order_by(back_reference.c.id.desc())))
    result = []
    for row in rows:
        usable = bool(filter_references([row.record], '/images', items))
        result.append({'id': row.id, 'active': bool(row.active), 'usable': usable, **row.record})
    return result


@app.post('/api/admin/back-references/{phone_id}', status_code=201, dependencies=[Depends(require_admin)])
def admin_add_back_reference(phone_id: int, item: BackReferenceCreate):
    if not all((item.model_match, item.color_match, item.back_only, item.full_body, item.no_watermark, item.loads)):
        raise HTTPException(status_code=422, detail='请逐项确认型号、配色、背面、完整机身、无水印和加载')
    try:
        digest = inspect_reference_file('/images', item.address)
        if digest != item.sha256:
            raise HTTPException(status_code=409, detail='图片已变化，请重新检查')
        with open('/seed/back-references.json', encoding='utf-8') as file:
            curated = json.load(file)
        if curated.get('version') != 1 or not isinstance(curated.get('references'), list):
            raise ValueError('内置参考图清单格式无效')
        if any(isinstance(row, dict) and row.get('sha256') == digest for row in curated['references']):
            raise HTTPException(status_code=409, detail='该图片已在内置参考库中')
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        with engine.begin() as connection:
            phone = connection.execute(select(phones.c.id, phones.c.name).where(
                phones.c.id == phone_id).with_for_update()).first()
            if phone is None:
                raise HTTPException(status_code=404, detail='机型不存在')
            record = {'phoneId': phone.id, 'phoneName': phone.name, 'image': item.address, 'sha256': digest,
                      'region': item.region, 'color': item.color, 'source': item.source_url, 'sourceStatus': item.source_status,
                      'checkedAt': item.checked_at.isoformat(),
                      'checks': {'model_match': item.model_match, 'color_match': item.color_match,
                                 'back_only': item.back_only, 'full_body': item.full_body,
                                 'no_watermark': item.no_watermark, 'loads': item.loads}}
            result = connection.execute(back_reference.insert().values(phone_id=phone_id, sha256=digest,
                                                                        record=record, active=1))
            reference_id = result.inserted_primary_key[0]
            connection.execute(back_reference_log.insert().values(reference_id=reference_id,
                                                                  before=None, after={'active': True, 'record': record}))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail='该图片已有参考记录，请检查或重新启用') from exc
    return {'id': reference_id, 'active': True}


@app.put('/api/admin/back-references/records/{reference_id}/state', dependencies=[Depends(require_admin)])
def admin_set_back_reference_state(reference_id: int, item: BackReferenceState):
    with engine.begin() as connection:
        row = connection.execute(select(back_reference).where(back_reference.c.id == reference_id).with_for_update()).first()
        if row is None:
            raise HTTPException(status_code=404, detail='参考记录不存在')
        if bool(row.active) != item.expected_active:
            raise HTTPException(status_code=409, detail='状态已改变，请重新读取')
        if item.active:
            phone = connection.scalar(select(phones.c.data).where(phones.c.id == row.phone_id))
            if phone is None or not filter_references([row.record], '/images', [phone]):
                raise HTTPException(status_code=409, detail='机型或图片已变化，不能启用')
        connection.execute(back_reference.update().where(back_reference.c.id == reference_id).values(active=int(item.active)))
        connection.execute(back_reference_log.insert().values(reference_id=reference_id,
            before={'active': bool(row.active)}, after={'active': item.active}))
    return {'id': reference_id, 'active': item.active}


@app.post('/api/feedback', status_code=201)
def submit_feedback(item: FeedbackRequest):
    if not item.request_id:
        with engine.begin() as connection:
            result = connection.execute(feedback.insert().values(type=item.type, text=item.text))
        return {'id': result.inserted_primary_key[0]}
    try:
        with engine.begin() as connection:
            connection.execute(feedback_request.insert().values(request_id=item.request_id))
            result = connection.execute(feedback.insert().values(type=item.type, text=item.text))
            feedback_id = result.inserted_primary_key[0]
            connection.execute(feedback_request.update().where(feedback_request.c.request_id == item.request_id).values(feedback_id=feedback_id))
        return {'id': feedback_id}
    except IntegrityError:
        with engine.connect() as connection:
            row = connection.execute(select(feedback.c.id, feedback.c.type, feedback.c.text).join(feedback_request, feedback.c.id == feedback_request.c.feedback_id).where(feedback_request.c.request_id == item.request_id)).first()
        if not row:
            raise HTTPException(status_code=409, detail='反馈提交状态未确认，请稍后重试')
        if row.type != item.type or row.text != item.text:
            raise HTTPException(status_code=409, detail='反馈编号已用于其他内容')
        return {'id': row.id}


@app.get('/api/admin/market-quote-gaps', dependencies=[Depends(require_admin)])
def admin_market_quote_gaps():
    with engine.connect() as connection:
        items = list(connection.scalars(select(phones.c.data).order_by(phones.c.id)))
    return market_quote_report(items)


@app.get('/api/admin/scheduled-official', dependencies=[Depends(require_admin)])
def admin_scheduled_official(before: str | None = Query(None, min_length=64, max_length=64, pattern='^[0-9a-f]{64}$'),
                             limit: int = Query(50, ge=1, le=100), keyword: str = Query('', max_length=100),
                             outcome: str = Query('', max_length=30), field_change: str = Query('', max_length=30)):
    if outcome and outcome not in OUTCOMES:
        raise HTTPException(status_code=422, detail='检查结果筛选无效')
    if field_change and field_change not in FIELD_CHANGES:
        raise HTTPException(status_code=422, detail='字段比较筛选无效')
    try:
        state = read_official_check_state('/reports')
        page = official_records_page(state['records'], before, limit, keyword, outcome, field_change)
    except LookupError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError):
        raise HTTPException(status_code=503, detail='自动检查记录或筛选条件无效')
    return {'last_attempt': state.get('last_attempt'), **page,
            'notice': '仅检查已登记官网的页面文字，不代表型号、地区或字段已核实；不会自动更新数据。'}


@app.get('/api/admin/scheduled-report', dependencies=[Depends(require_admin)])
def admin_scheduled_report():
    return report_status('/reports')


@app.get('/api/admin/gaps', dependencies=[Depends(require_admin)])
def admin_gaps():
    with engine.connect() as connection:
        rows = list(connection.scalars(select(phones.c.data).order_by(phones.c.id)))
        latest = latest_research(connection, list(FIELDS))
    report = make_report(rows)
    keys = {label: key for key, label in FIELDS.items()}
    by_id = {phone.get('id'): phone for phone in rows}
    for phone in report['未完成机型']:
        original = by_id.get(phone['id'], {})
        sources = original.get('specFieldSources')
        sources = sources if isinstance(sources, dict) else {}
        for field in phone['fields']:
            key = keys[field['field']]
            field['research'] = latest.get((phone['id'], key))
            field['value'] = original.get(key)
            evidence = sources.get(key)
            field['evidence'] = evidence if isinstance(evidence, dict) else None
    return report


def latest_research(connection, fields):
    published = set(connection.scalars(select(legacy_publications.c.phone_id)))
    records = connection.execute(select(research_log).where(
        research_log.c.field.in_(fields)).order_by(research_log.c.id.desc()))
    latest = {}
    for row in records:
        if row.target == 'phones' or (row.target == 'legacy-drafts' and row.phone_id in published):
            latest.setdefault((row.phone_id, row.field), {**row.record, 'target': row.target})
    return latest


@app.get('/api/admin/release-gaps', dependencies=[Depends(require_admin)])
def admin_release_gaps():
    with engine.connect() as connection:
        rows = list(connection.scalars(select(phones.c.data).order_by(phones.c.id)))
        latest = latest_research(connection, ['releaseDate'])
    report = release_report(rows)
    for item in report['未完成机型']:
        item['research'] = latest.get((item['id'], 'releaseDate'))
    return report


@app.get('/api/admin/price-gaps', dependencies=[Depends(require_admin)])
def admin_price_gaps():
    with engine.connect() as connection:
        rows = list(connection.scalars(select(phones.c.data).order_by(phones.c.id)))
        latest = latest_research(connection, ['launchPrice'])
    report = price_report(rows)
    for item in report['机型']:
        item['research'] = latest.get((item['id'], 'launchPrice'))
    return report


@app.get('/api/admin/images', dependencies=[Depends(require_admin)])
def admin_images():
    with engine.connect() as connection:
        rows = list(connection.scalars(select(phones.c.data).order_by(phones.c.id)))
        reviews = {r.phone_id: r.record for r in connection.execute(select(image_review))}
    report = audit_images(rows, load_image_map('/seed/index.html'), '/images')
    for item in report['机型']:
        record = reviews.get(item['id'])
        if record:
            item['review'] = record
            item['visual_status'] = (record['status'] if record['address'] == item['address'] and
                                     record.get('sha256') == item.get('sha256') else '图片已变化，待重新核实')
    report['说明'] = '仅盘点原型主图；人工记录不自动确认外链持续可加载，图片地址或本地文件变化后需重新核实。'
    return report


@app.put('/api/admin/images/{phone_id}/review', dependencies=[Depends(require_admin)])
def admin_image_review(phone_id: int, review: ImageReviewRequest):
    if review.status == '已核实' and not all((review.model_match, review.color_match, review.full_body,
                                           review.no_watermark, review.loads)):
        raise HTTPException(status_code=422, detail='已核实需要逐项确认型号、配色、完整机身、无水印和加载')
    with engine.begin() as connection:
        phone = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id).with_for_update())
        if phone is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        current = audit_images([phone], load_image_map('/seed/index.html'), '/images')['机型'][0]
        if current['address'] != review.address or current.get('sha256') != review.sha256:
            raise HTTPException(status_code=409, detail='图片已变化，请重新盘点')
        if review.status == '已核实' and current['status'] not in ('本地文件存在', '外链未检查加载'):
            raise HTTPException(status_code=422, detail='图片地址无效或本地文件不可读取')
        old = connection.scalar(select(image_review.c.record).where(image_review.c.phone_id == phone_id))
        record = review.model_dump(mode='json')
        if old is None:
            connection.execute(image_review.insert().values(phone_id=phone_id, record=record))
        else:
            connection.execute(image_review.update().where(image_review.c.phone_id == phone_id)
                               .values(record=record, updated_at=func.current_timestamp()))
        connection.execute(image_review_log.insert().values(phone_id=phone_id, before=old, after=record))
    return {'id': phone_id, 'status': review.status}


@app.get('/api/admin/feedback', dependencies=[Depends(require_admin)])
def admin_feedback(limit: int = Query(100, ge=1, le=500), before_id: int | None = None):
    if before_id is not None and before_id < 1:
        raise HTTPException(status_code=422, detail='分页位置无效')
    statement = select(feedback, feedback_state.c.status).select_from(
        feedback.outerjoin(feedback_state, feedback.c.id == feedback_state.c.feedback_id)
    )
    if before_id is not None:
        statement = statement.where(feedback.c.id < before_id)
    with engine.connect() as connection:
        rows = connection.execute(statement.order_by(feedback.c.id.desc()).limit(limit))
        return [{'id': row.id, 'type': row.type, 'text': row.text,
                 'status': row.status or '待处理',
                 'created_at': row.created_at.isoformat(sep=' ') if row.created_at else None}
                for row in rows]


@app.put('/api/admin/feedback/{feedback_id}/status', dependencies=[Depends(require_admin)])
def admin_feedback_status(feedback_id: int, item: FeedbackStatusRequest):
    with engine.begin() as connection:
        existing = connection.scalar(select(feedback.c.id).where(feedback.c.id == feedback_id).with_for_update())
        if existing is None:
            raise HTTPException(status_code=404, detail='反馈不存在')
        state = connection.scalar(select(feedback_state.c.feedback_id).where(feedback_state.c.feedback_id == feedback_id))
        if state is None:
            connection.execute(feedback_state.insert().values(feedback_id=feedback_id, status=item.status))
        else:
            connection.execute(feedback_state.update().where(feedback_state.c.feedback_id == feedback_id)
                               .values(status=item.status, updated_at=func.current_timestamp()))
    return {'id': feedback_id, 'status': item.status}


@app.get('/api/admin/phones', dependencies=[Depends(require_admin)])
def admin_phone_search(keyword: str = Query('', max_length=100), limit: int = Query(30, ge=1, le=100)):
    query = select(phones.c.id, phones.c.name, phones.c.brand).order_by(phones.c.name).limit(limit)
    keyword = keyword.strip()
    if keyword:
        query = query.where(phones.c.name.contains(keyword, autoescape=True))
    with engine.connect() as connection:
        return [{'id': row.id, 'name': row.name, 'brand': row.brand} for row in connection.execute(query)]


def research_phone_exists(connection, target, phone_id, field):
    if target not in ('phones', 'legacy-drafts') or field not in RESEARCH_FIELDS:
        raise HTTPException(status_code=422, detail='机型类型或字段无效')
    table, column = (phones, phones.c.id) if target == 'phones' else (legacy_drafts, legacy_drafts.c.phone_id)
    if connection.scalar(select(column).select_from(table).where(column == phone_id)) is None:
        raise HTTPException(status_code=404, detail='机型不存在')


@app.get('/api/admin/research/{target}/{phone_id}/{field}', dependencies=[Depends(require_admin)])
def admin_research_list(target: str, phone_id: int, field: str):
    with engine.connect() as connection:
        research_phone_exists(connection, target, phone_id, field)
        targets = [target]
        if target == 'phones' and connection.scalar(select(legacy_publications.c.phone_id).where(
                legacy_publications.c.phone_id == phone_id)) is not None:
            targets.append('legacy-drafts')
        rows = connection.execute(select(research_log).where(
            research_log.c.target.in_(targets), research_log.c.phone_id == phone_id,
            research_log.c.field == field).order_by(research_log.c.id.desc()).limit(100))
        return [{'id': row.id, **row.record, 'target': row.target} for row in rows]


@app.post('/api/admin/research/{target}/{phone_id}/{field}', status_code=201,
          dependencies=[Depends(require_admin)])
def admin_research_add(target: str, phone_id: int, field: str, item: ResearchRequest):
    with engine.begin() as connection:
        research_phone_exists(connection, target, phone_id, field)
        if target == 'legacy-drafts':
            connection.scalar(select(legacy_drafts.c.phone_id).where(
                legacy_drafts.c.phone_id == phone_id).with_for_update())
            if connection.scalar(select(legacy_publications.c.phone_id).where(
                    legacy_publications.c.phone_id == phone_id).with_for_update()) is not None:
                raise HTTPException(status_code=409, detail='机型已发布，请在已发布机型中记录')
        result = connection.execute(research_log.insert().values(
            target=target, phone_id=phone_id, field=field, record=item.model_dump(mode='json')))
    return {'id': result.inserted_primary_key[0]}


@app.get('/api/admin/legacy-candidates', dependencies=[Depends(require_admin)])
def admin_legacy_candidates():
    legacy = load_seed('/seed/legacy.html')
    with engine.connect() as connection:
        rows = connection.execute(select(phones.c.id, phones.c.name))
        present = {row.id: row.name for row in rows}
        staged = set(connection.scalars(select(legacy_drafts.c.phone_id)))
    return [{'id': p['id'], 'name': p['name'], 'brand': p['brand'],
             'source': p.get('source'), 'region': p.get('specRegion'),
             'fields': {key: p.get(key) for key in ('battery', 'charge', 'screen', 'chip', 'camera',
                                                      'front', 'weight', 'ip', 'system', 'storage', 'updates')},
             'sources': p.get('specFieldSources') or {},
             'staged': p['id'] in staged,
             'warning': '旧版资料，尚未与后续核查记录核对；不能视为已验证。'}
            for p in legacy if p['id'] not in present]


@app.post('/api/admin/legacy-candidates/{phone_id}/stage', status_code=201,
          dependencies=[Depends(require_admin)])
def admin_stage_legacy(phone_id: int):
    candidate = next((p for p in load_seed('/seed/legacy.html') if p['id'] == phone_id), None)
    if candidate is None:
        raise HTTPException(status_code=404, detail='旧版机型不存在')
    try:
        with engine.begin() as connection:
            existing = connection.execute(select(phones.c.id, phones.c.name).where(
                (phones.c.id == phone_id) | (phones.c.name == candidate['name'])).with_for_update()).first()
            if existing:
                raise HTTPException(status_code=409, detail='数据库已有相同 ID 或名称，请先核对')
            if connection.scalar(select(legacy_drafts.c.phone_id).where(legacy_drafts.c.phone_id == phone_id)) is not None:
                raise HTTPException(status_code=409, detail='该机型已在待审核区')
            connection.execute(legacy_drafts.insert().values(phone_id=phone_id, name=candidate['name'], data=candidate))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail='该机型已在待审核区，请刷新列表') from exc
    return {'id': phone_id, 'name': candidate['name'], 'status': '待审核'}


@app.get('/api/admin/legacy-drafts', dependencies=[Depends(require_admin)])
def admin_legacy_drafts(keyword: str = Query('', max_length=100)):
    query = select(legacy_drafts.c.phone_id, legacy_drafts.c.name, legacy_drafts.c.data).where(
        ~legacy_drafts.c.phone_id.in_(select(legacy_publications.c.phone_id))).order_by(legacy_drafts.c.name)
    keyword = keyword.strip()
    if keyword:
        query = query.where(legacy_drafts.c.name.contains(keyword, autoescape=True))
    with engine.connect() as connection:
        rows = list(connection.execute(query))
    result = []
    for row in rows:
        check = legacy_publish_check(row.data)
        result.append({'id': row.phone_id, 'name': row.name, 'brand': row.data.get('brand', ''),
                       'ready': check['ready'], 'blocked_count': len(check['blocked']),
                       'missing_count': len(check['missing'])})
    return result


@app.get('/api/admin/legacy-drafts/{phone_id}', dependencies=[Depends(require_admin)])
def admin_legacy_draft(phone_id: int):
    with engine.connect() as connection:
        draft = connection.scalar(select(legacy_drafts.c.data).where(legacy_drafts.c.phone_id == phone_id))
    if draft is None:
        raise HTTPException(status_code=404, detail='待审核机型不存在')
    return draft


@app.get('/api/admin/legacy-drafts/{phone_id}/history', dependencies=[Depends(require_admin)])
def admin_legacy_draft_history(phone_id: int, limit: int = Query(100, ge=1, le=500)):
    with engine.connect() as connection:
        if connection.scalar(select(legacy_drafts.c.phone_id).where(legacy_drafts.c.phone_id == phone_id)) is None:
            raise HTTPException(status_code=404, detail='待审核机型不存在')
        rows = connection.execute(select(legacy_draft_log).where(legacy_draft_log.c.phone_id == phone_id)
                                  .order_by(legacy_draft_log.c.id.desc()).limit(limit))
        return [{'id': row.id, 'field': row.field, 'before': row.before, 'after': row.after,
                 'created_at': row.created_at.isoformat(sep=' ') if row.created_at else None}
                for row in rows]


@app.put('/api/admin/legacy-drafts/{phone_id}/field', dependencies=[Depends(require_admin)])
def admin_update_legacy_draft(phone_id: int, edit: FieldEdit):
    with engine.begin() as connection:
        draft = connection.scalar(select(legacy_drafts.c.data).where(
            legacy_drafts.c.phone_id == phone_id).with_for_update())
        if draft is None:
            raise HTTPException(status_code=404, detail='待审核机型不存在')
        if connection.scalar(select(legacy_publications.c.phone_id).where(legacy_publications.c.phone_id == phone_id)) is not None:
            raise HTTPException(status_code=409, detail='机型已发布，请在已发布机型中编辑')
        try:
            updated = update_field(draft, edit.field, edit.value, edit.expected_value,
                                   edit.expected_evidence, edit.evidence)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        old_sources = draft.get('specFieldSources')
        before = {'value': draft.get(edit.field), 'evidence': old_sources.get(edit.field) if isinstance(old_sources, dict) else None}
        after = {'value': updated[edit.field], 'evidence': updated['specFieldSources'][edit.field]}
        connection.execute(legacy_drafts.update().where(legacy_drafts.c.phone_id == phone_id).values(data=updated))
        connection.execute(legacy_draft_log.insert().values(phone_id=phone_id, field=edit.field, before=before, after=after))
    return {'id': phone_id, 'field': edit.field, 'value': updated[edit.field], 'status': '待审核'}


@app.get('/api/admin/legacy-drafts/{phone_id}/publish-check', dependencies=[Depends(require_admin)])
def admin_legacy_publish_check(phone_id: int):
    return legacy_publish_check(admin_legacy_draft(phone_id))


@app.post('/api/admin/legacy-drafts/{phone_id}/publish', dependencies=[Depends(require_admin)])
def admin_publish_legacy(phone_id: int, request: PublishRequest):
    if not request.confirmed:
        raise HTTPException(status_code=422, detail='请确认发布')
    try:
        with engine.begin() as connection:
            draft = connection.scalar(select(legacy_drafts.c.data).where(
                legacy_drafts.c.phone_id == phone_id).with_for_update())
            if draft is None:
                raise HTTPException(status_code=404, detail='待审核机型不存在')
            check = legacy_publish_check(draft)
            if not check['ready']:
                raise HTTPException(status_code=409, detail='仍有未核实字段，请先完成核查')
            existing = connection.execute(select(phones.c.id).where(
                (phones.c.id == phone_id) | (phones.c.name == draft['name'])).with_for_update()).first()
            if existing:
                raise HTTPException(status_code=409, detail='已存在相同 ID 或名称的机型')
            published = prepare_legacy_for_publish(draft)
            connection.execute(phones.insert().values(id=phone_id, name=published['name'],
                                                       brand=published['brand'], data=published))
            connection.execute(legacy_publications.insert().values(phone_id=phone_id))
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail='机型已发布或发生数据冲突') from exc
    return {'id': phone_id, 'status': '已发布', 'missing': check['missing']}


@app.get('/api/admin/phones/{phone_id}/official-check', dependencies=[Depends(require_admin)])
def admin_official_check(phone_id: int, field: str = Query(...)):
    if field not in FIELDS:
        raise HTTPException(status_code=422, detail='不支持的字段')
    with engine.connect() as connection:
        item = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id))
    if item is None:
        raise HTTPException(status_code=404, detail='机型不存在')
    sources = item.get('specFieldSources')
    sources = sources if isinstance(sources, dict) else {}
    evidence = sources.get(field)
    evidence = evidence if isinstance(evidence, dict) else {}
    url = None
    for candidate in (evidence.get('url'), item.get('specUrl')):
        if not candidate:
            continue
        try:
            url = validate_url(candidate)
            break
        except ValueError:
            continue
    if not url:
        raise HTTPException(status_code=404, detail='没有可检查的受支持厂商官网地址')
    try:
        return check_source(url, field)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get('/api/admin/phones/{phone_id}', dependencies=[Depends(require_admin)])
def admin_phone(phone_id: int):
    with engine.connect() as connection:
        item = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id))
        if item is None: raise HTTPException(status_code=404, detail='机型不存在')
        return apply_reviewed_images(connection, [item])[0]


@app.put('/api/admin/release/{target}/{phone_id}', dependencies=[Depends(require_admin)])
def admin_update_release(target: str, phone_id: int, edit: ReleaseEdit):
    if target not in ('phones', 'legacy-drafts'):
        raise HTTPException(status_code=422, detail='机型类型无效')
    table, column, log = ((phones, phones.c.id, edit_log) if target == 'phones'
                          else (legacy_drafts, legacy_drafts.c.phone_id, legacy_draft_log))
    with engine.begin() as connection:
        item = connection.scalar(select(table.c.data).where(column == phone_id).with_for_update())
        if item is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        if target == 'legacy-drafts' and connection.scalar(select(legacy_publications.c.phone_id).where(
                legacy_publications.c.phone_id == phone_id).with_for_update()) is not None:
            raise HTTPException(status_code=409, detail='机型已发布，请在已发布机型中编辑')
        old_source = item.get('releaseSource')
        if (item.get('releaseDate') != edit.expected_value or old_source != edit.expected_evidence
                or item.get('releaseDateLabel') != edit.expected_label):
            raise HTTPException(status_code=409, detail='发布日期或来源已变更，请重新读取')
        evidence = {**(old_source if isinstance(old_source, dict) else {}), 'url': edit.url,
                    'region': edit.region, 'checkedAt': edit.checked_at.isoformat(), 'status': edit.status}
        updated = {**item, 'releaseDate': edit.value.isoformat(), 'releaseDateLabel': '发布日期', 'releaseSource': evidence}
        before = {'value': item.get('releaseDate'), 'label': item.get('releaseDateLabel'), 'evidence': old_source}
        after = {'value': updated['releaseDate'], 'label': '发布日期', 'evidence': evidence}
        connection.execute(table.update().where(column == phone_id).values(data=updated))
        connection.execute(log.insert().values(phone_id=phone_id, field='releaseDate', before=before, after=after))
    return {'id': phone_id, **after}


@app.put('/api/admin/phones/{phone_id}/sales-status', dependencies=[Depends(require_admin)])
def admin_update_sales_status(phone_id: int, edit: SalesStatusEdit):
    with engine.begin() as connection:
        item = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id).with_for_update())
        if item is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        old_source = item.get('salesStatusSource')
        if item.get('status') != edit.expected_value or old_source != edit.expected_evidence:
            raise HTTPException(status_code=409, detail='销售状态或来源已变更，请重新读取')
        evidence = {'url': edit.url, 'region': edit.region, 'channel': edit.channel,
                    'checkedAt': edit.checked_at.isoformat()}
        updated = {**item, 'status': edit.value, 'salesStatusSource': evidence}
        before = {'value': item.get('status'), 'evidence': old_source}
        after = {'value': edit.value, 'evidence': evidence}
        connection.execute(phones.update().where(phones.c.id == phone_id).values(data=updated))
        connection.execute(edit_log.insert().values(phone_id=phone_id, field='status', before=before, after=after))
    return {'id': phone_id, **after}


@app.put('/api/admin/phones/{phone_id}/market-quote', dependencies=[Depends(require_admin)])
def admin_update_market_quote(phone_id: int, edit: MarketPriceEdit):
    with engine.begin() as connection:
        item = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id).with_for_update())
        if item is None: raise HTTPException(status_code=404, detail='机型不存在')
        old = item.get('marketQuote')
        if item.get('marketQuotes'):
            raise HTTPException(status_code=409, detail='该机型已有多条报价，请使用版本报价维护')
        if old != edit.expected_quote: raise HTTPException(status_code=409, detail='渠道报价已变更，请重新读取')
        quote = {'amount': str(edit.amount), 'currency': edit.currency, 'variant': edit.variant,
                 'region': edit.region, 'channel': edit.channel, 'url': edit.url,
                 'observedAt': edit.observed_at.isoformat(), 'kind': '人工核查渠道报价'}
        connection.execute(phones.update().where(phones.c.id == phone_id).values(data={**item, 'marketQuote': quote}))
        connection.execute(edit_log.insert().values(phone_id=phone_id, field='marketQuote', before=old, after=quote))
    return {'id':phone_id, 'quote':quote}


@app.put('/api/admin/phones/{phone_id}/market-quotes', dependencies=[Depends(require_admin)])
def admin_save_market_quotes(phone_id: int, edit: MarketQuotesEdit):
    with engine.begin() as connection:
        item=connection.scalar(select(phones.c.data).where(phones.c.id==phone_id).with_for_update())
        if item is None: raise HTTPException(status_code=404, detail='机型不存在')
        old=item.get('marketQuote');quotes=item.get('marketQuotes')
        if old != edit.expected_quote or quotes != edit.expected_quotes:
            raise HTTPException(status_code=409, detail='报价已变更，请重新读取')
        if (old is not None and not isinstance(old,dict)) or (quotes is not None and (not isinstance(quotes,list) or len(quotes)>20 or any(not isinstance(q,dict) for q in quotes))):
            raise HTTPException(status_code=409, detail='原报价格式无效，请先检查')
        new_quote={'amount':str(edit.amount),'currency':edit.currency,'variant':edit.variant,'region':edit.region,
                   'channel':edit.channel,'url':edit.url,'observedAt':edit.observed_at.isoformat(),'kind':'人工核查渠道报价'}
        entries=[('legacy',old)] if old is not None else []
        entries += [(str(i),q) for i,q in enumerate(quotes or [])]
        if edit.slot is not None and not any(slot==edit.slot for slot,_ in entries):
            raise HTTPException(status_code=404, detail='报价记录不存在，请重新读取')
        norm=lambda v: ''.join(str(v or '').split()).casefold()
        key=lambda q: tuple(norm(q.get(k)) for k in ('variant','region','channel'))
        if any(slot!=edit.slot and key(q)==key(new_quote) for slot,q in entries):
            raise HTTPException(status_code=409, detail='该版本、地区和渠道已有报价，请编辑原记录')
        if edit.slot is None and len(entries)>=20: raise HTTPException(status_code=409, detail='每款机型最多保存 20 条报价')
        new_quotes=list(quotes or []);new_old=old
        if edit.slot is None: new_quotes.append(new_quote)
        elif edit.slot=='legacy': new_old=new_quote
        else: new_quotes[int(edit.slot)]=new_quote
        updated={**item,'marketQuotes':new_quotes}
        if new_old is not None: updated['marketQuote']=new_old
        before={'legacy':old,'quotes':quotes};after={'legacy':new_old,'quotes':new_quotes}
        connection.execute(phones.update().where(phones.c.id==phone_id).values(data=updated))
        connection.execute(edit_log.insert().values(phone_id=phone_id,field='marketQuotes',before=before,after=after))
    return {'id':phone_id,**after}


@app.post('/api/admin/phones/{phone_id}/historical-prices', status_code=201,
          dependencies=[Depends(require_admin)])
def admin_add_historical_price(phone_id: int, edit: HistoricalPriceAdd):
    with engine.begin() as connection:
        item = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id).with_for_update())
        if item is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        primary, variants = item.get('launchPrice'), item.get('launchPriceVariants')
        if primary != edit.expected_primary or variants != edit.expected_variants:
            raise HTTPException(status_code=409, detail='价格记录已变更，请重新读取机型')
        if (primary is not None and not isinstance(primary, dict)) or (variants is not None and
                (not isinstance(variants, list) or any(not isinstance(v, dict) for v in variants))):
            raise HTTPException(status_code=409, detail='原价格记录格式异常，请先检查')
        if primary and primary.get('status') == '资料冲突':
            raise HTTPException(status_code=409, detail='主价格资料冲突，请先核对现有记录')
        normalize = lambda value: ''.join(str(value or '').split()).casefold()
        entries = ([primary] if primary else []) + (variants or [])
        if any(normalize(v.get('variant')) == normalize(edit.variant) and
               normalize(v.get('region')) == normalize(edit.region) for v in entries):
            raise HTTPException(status_code=409, detail='相同地区和版本已有价格，请先核对原记录')
        record = {'amount': float(edit.amount), 'currency': edit.currency, 'variant': edit.variant,
                  'type': edit.type, 'region': edit.region, 'url': edit.url,
                  'checkedAt': edit.checked_at.isoformat(), 'status': edit.status}
        updated = dict(item)
        if not primary:
            updated['launchPrice'] = record
        else:
            updated['launchPriceVariants'] = [*(variants or []), record]
        before = {'primary': primary, 'variants': variants}
        after = {'primary': updated.get('launchPrice'), 'variants': updated.get('launchPriceVariants')}
        connection.execute(phones.update().where(phones.c.id == phone_id).values(data=updated))
        connection.execute(edit_log.insert().values(phone_id=phone_id, field='launchPrice', before=before, after=after))
    return {'id': phone_id, **after}


@app.put('/api/admin/phones/{phone_id}/historical-prices/{slot}', dependencies=[Depends(require_admin)])
def admin_edit_historical_price(phone_id: int, slot: str, edit: HistoricalPriceAdd):
    if slot != 'primary' and (not slot.isascii() or not slot.isdigit() or len(slot) > 6):
        raise HTTPException(status_code=422, detail='价格位置无效')
    with engine.begin() as connection:
        item = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id).with_for_update())
        if item is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        primary, variants = item.get('launchPrice'), item.get('launchPriceVariants')
        if primary != edit.expected_primary or variants != edit.expected_variants:
            raise HTTPException(status_code=409, detail='价格记录已变更，请重新读取机型')
        if (primary is not None and not isinstance(primary, dict)) or (variants is not None and
                (not isinstance(variants, list) or any(not isinstance(v, dict) for v in variants))):
            raise HTTPException(status_code=409, detail='原价格记录格式异常，请先检查')
        index = None if slot == 'primary' else int(slot)
        if (index is None and not primary) or (index is not None and (not variants or index >= len(variants))):
            raise HTTPException(status_code=404, detail='价格记录不存在，请重新读取')
        old = primary if index is None else variants[index]
        others = ([] if index is None or not primary else [primary]) + [
            entry for i, entry in enumerate(variants or []) if i != index]
        normalize = lambda value: ''.join(str(value or '').split()).casefold()
        if any(normalize(v.get('variant')) == normalize(edit.variant) and
               normalize(v.get('region')) == normalize(edit.region) for v in others):
            raise HTTPException(status_code=409, detail='相同地区和版本已有价格，请先核对原记录')
        record = {**old, 'amount': float(edit.amount), 'currency': edit.currency, 'variant': edit.variant,
                  'type': edit.type, 'region': edit.region, 'url': edit.url,
                  'checkedAt': edit.checked_at.isoformat(), 'status': edit.status}
        updated = dict(item)
        if index is None:
            updated['launchPrice'] = record
        else:
            updated_variants = list(variants)
            updated_variants[index] = record
            updated['launchPriceVariants'] = updated_variants
        before = {'primary': primary, 'variants': variants}
        after = {'primary': updated.get('launchPrice'), 'variants': updated.get('launchPriceVariants')}
        connection.execute(phones.update().where(phones.c.id == phone_id).values(data=updated))
        connection.execute(edit_log.insert().values(phone_id=phone_id, field='launchPrice', before=before, after=after))
    return {'id': phone_id, **after}


@app.get('/api/admin/phones/{phone_id}/history', dependencies=[Depends(require_admin)])
def admin_phone_history(phone_id: int, limit: int = Query(100, ge=1, le=500)):
    with engine.connect() as connection:
        if connection.scalar(select(phones.c.id).where(phones.c.id == phone_id)) is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        rows = connection.execute(select(edit_log).where(edit_log.c.phone_id == phone_id)
                                  .order_by(edit_log.c.id.desc()).limit(limit))
        return [{'id': row.id, 'field': row.field, 'before': row.before, 'after': row.after,
                 'created_at': row.created_at.isoformat(sep=' ') if row.created_at else None}
                for row in rows]


@app.put('/api/admin/phones/{phone_id}/field', dependencies=[Depends(require_admin)])
def admin_update_field(phone_id: int, edit: FieldEdit):
    with engine.begin() as connection:
        phone = connection.scalar(select(phones.c.data).where(phones.c.id == phone_id).with_for_update())
        if phone is None:
            raise HTTPException(status_code=404, detail='机型不存在')
        try:
            updated = update_field(phone, edit.field, edit.value, edit.expected_value, edit.expected_evidence, edit.evidence)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        old_sources = phone.get('specFieldSources')
        before = {'value': phone.get(edit.field), 'evidence': old_sources.get(edit.field) if isinstance(old_sources, dict) else None}
        after = {'value': updated[edit.field], 'evidence': updated['specFieldSources'][edit.field]}
        connection.execute(phones.update().where(phones.c.id == phone_id).values(data=updated))
        connection.execute(edit_log.insert().values(phone_id=phone_id, field=edit.field, before=before, after=after))
    return {'id': phone_id, 'field': edit.field, 'value': updated[edit.field]}
