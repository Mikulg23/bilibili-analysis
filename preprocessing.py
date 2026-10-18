import argparse
import hashlib
import html
import json
import os
import re
import tempfile
import unicodedata
from datetime import date
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import ProxyHandler, Request, build_opener

import numpy as np
import pandas as pd
import pymysql

import config
from db import save_cleaned_data
from pachong import FIELDS

NUMERIC_FIELDS = FIELDS[3:]


def count_to_number(value):
    text = unicodedata.normalize("NFKC", str(value))
    text = re.sub(r"[\s,]", "", text)
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([千kK万wW亿]?)", text)
    if not match:
        return np.nan
    multiplier = {"千": 1000, "k": 1000, "万": 10000, "w": 10000, "亿": 100000000}
    number = float(match.group(1)) * multiplier.get(match.group(2).lower(), 1)
    return number if 0 <= number <= 2 ** 53 - 1 else np.nan


def clean_title(value):
    text = html.unescape(unicodedata.normalize("NFKC", str(value)))
    text = re.sub(r"<[^>]*>", "", text)
    text = re.sub(r"[\x00-\x1f\x7f\u200b-\u200f\ufeff]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(value):
    try:
        parsed = urlsplit(str(value).strip())
    except ValueError:
        return ""
    if parsed.scheme not in ("https", "http") or parsed.hostname not in ("www.bilibili.com", "bilibili.com", "m.bilibili.com"):
        return ""
    match = re.fullmatch(r"/video/(BV[0-9A-Za-z]{10})/?", parsed.path)
    return f"https://www.bilibili.com/video/{match.group(1)}/" if match else ""


def clean_dataframe(frame):
    missing = set(FIELDS) - set(frame.columns)
    if missing:
        raise ValueError("原始 CSV 缺少必需字段：" + ", ".join(sorted(missing)))
    frame = frame[FIELDS].copy().fillna("")
    stats = {"before_count": len(frame)}
    frame["title"] = frame["title"].map(clean_title).replace("", "未命名视频")
    frame["up"] = frame["up"].str.strip().replace("", "未知UP主")
    frame["url"] = frame["url"].map(canonical_url)
    stats["invalid_urls"] = int(frame["url"].eq("").sum())
    frame = frame.loc[frame["url"].ne("")].copy()
    before_dedup = len(frame)
    frame = frame.drop_duplicates(subset="url", keep="first").copy()
    stats["removed_duplicates"] = before_dedup - len(frame)
    stats["filled_numeric_cells"] = 0
    stats["clipped_outlier_cells"] = 0
    for field in NUMERIC_FIELDS:
        values = frame[field].map(count_to_number)
        stats["filled_numeric_cells"] += int(values.isna().sum())
        values = values.fillna(0)
        q1, q3 = values.quantile([0.25, 0.75])
        iqr = q3 - q1
        # 使用 IQR 边界截尾而不是删视频，保留后续热度分析样本。
        if iqr > 0:
            lower, upper = max(0, q1 - 1.5 * iqr), q3 + 1.5 * iqr
            stats["clipped_outlier_cells"] += int(((values < lower) | (values > upper)).sum())
            values = values.clip(lower=lower, upper=upper)
        frame[field] = values.round().astype("int64")
    frame = frame.reset_index(drop=True)
    stats["after_count"] = len(frame)
    return frame, stats


def batch_table_name(collection_date, keyword):
    prefix = f"bilibili_video_data_{date.fromisoformat(collection_date):%Y%m%d}_"
    if not keyword:
        return prefix + "all"
    suffix = re.sub(r"[^A-Za-z0-9_\u4e00-\u9fff]", "_", keyword)
    if suffix != keyword or len(suffix) > 35 or suffix.lower() == "all":
        suffix = suffix[:26] + "_" + hashlib.sha256(keyword.encode("utf-8")).hexdigest()[:8]
    return prefix + suffix


def upload_to_hdfs(path):
    endpoint = config.HDFS_WEBHDFS_URL
    if urlsplit(endpoint).scheme not in ("http", "https"):
        raise ValueError("请在 .env 配置 HDFS_WEBHDFS_URL 后重启服务。")
    directory = config.HDFS_DATA_DIR.rstrip("/")
    if not directory.startswith("/") or ".." in directory.split("/"):
        raise ValueError("HDFS_DATA_DIR 必须是无上级跳转的绝对目录。")
    user = {"user.name": config.HDFS_USER} if config.HDFS_USER else {}
    # 虚拟机服务直接连接，避免本机代理拦截 WebHDFS 的 PUT 请求。
    opener = build_opener(ProxyHandler({}))

    def url(remote_path, **parameters):
        return endpoint + "/webhdfs/v1" + quote(remote_path, safe="/") + "?" + urlencode({**user, **parameters})

    with opener.open(Request(url(directory, op="MKDIRS"), data=b"", method="PUT"), timeout=5) as response:
        if not json.load(response).get("boolean"):
            raise RuntimeError("HDFS 目录创建失败。")
    remote_path = directory + "/" + path.name
    # WebHDFS 先向 NameNode 申请上传地址，再把文件发送给 DataNode。
    with opener.open(Request(url(remote_path, op="CREATE", overwrite="true", noredirect="true"), data=b"", method="PUT"), timeout=5) as response:
        location = json.load(response)["Location"]
    if urlsplit(location).scheme not in ("http", "https"):
        raise ValueError("HDFS 返回了无效的上传地址。")
    with opener.open(Request(location, data=path.read_bytes(), method="PUT", headers={"Content-Type": "application/octet-stream"}), timeout=10) as response:
        if response.status != 201:
            raise RuntimeError("HDFS 文件上传失败。")
    with opener.open(url(remote_path, op="GETFILESTATUS"), timeout=5) as response:
        if json.load(response)["FileStatus"]["length"] != path.stat().st_size:
            raise RuntimeError("HDFS 文件大小校验失败。")
    return remote_path


def preprocess_data(collection_date, keyword=""):
    batch_date = date.fromisoformat(collection_date)
    if collection_date != batch_date.isoformat():
        raise ValueError("采集日期请使用 YYYY-MM-DD 格式。")
    keyword = keyword.strip()
    if len(keyword) > 100:
        raise ValueError("关键词不能超过 100 个字符。")
    prefix = f"bilibili_video_data_{batch_date:%Y%m%d}_"
    paths = sorted(config.RAW_DATA_DIR.glob(prefix + "*.csv"))
    if keyword:
        safe_keyword = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", keyword).strip(". ") or "keyword"
        paths = [path for path in paths if path.name == prefix + safe_keyword + ".csv"]
    if not paths:
        raise FileNotFoundError("当前采集日期和关键词没有原始 CSV，请检查筛选条件。")
    frames = []
    for path in paths:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if not set(FIELDS).issubset(frame.columns):
            raise ValueError("有原始 CSV 缺少必需字段，请检查表头。")
        frames.append(frame[FIELDS])
    cleaned, result = clean_dataframe(pd.concat(frames, ignore_index=True))
    if cleaned.empty:
        raise ValueError("清洗后没有有效视频，未覆盖已有清洗文件或数据库表。")
    table = batch_table_name(collection_date, keyword)
    config.PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = config.PROCESSED_DATA_DIR / (table + ".csv")
    # 先写临时文件再替换，避免失败时损坏上一次清洗结果。
    descriptor, temporary = tempfile.mkstemp(dir=config.PROCESSED_DATA_DIR, suffix=".tmp")
    os.close(descriptor)
    try:
        cleaned.to_csv(temporary, index=False, encoding="utf-8-sig")
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    result.update(date=collection_date, keyword=keyword, source_files=len(paths),
                  filename=output.name, table_name=table, rows=cleaned.head(20).to_dict("records"))
    try:
        count = save_cleaned_data(cleaned, table)
        result["mysql_status"] = f"已写入 MySQL（{count} 条）"
        mysql_ok = True
    except ValueError as error:
        result["mysql_status"] = str(error)
        mysql_ok = False
    except pymysql.MySQLError as error:
        result["mysql_status"] = f"MySQL 写入失败（错误码 {error.args[0]}），请检查本地凭据、端口和建库权限。"
        mysql_ok = False
    except RuntimeError as error:
        result["mysql_status"] = str(error)
        mysql_ok = False
    if not config.HDFS_WEBHDFS_URL:
        result["hdfs_status"] = "HDFS 未配置，清洗文件已在本地保留。"
        hdfs_ok = False
    else:
        try:
            result["hdfs_path"] = upload_to_hdfs(output)
            result["hdfs_status"] = "已上传 HDFS，并核对文件大小。"
            hdfs_ok = True
        except (OSError, ValueError, KeyError, RuntimeError):
            result["hdfs_status"] = "HDFS 上传失败，本地文件保留，请检查虚拟机服务、网络和 HDFS 配置。"
            hdfs_ok = False
    result["storage_complete"] = mysql_ok and hdfs_ok
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="模块二：清洗采集批次并保存 CSV、MySQL、HDFS。")
    parser.add_argument("--date", required=True, help="采集日期，YYYY-MM-DD")
    parser.add_argument("--keyword", default="", help="留空处理该日期所有关键词并跨文件去重")
    args = parser.parse_args()
    try:
        result = preprocess_data(args.date, args.keyword)
        # 控制台只打印统计与存储状态，不打印标题或 UP 主信息。
        print(json.dumps({key: value for key, value in result.items() if key != "rows"}, ensure_ascii=False, indent=2))
    except (ValueError, OSError, pd.errors.ParserError) as error:
        parser.exit(1, f"预处理未完成：{error}\n")
