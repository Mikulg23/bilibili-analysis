import argparse
import csv
import random
import re
from concurrent.futures import CancelledError
from datetime import date
from threading import Event
from urllib.parse import quote

from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

import config

# CSV 与前端共用字段名，数值单位留给模块二清洗。
FIELDS = ["title", "url", "up", "play", "like", "coin", "favorite", "share"]


def metric_text(driver, selector):
    for element in driver.find_elements(By.CSS_SELECTOR, selector):
        text = element.text.strip()
        if re.search(r"\d", text):
            return text
    return ""


def check_stop(stop_event):
    if stop_event.is_set():
        raise CancelledError("已停止采集，已写入的 CSV 数据保留。")


def read_video(driver, url, stop_event):
    check_stop(stop_event)
    driver.get(url)
    check_stop(stop_event)
    wait = WebDriverWait(driver, config.CRAWLER_WAIT_SECONDS)
    wait.until(lambda d: check_stop(stop_event) or (d.find_elements(By.CSS_SELECTOR, "h1.video-title")
               and d.find_elements(By.CSS_SELECTOR, "a.up-name")
               and d.find_elements(By.CSS_SELECTOR, ".video-like")
               and metric_text(d, ".view-text")))
    return {
        "title": driver.find_element(By.CSS_SELECTOR, "h1.video-title").text.strip(),
        "url": url,
        "up": driver.find_element(By.CSS_SELECTOR, "a.up-name").text.strip(),
        "play": metric_text(driver, ".view-text"),
        "like": metric_text(driver, ".video-like"),
        "coin": metric_text(driver, ".video-coin"),
        "favorite": metric_text(driver, ".video-fav"),
        "share": metric_text(driver, ".video-share"),
    }

#采集视频
def collect_videos(keyword, pages, collection_date, limit=None, headless=None, on_progress=None, stop_event=None):
    if stop_event is None:
        stop_event = Event()
    check_stop(stop_event)
    keyword = keyword.strip()
    if not keyword or len(keyword) > 100:
        raise ValueError("关键词必须为 1–100 个字符。")
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 100:
        raise ValueError("采集页数必须是 1–100 的整数。")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ValueError("条数上限必须是正整数。")
    batch_date = date.fromisoformat(collection_date)
    if collection_date != batch_date.isoformat():
        raise ValueError("采集日期请使用 YYYY-MM-DD 格式。")
    if not 0 < config.CRAWLER_DELAY_MIN <= config.CRAWLER_DELAY_MAX or config.CRAWLER_WAIT_SECONDS < 1:
        raise ValueError("等待时间必须为正数，最大间隔不能小于最小间隔。")

    safe_keyword = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", keyword).strip(". ") or "keyword"
    config.RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    output = config.RAW_DATA_DIR / f"bilibili_video_data_{batch_date:%Y%m%d}_{safe_keyword}.csv"
    seen = set()
    preview = []
    # 重复运行同一批次时追加新视频，不覆盖已有数据。
    if output.exists() and output.stat().st_size:
        with output.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames != FIELDS:
                raise ValueError("已有 CSV 的字段不匹配，请先移动旧文件后再采集。")
            for row in reader:
                check_stop(stop_event)
                seen.add(row["url"])
                if len(preview) < 20:
                    preview.append(row)

    progress = {
        "date": collection_date, "keyword": keyword, "pages": pages,
        "page": 0, "count": len(seen), "new_count": 0, "failed_count": 0,
        "filename": output.name, "rows": preview, "message": "正在启动 Chrome…",
    }

    def report(text):
        progress["message"] = text
        if on_progress:
            on_progress({**progress, "rows": list(preview)})

    report("正在启动 Chrome，首次使用可能需要下载匹配的驱动。")
    check_stop(stop_event)
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    options.add_argument("--mute-audio")
    options.add_argument("--autoplay-policy=user-gesture-required")
    options.add_argument("--window-size=1440,1000")
    if config.CHROME_BINARY:
        options.binary_location = config.CHROME_BINARY
    if headless is None:
        headless = config.CRAWLER_HEADLESS
    if headless:
        options.add_argument("--headless=new")
    service = Service(config.CHROMEDRIVER_PATH) if config.CHROMEDRIVER_PATH else Service()
    driver = webdriver.Chrome(service=service, options=options)
    page_results = set()
    consecutive_failures = 0
    try:
        check_stop(stop_event)
        driver.set_page_load_timeout(config.CRAWLER_WAIT_SECONDS)
        needs_header = not output.exists() or output.stat().st_size == 0
        with output.open("a", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            if needs_header:
                writer.writeheader()
                stream.flush()
            for page in range(1, pages + 1):
                check_stop(stop_event)
                progress["page"] = page
                report(f"正在读取第 {page}/{pages} 页搜索结果…")
                # 日期仅用于采集批次，不加入视频发布时间筛选。
                try:
                    check_stop(stop_event)
                    driver.get(f"https://search.bilibili.com/video?keyword={quote(keyword)}&page={page}")
                    check_stop(stop_event)
                    WebDriverWait(driver, config.CRAWLER_WAIT_SECONDS).until(
                        lambda d: check_stop(stop_event) or (
                            d.find_elements(By.CSS_SELECTOR, '.bili-video-card a[href*="/video/BV"]')
                            or d.find_elements(By.CSS_SELECTOR, ".search-empty, .search-nothing")))
                except TimeoutException as error:
                    check_stop(stop_event)
                    raise RuntimeError("搜索页未能加载，可能需要登录或人工验证；已采集数据已保留。") from error
                # 随机延时可以被停止信号立即打断。
                stop_event.wait(random.uniform(config.CRAWLER_DELAY_MIN, config.CRAWLER_DELAY_MAX))
                check_stop(stop_event)
                urls = []
                for link in driver.find_elements(By.CSS_SELECTOR, '.bili-video-card a[href*="/video/BV"]'):
                    match = re.search(r"/video/(BV[0-9A-Za-z]{10})(?:[/?#]|$)", link.get_attribute("href") or "")
                    if match:
                        url = f"https://www.bilibili.com/video/{match.group(1)}/"
                        if url not in urls:
                            urls.append(url)
                if not urls:
                    report("搜索结果已结束。")
                    break
                fingerprint = tuple(urls)
                if fingerprint in page_results:
                    report("搜索结果出现重复页，已停止翻页，避免重复请求。")
                    break
                page_results.add(fingerprint)
                for url in urls:
                    check_stop(stop_event)
                    if url in seen:
                        continue
                    if limit is not None and progress["new_count"] >= limit:
                        break
                    stop_event.wait(random.uniform(config.CRAWLER_DELAY_MIN, config.CRAWLER_DELAY_MAX))
                    check_stop(stop_event)
                    try:
                        row = read_video(driver, url, stop_event)
                    except (TimeoutException, WebDriverException):
                        check_stop(stop_event)
                        progress["failed_count"] += 1
                        consecutive_failures += 1
                        report("有视频未能读取，已跳过；已保存的数据不受影响。")
                        if consecutive_failures >= 3:
                            raise RuntimeError("连续三条视频读取失败，已停止。请检查网络或在浏览器中处理登录/验证后重试。")
                        continue
                    consecutive_failures = 0
                    check_stop(stop_event)
                    writer.writerow(row)
                    stream.flush()
                    seen.add(url)
                    progress["count"] = len(seen)
                    progress["new_count"] += 1
                    if len(preview) < 20:
                        preview.append(row)
                    report(f"第 {page}/{pages} 页，累计 {progress['count']} 条，新增 {progress['new_count']} 条。")
                if limit is not None and progress["new_count"] >= limit:
                    break
    finally:
        try:
            driver.quit()
        except WebDriverException:
            if not stop_event.is_set():
                raise
    check_stop(stop_event)
    if progress["count"] == 0:
        raise RuntimeError("没有采集到视频数据，请更换关键词或检查页面是否需要验证。")
    report(f"采集结束：新增 {progress['new_count']} 条，文件累计 {progress['count']} 条，跳过失败 {progress['failed_count']} 条。")
    return progress


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B 站搜索视频采集，日期表示采集批次。")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument("--pages", type=int, default=1, help="采集页数，1–100")
    parser.add_argument("--date", default=date.today().isoformat(), help="采集日期，YYYY-MM-DD")
    parser.add_argument("--limit", type=int, help="本次新增条数上限，适合小样本试跑")
    browser_mode = parser.add_mutually_exclusive_group()
    browser_mode.add_argument("--headless", action="store_true", default=None, help="不显示浏览器窗口（默认）")
    browser_mode.add_argument("--show-browser", dest="headless", action="store_false", default=None, help="显示浏览器，便于排查登录或验证")
    args = parser.parse_args()
    try:
        result = collect_videos(args.keyword, args.pages, args.date, args.limit, args.headless,
                                lambda progress: print(progress["message"], flush=True))
        print(f"CSV 已保存到 data/raw/{result['filename']}")
    except (ValueError, RuntimeError, WebDriverException, OSError) as error:
        parser.exit(1, f"采集停止：{error}\n")
    except CancelledError as error:
        parser.exit(130, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(130, "\n已停止采集，已写入的 CSV 数据保留。\n")
