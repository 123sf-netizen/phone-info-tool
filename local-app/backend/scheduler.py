"""定期只读盘点，按配置低频检查已登记官网；不修改机型。"""
import logging
import os
import time

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, select, text
from gaps import make_report
from report_writer import write_report
from scheduled_sources import run_once as check_official_once

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
engine = create_engine(os.environ['DATABASE_URL'], pool_pre_ping=True)
phones = Table('phones', MetaData(), Column('id', Integer, primary_key=True),
               Column('name', String(255)), Column('brand', String(128)), Column('data', JSON))


def run_once():
    with engine.connect() as connection:
        acquired = connection.scalar(text("SELECT GET_LOCK('phoneguide_gap_report', 0)"))
        if acquired != 1:
            logging.info('另一实例正在盘点，本次跳过')
            return
        try:
            rows = list(connection.scalars(select(phones.c.data).order_by(phones.c.id)))
            write_report('/reports', make_report(rows))
            logging.info('缺口报告已生成，机型数 %s', len(rows))
            if os.environ.get('AUTO_OFFICIAL_CHECK', '1') == '1':
                try:
                    item = check_official_once('/reports', rows)
                    if item: logging.info('官网线索检查完成: 机型 %s 字段数 %s 首字段 %s 状态 %s', item['phone_id'], item['field_count'], item['field'], item['outcome'])
                except Exception:
                    logging.exception('官网线索检查失败，不影响缺口盘点')
        finally:
            connection.execute(text("SELECT RELEASE_LOCK('phoneguide_gap_report')"))


if __name__ == '__main__':
    while True:
        try:
            run_once()
        except Exception:
            logging.exception('盘点失败，将在下次周期重试')
        time.sleep(180)
