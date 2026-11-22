"""只读比较原型和数据库；字段值不写入报告，避免暴露无关内容。"""
import json
import os
from pathlib import Path

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, select
from seed import compare, load_seed


def main():
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    metadata = MetaData()
    phones = Table('phones', metadata, Column('id', Integer, primary_key=True),
                   Column('name', String(255)), Column('brand', String(128)), Column('data', JSON))
    try:
        with engine.connect() as connection:
            rows = list(connection.scalars(select(phones.c.data)))
        print(json.dumps(compare(load_seed(Path('/seed/index.html')), rows), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
