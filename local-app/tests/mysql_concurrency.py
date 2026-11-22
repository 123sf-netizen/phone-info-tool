from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from sqlalchemy import select, func
import app
import time

for attempt in range(30):
    try:
        app.metadata.create_all(app.engine)
        break
    except Exception:
        if attempt == 29: raise
        time.sleep(1)
barrier = Barrier(12)
def send(_):
    barrier.wait(timeout=15)
    return app.submit_feedback(app.FeedbackRequest(type='问题反馈', text='隔离并发测试', request_id='2ca47cd1-3c7a-4c09-9117-911aff900001'))['id']
with ThreadPoolExecutor(max_workers=12) as executor:
    ids = list(executor.map(send, range(12)))
with app.engine.connect() as connection:
    total = connection.scalar(select(func.count()).select_from(app.feedback))
    keys = connection.scalar(select(func.count()).select_from(app.feedback_request))
if len(set(ids)) != 1 or total != 1 or keys != 1:
    raise SystemExit('FAIL: concurrent retries did not deduplicate')
print('PASS: 12 concurrent requests, one feedback and one request key')
