import re

import pymysql

import config
from pachong import FIELDS


def get_connection(database=config.MYSQL_DATABASE):
    if not config.MYSQL_USER or "PLACEHOLDER" in config.MYSQL_USER or "PLACEHOLDER" in config.MYSQL_PASSWORD:
        raise ValueError("请在本地 .env 填写 MySQL 账号和密码后重启服务。")
    return pymysql.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
                           user=config.MYSQL_USER, password=config.MYSQL_PASSWORD,
                           database=database, charset="utf8mb4", autocommit=False,
                           connect_timeout=3, read_timeout=10, write_timeout=10)


def save_cleaned_data(frame, table_name):
    # 表名不能作为 SQL 参数绑定，必须先严格校验。
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", config.MYSQL_DATABASE):
        raise ValueError("数据库名只能使用字母、数字和下划线，长度不超过 64。")
    if len(table_name) > 64 or not re.fullmatch(r"bilibili_video_data_\d{8}_[A-Za-z0-9_\u4e00-\u9fff]+", table_name):
        raise ValueError("数据表名不符合规则。")
    connection = get_connection(database=None)
    try:
        with connection.cursor() as cursor:
            sql = (config.BASE_DIR / "sql" / "init.sql").read_text(encoding="utf-8")
            sql = sql.replace("`bilibili_analysis`", f"`{config.MYSQL_DATABASE}`")
            for statement in sql.split(";"):
                if statement.strip():
                    cursor.execute(statement)
            cursor.execute(f"CREATE TABLE IF NOT EXISTS `{table_name}` LIKE `video_data_template`")
            # 同批次重跑时在一个事务内替换，插入失败则回滚旧数据。
            connection.begin()
            cursor.execute(f"DELETE FROM `{table_name}`")
            columns = ",".join(f"`{field}`" for field in FIELDS)
            placeholders = ",".join(["%s"] * len(FIELDS))
            cursor.executemany(f"INSERT INTO `{table_name}` ({columns}) VALUES ({placeholders})",
                               list(frame[FIELDS].itertuples(index=False, name=None)))
            cursor.execute(f"SELECT COUNT(*) FROM `{table_name}`")
            count = cursor.fetchone()[0]
            if count != len(frame):
                raise RuntimeError("MySQL 写入数量不匹配，已回滚。")
        connection.commit()
        return count
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
