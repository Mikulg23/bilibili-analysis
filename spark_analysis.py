"""模块三：从 MySQL 读取清洗数据，用 Spark 计算图表结果。"""
import os
import re

from pyspark.sql import SparkSession, functions as F

import config
from db import get_connection
from preprocessing import batch_table_name


def get_spark():
    if config.SPARK_JAVA_HOME:
        os.environ["JAVA_HOME"] = config.SPARK_JAVA_HOME
    if not config.MYSQL_JDBC_JAR.is_file():
        raise ValueError("缺少 MySQL JDBC 驱动，请按 README 下载并配置 MYSQL_JDBC_JAR。")
    # 按手册使用本机全部核心；首次请求启动，后续请求复用 JVM。
    spark = (SparkSession.builder.appName("Bilibili_Analysis").master("local[*]")
             .config("spark.driver.extraClassPath", str(config.MYSQL_JDBC_JAR))
             .config("spark.executor.extraClassPath", str(config.MYSQL_JDBC_JAR))
             .config("spark.driver.host", "127.0.0.1")
             .config("spark.driver.bindAddress", "127.0.0.1")
             .config("spark.sql.shuffle.partitions", "8")
             .config("spark.ui.enabled", "false")
             .getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    return spark


def read_mysql(file_name):
    if not re.fullmatch(r"bilibili_video_data_\d{8}_[A-Za-z0-9_\u4e00-\u9fff]+", file_name) or len(file_name) > 64:
        raise ValueError("数据表名不合法。")
    url = (f"jdbc:mysql://{config.MYSQL_HOST}:{config.MYSQL_PORT}/{config.MYSQL_DATABASE}"
           "?useUnicode=true&characterEncoding=UTF-8&serverTimezone=Asia/Shanghai"
           "&connectTimeout=5000&socketTimeout=30000")
    frame = (get_spark().read.format("jdbc").option("url", url)
             .option("dbtable", f"`{file_name}`")
             .option("user", config.MYSQL_USER).option("password", config.MYSQL_PASSWORD)
             .option("driver", "com.mysql.cj.jdbc.Driver").load())
    # MySQL 无符号整数可能读成 Decimal，转为适合统计和 JSON 的整数。
    return frame.select("title", "url", "up", *[
        F.col(name).cast("long").alias(name) for name in ("play", "like", "coin", "favorite", "share")])


def top10_play(file_name, data=None):
    data = read_mysql(file_name) if data is None else data
    rows = data.orderBy(F.desc("play"), "url").select("title", "play").limit(10).collect()
    return {"titles": [row.title[:20] + ("…" if len(row.title) > 20 else "") for row in rows],
            "values": [row.play for row in rows]}


def interaction_ratio(file_name, data=None):
    data = read_mysql(file_name) if data is None else data
    fields = {"like": "点赞", "coin": "投币", "favorite": "收藏", "share": "转发"}
    row = data.agg(F.count("*").alias("count"), *[F.sum(name).alias(name) for name in fields]).first()
    if not row["count"]:
        return []
    return [{"name": label, "value": row[name] or 0} for name, label in fields.items()]


def title_len_play(file_name, data=None):
    data = read_mysql(file_name) if data is None else data
    rows = (data.groupBy(F.length("title").alias("length"))
            .agg((F.sum("play") / 10000).alias("total"))
            .orderBy("length").collect())
    return {"x": [row.length for row in rows], "y": [row.total for row in rows]}


def like_coin_scatter(file_name, data=None):
    data = read_mysql(file_name) if data is None else data
    return [[row["like"], row.coin] for row in data.select("like", "coin").collect()]


def analyze_data(collection_date, keyword=""):
    file_name = batch_table_name(collection_date, keyword)
    # 先检查批次是否存在，返回易懂的提示，避免把 JDBC 错误暴露给页面。
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                           (config.MYSQL_DATABASE, file_name))
            if cursor.fetchone() is None:
                raise ValueError("该批次尚未写入 MySQL，请先执行数据预处理；关键词留空对应当日合并表。")
    data = read_mysql(file_name).cache()
    try:
        row = data.agg(F.count("*").alias("count"), F.sum("play").alias("play"),
                       F.countDistinct("up").alias("up")).first()
        interactions = interaction_ratio(file_name, data)
        return {"summary": {"video_count": row["count"], "total_play": row.play or 0,
                            "total_interactions": sum(item["value"] for item in interactions), "up_count": row.up},
                "top10_play": top10_play(file_name, data), "interaction_ratio": interactions,
                "title_len_play": title_len_play(file_name, data),
                "like_coin_scatter": like_coin_scatter(file_name, data)}
    finally:
        data.unpersist()
