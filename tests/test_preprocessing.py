"""只检查核心清洗规则，不连接数据库或 HDFS。"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from preprocessing import clean_dataframe, count_to_number, batch_table_name


if __name__ == "__main__":
    assert count_to_number("1.2万") == 12000
    assert count_to_number("２.５千") == 2500
    assert count_to_number("1,234") == 1234
    assert np.isnan(count_to_number("-1"))
    rows = []
    for index in range(10):
        rows.append({"title": " <b>TITLE_PLACEHOLDER</b>\n&amp; ",
                     "url": f"https://www.bilibili.com/video/BV{index:010d}/",
                     "up": "UP_PLACEHOLDER", "play": str(index + 1),
                     "like": "" if index == 0 else str(index),
                     "coin": "1千", "favorite": "1.2万", "share": "1"})
    rows[-1]["play"] = "1000000000"
    rows.append({**rows[0], "url": rows[0]["url"] + "?source=TEST"})
    rows.append({**rows[0], "url": "https://invalid.example/video/TEST"})
    frame, stats = clean_dataframe(pd.DataFrame(rows))
    assert stats["before_count"] == 12 and stats["after_count"] == 10
    assert stats["removed_duplicates"] == 1 and stats["invalid_urls"] == 1
    assert stats["filled_numeric_cells"] == 1 and stats["clipped_outlier_cells"] == 1
    assert frame.iloc[0]["like"] == 0 and frame.iloc[0]["title"] == "TITLE_PLACEHOLDER &"
    assert frame["coin"].eq(1000).all() and frame["favorite"].eq(12000).all()
    assert frame.iloc[-1]["play"] < 1000000000
    assert frame["url"].is_unique and frame["play"].dtype == "int64"
    assert len(batch_table_name("2026-10-16", "KEYWORD_PLACEHOLDER" * 10)) <= 64
    print("PASS: unit conversion, missing values, titles, URLs, duplicates and IQR clipping")
