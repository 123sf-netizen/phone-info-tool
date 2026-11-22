"""默认只预览；--apply 仅插入缺失的机型，不更新或删除已有记录。"""
import argparse
import json
import os

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, select
from seed import load_seed, missing_rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true', help='插入原型中存在但数据库中没有的机型')
    args = parser.parse_args()
    data = load_seed('/seed/index.html')
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    metadata = MetaData()
    phones = Table('phones', metadata, Column('id', Integer, primary_key=True),
                   Column('name', String(255)), Column('brand', String(128)), Column('data', JSON))
    try:
        with engine.begin() as connection:
            existing = list(connection.scalars(select(phones.c.id)))
            rows = missing_rows(data, existing)
            if args.apply and rows:
                connection.execute(phones.insert(), [
                    {'id': row['id'], 'name': row['name'], 'brand': row['brand'], 'data': row}
                    for row in rows
                ])
        print(json.dumps({'mode': 'inserted' if args.apply else 'preview', 'count': len(rows),
                          'phones': [{'id': row['id'], 'name': row['name']} for row in rows]},
                         ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
