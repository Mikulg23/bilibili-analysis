"""轻量接口自检，不打开浏览器、不采集真实数据。"""
import sys
import csv
import tempfile
from concurrent.futures import CancelledError
from pathlib import Path
from threading import Event
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as application
import pachong


if __name__ == "__main__":
    client = application.app.test_client()
    assert client.get("/api/collect/status").json["data"]["state"] == "idle"
    data = {"date": "2026-10-17", "keyword": "KEYWORD_PLACEHOLDER", "pages": 1}
    assert client.post("/api/collect", json={**data, "pages": True}).status_code == 400
    assert client.post("/api/collect", json={**data, "date": "not-a-date"}).status_code == 400
    assert client.post("/api/collect", json=data, headers={"Origin": "https://invalid.example"}).status_code == 403
    # 用空线程验证启动与互斥，不触发真正的 Selenium 采集。
    with patch("app.Thread") as thread:
        result = client.post("/api/collect", json=data)
        assert result.status_code == 202
        assert result.json["data"]["task_id"]
        thread.return_value.start.assert_called_once()
        assert client.post("/api/collect", json=data).status_code == 409
    task_id = result.json["data"]["task_id"]
    assert client.post("/api/collect/stop", json={"task_id": "WRONG_ID"}).status_code == 409
    assert client.post("/api/collect/stop", json={"task_id": task_id}, headers={"Origin": "https://invalid.example"}).status_code == 403
    stopped = client.post("/api/collect/stop", json={"task_id": task_id})
    assert stopped.json["data"]["state"] == "stopping"
    assert application.collection_stop.is_set()
    assert client.post("/api/collect", json=data).status_code == 409
    with patch("app.collect_videos", side_effect=CancelledError("STOP_SELF_CHECK")):
        application.run_collection(data["keyword"], data["pages"], data["date"])
    assert client.get("/api/collect/status").json["data"]["state"] == "stopped"
    with patch("app.Thread"):
        assert client.post("/api/collect", json=data).status_code == 202
        assert not application.collection_stop.is_set()
    with patch("app.collect_videos", side_effect=RuntimeError("SELF_CHECK")):
        application.run_collection(data["keyword"], data["pages"], data["date"])
    status = client.get("/api/collect/status").json["data"]
    assert status["state"] == "error" and status["message"] == "SELF_CHECK"
    assert client.get("/dashboard").status_code == 200

    # 模拟在等待搜索结果时停止，确认关闭浏览器且不损坏旧 CSV。
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "bilibili_video_data_20261017_KEYWORD_PLACEHOLDER.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=pachong.FIELDS)
            writer.writeheader()
            writer.writerow(dict.fromkeys(pachong.FIELDS, "VALUE_PLACEHOLDER"))
        original = path.read_bytes()
        cancel = Event()
        driver = MagicMock()
        driver.find_elements.side_effect = lambda *args: cancel.set() or []
        with patch("config.RAW_DATA_DIR", root), patch("pachong.webdriver.Chrome", return_value=driver) as chrome:
            try:
                pachong.collect_videos(data["keyword"], 1, data["date"], headless=True, stop_event=cancel)
                raise AssertionError("Cancellation was ignored")
            except CancelledError:
                pass
            assert "--headless=new" in chrome.call_args.kwargs["options"].arguments
        driver.quit.assert_called_once()
        assert path.read_bytes() == original
    print("PASS: stop API, restart, cancellation, browser cleanup and preserved CSV")
