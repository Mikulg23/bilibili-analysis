"""小数据验证建库复用、检索、全量统计和旧索引失效，不调用真实模型。"""
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pandas as pd
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import AI_Knowledge as knowledge
from app import app
from pachong import FIELDS


if __name__ == "__main__":
    rows = [["TITLE_PLACEHOLDER_A", "https://www.bilibili.com/video/BV1234567890/", "UP_PLACEHOLDER", 10, 2, 1, 0, 0],
            ["TITLE_PLACEHOLDER_B", "https://www.bilibili.com/video/BV1234567891/", "UP_PLACEHOLDER", 20, 3, 2, 1, 0],
            ["TITLE_PLACEHOLDER_C", "https://www.bilibili.com/video/BV1234567892/", "UP_PLACEHOLDER_B", 20, 4, 2, 1, 0]]
    with TemporaryDirectory() as temporary:
        root = Path(temporary)
        source = root / "bilibili_video_data_20260101_all.csv"
        pd.DataFrame(rows, columns=FIELDS).to_csv(source, index=False, encoding="utf-8-sig")
        embedding = MagicMock()
        embedding.embed_documents.return_value = [[1, 0], [0, 1], [1, 1]]
        embedding.embed_query.return_value = [1, 0]
        with patch.object(knowledge.config, "PROCESSED_DATA_DIR", root), patch.object(knowledge.config, "KNOWLEDGE_DIR", root / "index"), patch.object(knowledge, "embedding_model", return_value=embedding):
            assert knowledge.build_knowledge("2026-01-01")["document_count"] == 3
            knowledge.build_knowledge("2026-01-01")
            assert embedding.embed_documents.call_count == 1
            result = knowledge.ask_knowledge("2026-01-01", "", "哪个 UP 主的视频最多？")
            assert result["method"] == "statistics" and "2 条" in result["answer"]
            result = knowledge.ask_knowledge("2026-01-01", "", "播放量最高的视频是哪个？")
            assert "2 条视频并列" in result["answer"] and len(result["sources"]) == 2
            name, frame, signature = knowledge.read_source("2026-01-01", "")
            assert knowledge.statistical_answer(frame, "Python 视频有多少条？") is None
            with patch.object(knowledge, "ChatOllama", return_value=RunnableLambda(lambda _: AIMessage(content="ANSWER_PLACEHOLDER [1]"))):
                result = knowledge.ask_knowledge("2026-01-01", "", "TITLE_PLACEHOLDER_A 有哪些信息？")
                assert result["method"] == "rag" and result["sources"][0]["title"] == "TITLE_PLACEHOLDER_A"
            embedding.embed_query.return_value = [-1, -1]
            result = knowledge.ask_knowledge("2026-01-01", "", "UNRELATED_QUESTION_PLACEHOLDER")
            assert "资料不足" in result["answer"] and result["sources"] == []
            index = root / "index" / (name + ".npz")
            original = index.read_bytes()
            source.write_bytes(source.read_bytes() + b"\n")
            try:
                knowledge.ask_knowledge("2026-01-01", "", "有多少条视频？")
                raise AssertionError("Stale index accepted")
            except ValueError:
                pass
            embedding.embed_documents.side_effect = ConnectionError("TEST_OFFLINE")
            try:
                knowledge.build_knowledge("2026-01-01")
                raise AssertionError("Failed embedding accepted")
            except ConnectionError:
                assert index.read_bytes() == original
    client = app.test_client()
    with patch.object(knowledge.config, "OLLAMA_BASE_URL", "https://example.invalid"):
        try:
            knowledge.embedding_model()
            raise AssertionError("Remote model endpoint accepted")
        except ValueError:
            pass
    assert client.post("/api/knowledge/build", json=[]).status_code == 400
    assert client.post("/api/knowledge/ask", json={"date": "BAD_DATE"}).status_code == 400
    assert client.post("/api/knowledge/build", json={"date": "2026-01-01"}, headers={"Origin": "https://example.invalid"}).status_code == 403
    print("PASS: build, reuse, retrieval, statistics, invalidation, failure preservation and API validation")
