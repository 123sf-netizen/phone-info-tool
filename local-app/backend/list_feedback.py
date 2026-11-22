"""只在本机容器命令行读取最近的反馈，不开放公网读取接口。"""
import argparse
import json
import os

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, select


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--limit', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 500:
        parser.error('数量必须在 1 到 500 之间')
    feedback = Table('feedback', MetaData(),
                     Column('id', Integer, primary_key=True),
                     Column('type', String(32)), Column('text', Text),
                     Column('created_at', DateTime))
    state = Table('feedback_state', feedback.metadata,
                  Column('feedback_id', Integer, primary_key=True), Column('status', String(32)))
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            rows = connection.execute(select(feedback, state.c.status).select_from(
                feedback.outerjoin(state, feedback.c.id == state.c.feedback_id)
            ).order_by(feedback.c.id.desc()).limit(args.limit))
            data = [{'id': row.id, 'type': row.type, 'text': row.text,
                     'status': row.status or '待处理',
                     'created_at': row.created_at.isoformat(sep=' ') if row.created_at else None}
                    for row in rows]
        print(json.dumps(data, ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
