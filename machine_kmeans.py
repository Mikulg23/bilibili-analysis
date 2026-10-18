"""模块四：K-Means 热度聚类、预测与 Apriori 关联规则。"""
import hashlib
import re
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
from mlxtend.frequent_patterns import apriori, association_rules
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

import config
from db import get_connection
from preprocessing import batch_table_name

FEATURES = ["play", "like", "coin", "favorite", "share"]
INTERACTIONS = {"like": "高点赞", "coin": "高投币", "favorite": "高收藏", "share": "高转发"}


def read_data(collection_date, keyword):
    table_name = batch_table_name(collection_date, keyword)
    if len(table_name) > 64 or not re.fullmatch(r"bilibili_video_data_\d{8}_[A-Za-z0-9_\u4e00-\u9fff]+", table_name):
        raise ValueError("数据表名不合法。")
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
                           (config.MYSQL_DATABASE, table_name))
            if cursor.fetchone() is None:
                raise ValueError("该批次尚未写入 MySQL，请先执行数据预处理；关键词留空对应当日合并表。")
            cursor.execute(f"SELECT * FROM `{table_name}` ORDER BY id")
            frame = pd.DataFrame(cursor.fetchall(), columns=[column[0] for column in cursor.description])
    if frame.empty:
        raise ValueError("该批次没有清洗数据，请先完成数据预处理。")
    values = frame[FEATURES].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("数据包含无效数值，请先重新预处理。")
    return table_name, frame


def data_signature(frame):
    # 预处理重新写表后，旧模型不能用于已经变化的数据。
    hashes = pd.util.hash_pandas_object(frame[["id", "url"] + FEATURES], index=False)
    return hashlib.sha256(hashes.values.tobytes()).hexdigest()


def fit_clusters(frame):
    if len(frame[FEATURES].drop_duplicates()) < 2:
        raise ValueError("至少需要两组不同的数值特征，才能区分视频热度。")
    scaler = StandardScaler()
    values = scaler.fit_transform(frame[FEATURES])
    ks = list(range(1, min(10, len(frame[FEATURES].drop_duplicates())) + 1))
    models = [KMeans(n_clusters=k, random_state=42, n_init=10).fit(values) for k in ks]
    sse = np.array([model.inertia_ for model in models])
    # 将 K 与 SSE 归一化，取下降曲线到首尾连线距离最大的肘点。
    x = (np.array(ks) - 1) / (ks[-1] - 1)
    y = (sse - sse[-1]) / (sse[0] - sse[-1])
    distances = 1 - x - y
    index = int(np.argmax(distances)) if distances.max() > 1e-8 else 1
    model = models[index]
    # 标准化后的五项特征等权计算热度，最高中心为爆款候选。
    hot_cluster = int(np.argmax(model.cluster_centers_.mean(axis=1)))
    labels = {cluster: "高热度（爆款候选）" if cluster == hot_cluster else "普通热度"
              for cluster in range(model.n_clusters)}
    return model, scaler, labels, {"k": ks, "sse": sse.tolist()}


def cluster_result(frame, bundle):
    counts = frame.groupby("cluster").size()
    return {"optimal_k": bundle["model"].n_clusters, "elbow": bundle["elbow"],
            "distribution": [{"name": f"聚类 {int(cluster)} · {bundle['labels'][int(cluster)]}", "value": int(count)}
                             for cluster, count in counts.items()],
            "rows": frame[["title"] + FEATURES + ["cluster", "label"]].head(20).to_dict("records"),
            "video_count": len(frame)}


def train_models(collection_date, keyword=""):
    table_name, frame = read_data(collection_date, keyword)
    model, scaler, labels, elbow = fit_clusters(frame)
    frame["cluster"] = model.labels_.astype(int)
    frame["label"] = frame["cluster"].map(labels)
    # 旧批次表按需补列，原始八个字段保持不变。
    with get_connection() as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(f"SHOW COLUMNS FROM `{table_name}`")
                columns = {row[0] for row in cursor.fetchall()}
                for name, sql_type in (("cluster", "INT NULL"), ("label", "VARCHAR(32) NULL")):
                    if name not in columns:
                        cursor.execute(f"ALTER TABLE `{table_name}` ADD COLUMN `{name}` {sql_type}")
                connection.begin()
                cursor.executemany(f"UPDATE `{table_name}` SET cluster=%s, label=%s WHERE id=%s",
                                   list(frame[["cluster", "label", "id"]].itertuples(index=False, name=None)))
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    training_id = uuid4().hex
    bundle = {"model": model, "labels": labels, "elbow": elbow,
              "signature": data_signature(frame), "training_id": training_id}
    directory = config.MODELS_DIR / table_name
    directory.mkdir(parents=True, exist_ok=True)
    # 先写临时文件；两文件携带相同编号，意外中断时不会混用不同次训练。
    for name, value in (("scaler.pkl", {"scaler": scaler, "training_id": training_id}),
                        ("cluster_model.pkl", bundle)):
        temporary = directory / (name + ".tmp")
        try:
            joblib.dump(value, temporary)
            temporary.replace(directory / name)
        finally:
            temporary.unlink(missing_ok=True)
    return cluster_result(frame, bundle)


def load_model(table_name, frame):
    directory = config.MODELS_DIR / table_name
    if not all((directory / name).is_file() for name in ("cluster_model.pkl", "scaler.pkl")):
        raise ValueError("该批次尚未训练，请先点击“训练聚类模型”。")
    # 仅加载本项目生成、被 Git 忽略的本地模型文件。
    bundle = joblib.load(directory / "cluster_model.pkl")
    saved_scaler = joblib.load(directory / "scaler.pkl")
    if (bundle["training_id"] != saved_scaler["training_id"] or bundle["signature"] != data_signature(frame)
            or not {"cluster", "label"}.issubset(frame.columns) or frame[["cluster", "label"]].isna().any().any()):
        raise ValueError("数据已变化或模型文件不完整，请重新训练该批次模型。")
    return bundle, saved_scaler["scaler"]


def get_clusters(collection_date, keyword=""):
    table_name, frame = read_data(collection_date, keyword)
    bundle, _ = load_model(table_name, frame)
    return cluster_result(frame, bundle)


def predict_video(collection_date, keyword, features):
    values = [features.get(name) for name in FEATURES]
    if any(isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2 ** 53 - 1 for value in values):
        raise ValueError("五项特征必须是非负整数，且不超过 9007199254740991。")
    table_name, frame = read_data(collection_date, keyword)
    bundle, scaler = load_model(table_name, frame)
    sample = pd.DataFrame([values], columns=FEATURES)
    cluster = int(bundle["model"].predict(scaler.transform(sample))[0])
    return {"cluster": cluster, "label": bundle["labels"][cluster]}


def mine_rules(frame):
    # 每条视频是一笔交易，“高互动”表示高于本批次中位数且大于零。
    thresholds = {name: float(frame[name].median()) for name in INTERACTIONS}
    transactions = pd.DataFrame({label: frame[name] > max(thresholds[name], 0)
                                 for name, label in INTERACTIONS.items()})
    itemsets = apriori(transactions, min_support=0.1, use_colnames=True)
    if itemsets.empty:
        return []
    rules = association_rules(itemsets, num_itemsets=len(frame), metric="confidence", min_threshold=0.6)
    rules = rules[rules["lift"] >= 1].sort_values(["confidence", "lift", "support"], ascending=False)
    return [{"antecedents": sorted(row["antecedents"]), "consequents": sorted(row["consequents"]),
             "support": round(float(row["support"]), 4), "confidence": round(float(row["confidence"]), 4),
             "lift": round(float(row["lift"]), 4)} for _, row in rules.iterrows()]


def get_rules(collection_date, keyword=""):
    _, frame = read_data(collection_date, keyword)
    return {"rules": mine_rules(frame)}
