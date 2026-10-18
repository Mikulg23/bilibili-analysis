from datetime import date
from concurrent.futures import CancelledError
from threading import Event, Lock, Thread
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, url_for
from selenium.common.exceptions import WebDriverException

from pachong import collect_videos
from preprocessing import preprocess_data

app = Flask(__name__)
# 当前仅在本机提供采集预览，防止通过其他域名访问本地服务。
app.config["TRUSTED_HOSTS"] = ["127.0.0.1", "localhost"]
collection_lock = Lock()
collection_job = {"state": "idle"}
collection_stop = Event()
preprocessing_lock = Lock()


def run_collection(keyword, pages, collection_date):
    def update(progress):
        with collection_lock:
            collection_job.update(progress)

    try:
        result = collect_videos(keyword, pages, collection_date, on_progress=update, stop_event=collection_stop)
        with collection_lock:
            collection_job.update(result, state="stopped" if collection_stop.is_set() else "completed")
            if collection_stop.is_set():
                collection_job["message"] = "已停止采集，已写入的 CSV 数据保留。"
    except CancelledError as error:
        update({"state": "stopped", "message": str(error)})
    except WebDriverException:
        if collection_stop.is_set():
            update({"state": "stopped", "message": "已停止采集，已写入的 CSV 数据保留。"})
        else:
            update({"state": "error", "message": "Chrome 启动或连接失败，请检查浏览器与驱动配置。已写入的数据保留。"})
    except OSError:
        update({"state": "error", "message": "CSV 文件读写失败，请检查目录权限，或关闭正在占用文件的软件后重试。"})
    except (ValueError, RuntimeError) as error:
        update({"state": "error", "message": str(error)})
    except Exception:
        update({"state": "error", "message": "采集意外停止，已写入的数据保留，请检查配置后重试。"})


@app.get("/")
def home():
    return redirect(url_for("login"))


@app.get("/login")
def login():
    return render_template("login.html")

# 前端预览入口。
@app.get("/dashboard")
def dashboard():
    # 当前仅提供本地前端预览，业务接口接入时必须补充服务端鉴权。
    return render_template("index.html")


@app.post("/api/collect")
def start_collection():
    # 不接受其他网页发起的采集请求，也不允许表单跨站提交。
    if request.headers.get("Origin") not in (None, request.host_url.rstrip("/")):
        return jsonify(success=False, message="请从本机管理页面发起采集。"), 403
    if not request.is_json:
        return jsonify(success=False, message="请求必须使用 JSON。"), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(success=False, message="请求内容必须是 JSON 对象。"), 400
    keyword, pages, collection_date = data.get("keyword"), data.get("pages"), data.get("date")
    if not isinstance(keyword, str) or not 1 <= len(keyword.strip()) <= 100:
        return jsonify(success=False, message="关键词必须为 1–100 个字符。"), 400
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 100:
        return jsonify(success=False, message="采集页数必须是 1–100 的整数。"), 400
    try:
        if not isinstance(collection_date, str) or date.fromisoformat(collection_date).isoformat() != collection_date:
            raise ValueError
    except ValueError:
        return jsonify(success=False, message="采集日期请使用 YYYY-MM-DD 格式。"), 400
    with collection_lock:
        if preprocessing_lock.locked():
            return jsonify(success=False, message="正在预处理数据，请稍后再采集。"), 409
        if collection_job["state"] in ("running", "stopping"):
            return jsonify(success=False, message="已有采集任务正在运行，请等待当前任务结束。"), 409
        collection_job.clear()
        collection_stop.clear()
        collection_job.update(task_id=uuid4().hex, state="running", date=collection_date,
                              keyword=keyword.strip(), pages=pages, page=0, count=0,
                              new_count=0, failed_count=0, rows=[], filename="",
                              message="正在启动采集…")
        snapshot = dict(collection_job)
    # 单个后台线程即可，避免长采集占用请求或触发前端超时。
    Thread(target=run_collection, args=(keyword.strip(), pages, collection_date), daemon=True).start()
    return jsonify(success=True, message="采集任务已启动。", data=snapshot), 202


@app.post("/api/collect/stop")
def stop_collection():
    if request.headers.get("Origin") not in (None, request.host_url.rstrip("/")):
        return jsonify(success=False, message="请从本机管理页面停止采集。"), 403
    if not request.is_json:
        return jsonify(success=False, message="请求必须使用 JSON。"), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not data.get("task_id"):
        return jsonify(success=False, message="请提供要停止的任务编号。"), 400
    with collection_lock:
        if data["task_id"] != collection_job.get("task_id"):
            return jsonify(success=False, message="任务已变化，请先查看当前任务。"), 409
        if collection_job["state"] in ("running", "stopping"):
            collection_stop.set()
            collection_job.update(state="stopping", message="正在停止，等待当前浏览器请求结束；已保存的数据保留。")
        snapshot = dict(collection_job)
    return jsonify(success=True, message=snapshot["message"], data=snapshot)


@app.get("/api/collect/status")
def collection_status():
    with collection_lock:
        snapshot = dict(collection_job)
    return jsonify(success=True, message="当前采集状态。", data=snapshot)

#数据预处理
@app.post("/api/preprocess")
def preprocess():
    if request.headers.get("Origin") not in (None, request.host_url.rstrip("/")):
        return jsonify(success=False, message="请从本机管理页面执行预处理。"), 403
    if not request.is_json:
        return jsonify(success=False, message="请求必须使用 JSON。"), 415
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or not isinstance(data.get("date"), str) or not isinstance(data.get("keyword", ""), str):
        return jsonify(success=False, message="请提供采集日期和关键词。"), 400
    if not preprocessing_lock.acquire(blocking=False):
        return jsonify(success=False, message="已有预处理正在运行，请稍候。"), 409
    try:
        with collection_lock:
            if collection_job["state"] in ("running", "stopping"):
                return jsonify(success=False, message="请先停止数据采集，再执行预处理。"), 409
        result = preprocess_data(data["date"], data.get("keyword", ""))
        message = f"本地清洗完成：{result['before_count']} → {result['after_count']} 条。{result['mysql_status']}；{result['hdfs_status']}"
        return jsonify(success=True, message=message, data=result)
    except (ValueError, FileNotFoundError) as error:
        return jsonify(success=False, message=str(error)), 400
    except OSError:
        return jsonify(success=False, message="CSV 读写失败，请检查文件是否被占用及目录权限，原始数据未修改。"), 500
    except Exception:
        return jsonify(success=False, message="预处理未完成，原始数据已保留，请检查 CSV 格式与存储配置。"), 500
    finally:
        preprocessing_lock.release()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5002)
