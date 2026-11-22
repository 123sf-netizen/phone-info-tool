FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN pip install --no-cache-dir --default-timeout=120 --retries 5 -r requirements.txt
COPY app.py seed.py audit.py sync_seed.py gaps.py gap_report.py list_feedback.py scheduler.py report_writer.py report_status.py online_vision.py official_check.py scheduled_sources.py editing.py test_feedback.py images_audit.py release_gaps.py price_gaps.py back_references.py ./
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
