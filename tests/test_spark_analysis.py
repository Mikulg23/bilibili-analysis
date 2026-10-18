"""少量固定数据验证四项计算；需要 Java 17 和 JDBC 驱动，不连接 MySQL。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from spark_analysis import get_spark, top10_play, interaction_ratio, title_len_play, like_coin_scatter


if __name__ == "__main__":
    spark = get_spark()
    try:
        # 使用 Spark SQL 建小表，避免依赖 Windows Python worker 的启动配置。
        frame = spark.sql("""SELECT * FROM VALUES
            ('AA', 'URL_1', 10000L, 10L, 2L, 3L, 1L),
            ('BB', 'URL_2', 20000L, 20L, 4L, 6L, 2L),
            ('CCC', 'URL_3', 5000L, 5L, 1L, 0L, 0L)
            AS videos(title, url, play, like, coin, favorite, share)""")
        assert top10_play("", frame) == {"titles": ["BB", "AA", "CCC"], "values": [20000, 10000, 5000]}
        assert interaction_ratio("", frame) == [
            {"name": "点赞", "value": 35}, {"name": "投币", "value": 7},
            {"name": "收藏", "value": 9}, {"name": "转发", "value": 3}]
        assert title_len_play("", frame) == {"x": [2, 3], "y": [3.0, 0.5]}
        assert sorted(like_coin_scatter("", frame)) == [[5, 1], [10, 2], [20, 4]]
        long_title = frame.selectExpr("repeat('字', 25) AS title", "url", "play")
        assert top10_play("", long_title)["titles"][0] == "字" * 20 + "…"
        empty = frame.limit(0)
        assert top10_play("", empty) == {"titles": [], "values": []}
        assert interaction_ratio("", empty) == []
        assert title_len_play("", empty) == {"x": [], "y": []}
        assert like_coin_scatter("", empty) == []
        print("Spark calculation checks passed.")
    finally:
        spark.stop()
