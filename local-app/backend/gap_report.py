"""只读数据库并输出字段缺口报告。"""
import json
import os
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, select
from gaps import make_report


def main():
    engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
    phones = Table('phones', MetaData(), Column('id', Integer, primary_key=True),
                   Column('name', String(255)), Column('brand', String(128)), Column('data', JSON))
    try:
        with engine.connect() as connection:
            rows = list(connection.scalars(select(phones.c.data).order_by(phones.c.id)))
        print(json.dumps(make_report(rows), ensure_ascii=False, indent=2))
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
