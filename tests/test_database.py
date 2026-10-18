"""检查表名校验与失败回滚，不连接真实 MySQL。"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pymysql

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from db import save_cleaned_data
from pachong import FIELDS


if __name__ == "__main__":
    frame = pd.DataFrame([["VALUE_PLACEHOLDER"] * 8], columns=FIELDS)
    with patch("db.get_connection") as connect:
        try:
            save_cleaned_data(frame, "TABLE; DROP DATABASE TEST")
            raise AssertionError("Invalid table name was accepted")
        except ValueError:
            pass
        connect.assert_not_called()
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.executemany.side_effect = pymysql.OperationalError(9999, "SELF_CHECK")
    with patch("db.get_connection", return_value=connection):
        try:
            save_cleaned_data(frame, "bilibili_video_data_20261016_TEST")
            raise AssertionError("Failed insert was ignored")
        except pymysql.OperationalError:
            pass
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()
    print("PASS: SQL identifier validation and rollback on failed replacement")
