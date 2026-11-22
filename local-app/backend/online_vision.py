"""Optional online image lookup. Never persists images or classifies returned pages as verified."""
import base64
import binascii
import json
import time
from collections import deque
from threading import Lock
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

MAX_IMAGE_BYTES = 2 * 1024 * 1024
ENDPOINT = 'https://vision.googleapis.com/v1/images:annotate'


_attempts = deque()
_attempt_lock = Lock()


def allow_online_request(now=None):
    now = time.monotonic() if now is None else now
    with _attempt_lock:
        while _attempts and _attempts[0] <= now - 60:
            _attempts.popleft()
        if len(_attempts) >= 6:
            return False
        _attempts.append(now)
        return True


def decode_image(encoded):
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError('图片编码无效') from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise ValueError('图片为空或超过 2 MB')
    if not (data.startswith(b'\xff\xd8\xff') or data.startswith(b'\x89PNG\r\n\x1a\n') or (data.startswith(b'RIFF') and data[8:12] == b'WEBP')):
        raise ValueError('仅支持 JPEG、PNG 或 WebP 图片')
    return data


def safe_url(value):
    try:
        parsed = urlparse(value)
        return value if parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password else None
    except (TypeError, ValueError):
        return None


def extract_results(document):
    responses = document.get('responses') if isinstance(document, dict) else None
    if not isinstance(responses, list) or not responses or not isinstance(responses[0], dict):
        raise ValueError('识图服务响应无效')
    response = responses[0]
    if response.get('error'):
        raise RuntimeError('识图服务未能处理图片')
    detection = response.get('webDetection') or {}
    if not isinstance(detection, dict):
        raise ValueError('识图服务响应无效')
    pages, seen = [], set()
    for item in detection.get('pagesWithMatchingImages') or []:
        if not isinstance(item, dict): continue
        url = safe_url(item.get('url'))
        if not url or url in seen: continue
        seen.add(url)
        title = str(item.get('pageTitle') or '相似图片网页')[:200]
        pages.append({'title': title, 'url': url})
        if len(pages) == 8: break
    labels = []
    for item in detection.get('webEntities') or []:
        if isinstance(item, dict) and isinstance(item.get('description'), str):
            label = item['description'].strip()[:100]
            if label and label not in labels: labels.append(label)
        if len(labels) == 8: break
    return {'pages': pages, 'labels': labels}


def search_google(encoded, api_key):
    decode_image(encoded)
    if not api_key: raise RuntimeError('在线识图尚未配置')
    body = json.dumps({'requests': [{'image': {'content': encoded}, 'features': [{'type': 'WEB_DETECTION', 'maxResults': 8}]}]}).encode('utf-8')
    request = Request(ENDPOINT, data=body, headers={'Content-Type': 'application/json', 'x-goog-api-key': api_key}, method='POST')
    try:
        with urlopen(request, timeout=15) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024: raise ValueError('识图服务响应过大')
        return extract_results(json.loads(raw))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError('在线识图服务暂不可用，请检查网络与配置') from exc
