"""Read-only official source checks; reachable text is not field verification."""
import ipaddress
import hashlib
import re
import socket
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urljoin
from urllib.request import Request, HTTPRedirectHandler, build_opener

HOSTS = {'consumer.huawei.com', 'www.vivo.com.cn', 'www.iqoo.com', 'www.oppo.com', 'www.oneplus.com', 'www.mi.com', 'www.apple.com.cn', 'www.honor.com', 'www.samsung.com.cn'}
KEYWORDS = {'battery': ('电池', '容量'), 'charge': ('充电', '闪充'), 'screen': ('屏幕', '显示屏'), 'chip': ('处理器', '芯片'), 'camera': ('后置', '主摄'), 'front': ('前置',), 'weight': ('重量',), 'ip': ('防尘', '防水', 'IP68', 'IP69'), 'system': ('操作系统', '系统'), 'storage': ('存储', '内存'), 'updates': ('升级', '更新')}
MAX_BYTES = 1024 * 1024


class SourceCheckError(RuntimeError):
    def __init__(self, category, message):
        super().__init__(message)
        self.category = category


def http_error(code):
    if code in (404,410): return SourceCheckError('not_found',f'来源页面不存在或已移除（HTTP {code}）；不代表该机型没有公开资料')
    if code in (401,403): return SourceCheckError('blocked',f'官网拒绝访问（HTTP {code}），请人工检查来源')
    if code == 429: return SourceCheckError('rate_limited','官网限制访问（HTTP 429），稍后重试')
    if 500 <= code <= 599: return SourceCheckError('server_error',f'官网服务器暂时异常（HTTP {code}）')
    return SourceCheckError('http_error',f'官网返回 HTTP {code}，请人工检查来源')


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(); self.hidden = 0; self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style', 'noscript'): self.hidden += 1
    def handle_endtag(self, tag):
        if tag in ('script', 'style', 'noscript') and self.hidden: self.hidden -= 1
    def handle_data(self, data):
        if not self.hidden: self.parts.append(data)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def validate_url(value):
    try:
        p = urlparse(value)
        if p.scheme != 'https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None, 443): raise ValueError()
        return value
    except (ValueError, TypeError):
        raise ValueError('仅支持已登记的厂商官网 HTTPS 地址')


def visible_text(body):
    parser = VisibleText(); parser.feed(body)
    return re.sub(r'\s+', ' ', ' '.join(parser.parts)).strip()


def snippets_from_text(text, field):
    if field not in KEYWORDS: raise ValueError('字段不支持')
    matches = []
    # Prioritize units for these fields; snippets are still unverified context.
    units = {'battery': r'\d\s*(?:mAh|毫安时)', 'charge': r'\d\s*(?:W|瓦)',
             'weight': r'\d\s*(?:g|克)', 'ip': r'\bIP\s*\d{2}\b'}
    pattern = units.get(field)
    for keyword in KEYWORDS[field]:
        for match in re.finditer(re.escape(keyword), text, flags=re.IGNORECASE):
            pos = match.start()
            snippet = text[max(0, pos-45):pos+len(keyword)+90]
            score = bool(pattern and re.search(pattern, snippet, flags=re.IGNORECASE))
            matches.append((not score, pos, snippet))
    matches.sort(key=lambda item: (item[0], item[1]))
    selected = []
    for _, pos, snippet in matches:
        if any(abs(pos - previous) < 45 for previous, _ in selected): continue
        selected.append((pos, snippet))
        if len(selected) == 3: break
    return [snippet for _, snippet in selected]


def extract_snippets(body, field):
    return snippets_from_text(visible_text(body), field)


def battery_typical_candidate(snippets):
    """只提取明确标注典型值的单一容量；结果仍须人工核对型号和地区。"""
    if not isinstance(snippets, list) or any(not isinstance(item, str) for item in snippets):
        return None
    patterns = (r'(?:典型容量|典型值|典型电池容量)\s*[:：]?\s*(\d{3,5})\s*mAh\b',
                r'(\d{3,5})\s*mAh\s*[（(]\s*典型值\s*[）)]')
    values = set()
    all_capacities = set()
    for snippet in snippets:
        all_capacities.update(int(match.group(1)) for match in re.finditer(r'(\d{3,5})\s*mAh\b', snippet, re.I))
        for pattern in patterns:
            values.update(int(match.group(1)) for match in re.finditer(pattern, snippet, re.I))
    if len(values) != 1 or all_capacities != values:
        return None
    return f'{values.pop()}mAh（典型值）'


def check_source_fields(url, fields):
    validate_url(url)
    if not fields or len(fields) > len(KEYWORDS) or len(set(fields)) != len(fields) or any(field not in KEYWORDS for field in fields):
        raise ValueError('字段不支持')
    original_host = urlparse(url).hostname
    current = url
    opener = build_opener(NoRedirect())
    try:
        for hops in range(3):
            host = urlparse(current).hostname
            addresses = {item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
            if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
                raise SourceCheckError('unsafe_address','官网地址解析异常，已停止访问')
            try:
                response = opener.open(Request(current, headers={'User-Agent':'PhoneGuideSourceCheck/1.0','Accept':'text/html'}), timeout=8)
            except HTTPError as exc:
                if exc.code not in (301, 302, 303, 307, 308):
                    raise http_error(exc.code) from exc
                location = exc.headers.get('Location') if exc.headers else None
                if not location or hops >= 2:
                    raise SourceCheckError('unsupported_redirect','官网跳转缺少地址或超过次数限制') from exc
                next_url = urljoin(current, location)
                try:
                    validate_url(next_url)
                except ValueError as problem:
                    raise SourceCheckError('unsupported_redirect','官网跳转到不受支持的地址，已停止访问') from problem
                if urlparse(next_url).hostname != original_host:
                    raise SourceCheckError('unsupported_redirect','官网跳转到不同域名，已停止访问')
                current = next_url
                continue
            with response:
                content_type = response.headers.get_content_type()
                if content_type not in ('text/html', 'application/xhtml+xml'):
                    raise SourceCheckError('invalid_content','来源不是 HTML 页面，无法提取文字')
                raw = response.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES: raise SourceCheckError('invalid_content','网页过大，未读取完整内容')
            body = raw.decode('utf-8', errors='replace')
            text = visible_text(body)
            snippets = {field: snippets_from_text(text, field) for field in fields}
            page_hash = hashlib.sha256(text.encode('utf-8')).hexdigest() if text else None
            return {'url':url, 'resolved_url':current, 'checked_at':datetime.now(timezone.utc).isoformat(), 'snippets_by_field':snippets, 'page_hash':page_hash,
                    'note':'只检查页面可访问性和关键词，不能证明参数、型号或地区正确；请人工核对后再保存。'}
    except (URLError, OSError, TimeoutError) as exc:
        raise SourceCheckError('network','官网连接失败或超时，请稍后重试') from exc


def check_source(url, field):
    result = check_source_fields(url, [field])
    snippets = result.pop('snippets_by_field')[field]
    return {**result, 'snippets': snippets}
