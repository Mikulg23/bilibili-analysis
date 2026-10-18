"""小规模计算、模型批次校验与请求校验，不读写真实 MySQL。"""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import joblib
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import machine_kmeans as mining
from app import app


if __name__ == "__main__":
    frame = pd.DataFrame([[value] * 5 for value in [0] * 4 + [10] * 4], columns=mining.FEATURES)
    frame["id"] = range(1, 9)
    frame["url"] = [f"URL_PLACEHOLDER_{index}" for index in range(8)]
    frame["title"] = "TITLE_PLACEHOLDER"
    model, scaler, labels, elbow = mining.fit_clusters(frame)
    assert model.n_clusters == 2 and elbow["k"] == [1, 2]
    assert elbow["sse"][0] > elbow["sse"][1]
    frame["cluster"] = model.labels_
    frame["label"] = frame["cluster"].map(labels)
    assert labels[int(model.predict(scaler.transform(frame[mining.FEATURES].iloc[[0]]))[0])] == "普通热度"
    assert labels[int(model.predict(scaler.transform(frame[mining.FEATURES].iloc[[-1]]))[0])] == "高热度（爆款候选）"
    rules = mining.mine_rules(frame)
    assert rules and all(row["support"] == 0.5 and row["confidence"] == 1 and row["lift"] == 2 for row in rules)
    assert mining.mine_rules(frame.iloc[:4]) == []
    bundle = {"model": model, "labels": labels, "elbow": elbow,
              "signature": mining.data_signature(frame), "training_id": "TEST"}
    with TemporaryDirectory() as temporary, patch.object(mining.config, "MODELS_DIR", Path(temporary)):
        directory = Path(temporary) / "TEST_BATCH"
        directory.mkdir()
        joblib.dump(bundle, directory / "cluster_model.pkl")
        joblib.dump({"scaler": scaler, "training_id": "TEST"}, directory / "scaler.pkl")
        assert mining.load_model("TEST_BATCH", frame)[0]["signature"] == bundle["signature"]
        changed = frame.copy()
        changed.loc[0, "play"] = 1
        try:
            mining.load_model("TEST_BATCH", changed)
            raise AssertionError("Stale model accepted")
        except ValueError:
            pass
        with patch.object(mining, "read_data", return_value=("TEST_BATCH", frame)):
            assert mining.predict_video("2026-01-01", "", dict.fromkeys(mining.FEATURES, 10))["label"] == "高热度（爆款候选）"
    try:
        mining.predict_video("2026-01-01", "", dict.fromkeys(mining.FEATURES, True))
        raise AssertionError("Boolean features accepted")
    except ValueError:
        pass
    client = app.test_client()
    assert client.get("/api/mining/clusters?date=BAD_DATE").status_code == 400
    assert client.post("/api/mining/train", json=[]).status_code == 400
    assert client.post("/api/mining/train", json={"date": "2026-01-01"}, headers={"Origin": "https://example.invalid"}).status_code == 403
    print("PASS: clustering, prediction, rules, stale models and API input validation")
