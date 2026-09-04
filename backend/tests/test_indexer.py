"""知识库索引器单元测试：文档切分、场景推断、噪声过滤。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.rag.indexer import _infer_scene, _is_noise_body, _split_by_headers, index_knowledge
from app.rag.store import InMemoryVectorStore


class TestSceneInference:
    """场景推断测试：文件名 → scene。"""

    def test_hospital(self):
        assert _infer_scene("hospital_guide.md") == "hospital"
        assert _infer_scene("hospital_departments.md") == "hospital"

    def test_government(self):
        assert _infer_scene("government_guide.md") == "government"
        assert _infer_scene("government_services.md") == "government"

    def test_accessibility(self):
        assert _infer_scene("accessibility_guide.md") == "accessibility"

    def test_unknown_returns_general(self):
        assert _infer_scene("random_file.md") == "general"
        assert _infer_scene("README.md") == "general"


class TestSplitByHeaders:
    """Markdown 文档切分测试。"""

    def test_split_by_h2(self):
        text = "## 第一节\n\n内容一\n\n## 第二节\n\n内容二"
        chunks = _split_by_headers(text)
        assert len(chunks) == 2
        assert chunks[0][0] == "第一节"
        assert "内容一" in chunks[0][1]
        assert chunks[1][0] == "第二节"
        assert "内容二" in chunks[1][1]

    def test_split_by_h3(self):
        text = "## 大节\n\n### 小节一\n\n内容A\n\n### 小节二\n\n内容B"
        chunks = _split_by_headers(text)
        assert len(chunks) == 2
        assert chunks[0][0] == "小节一"

    def test_no_headers_returns_overview(self):
        text = "只有正文，没有标题"
        chunks = _split_by_headers(text)
        assert len(chunks) == 1
        assert chunks[0][0] == "概述"

    def test_empty_text(self):
        chunks = _split_by_headers("")
        assert len(chunks) == 0


class TestNoiseFilter:
    """噪声正文过滤测试。"""

    def test_empty_body_is_noise(self):
        assert _is_noise_body("") is True
        assert _is_noise_body("   \n  \n  ") is True

    def test_only_headers_is_noise(self):
        assert _is_noise_body("# 标题\n## 子标题") is True

    def test_real_content_is_not_noise(self):
        assert _is_noise_body("这是一段真实的内容。") is False
        assert _is_noise_body("# 标题\n\n正文内容") is False


class TestIndexKnowledge:
    """知识库索引集成测试。"""

    @pytest.mark.asyncio
    async def test_index_md_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建测试 md 文件
            md_file = Path(tmpdir) / "hospital_test.md"
            md_file.write_text(
                "# 测试医院\n\n## 内科\n\n内科在1楼门诊大厅北侧。\n\n## 外科\n\n外科在2楼东侧。\n",
                encoding="utf-8",
            )

            store = InMemoryVectorStore()
            count = await index_knowledge(store, knowledge_dir=Path(tmpdir))
            assert count == 2  # 内科 + 外科

            # 验证检索
            results = await store.query("内科在哪里", k=2)
            assert len(results) > 0
            assert any("内科" in r.text for r in results)

    @pytest.mark.asyncio
    async def test_nonexistent_dir_returns_zero(self):
        store = InMemoryVectorStore()
        count = await index_knowledge(store, knowledge_dir=Path("/nonexistent/path"))
        assert count == 0
