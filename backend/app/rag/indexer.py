"""知识库索引器。

读取 knowledge/ 下的 Markdown 文档，按标题切分，
写入向量存储。场景由文件名推断。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from app.core.logging import get_logger
from app.rag.store import Document, VectorStore

logger = get_logger()

_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "knowledge"
# 文件名 -> 场景
# 注意：accessibility / transport 属跨场景通用内容，必须映射为 general，
# 否则会被 retrieve 的 scene 过滤（hospital / government）永久排除，
# 导致「无障碍服务」这类差异化知识根本召回不到。
_SCENE_MAP = {
    "hospital": "hospital",
    "government": "government",
    "accessibility": "general",
    "transport": "general",
}


def _infer_scene(filename: str) -> str:
    name = filename.lower()
    for key, scene in _SCENE_MAP.items():
        if key in name:
            return scene
    return "general"


def _split_by_headers(text: str) -> list[tuple[str, str]]:
    """按 Markdown 二/三级标题切分，返回 (标题, 正文)。"""
    chunks: list[tuple[str, str]] = []
    current_title = "概述"
    buf: list[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            chunks.append((current_title, body))
        buf.clear()

    for line in text.splitlines():
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            flush()
            current_title = m.group(2).strip()
        else:
            buf.append(line)
    flush()
    return chunks


async def index_knowledge(store: VectorStore, knowledge_dir: Path | None = None) -> int:
    """索引知识目录，返回切分文档数。"""
    kdir = (knowledge_dir or _KNOWLEDGE_DIR)
    if not kdir.exists():
        logger.warning("知识目录不存在：{}", kdir)
        return 0

    docs: list[Document] = []
    for md in sorted(kdir.glob("*.md")):
        scene = _infer_scene(md.name)
        text = md.read_text(encoding="utf-8")
        for title, body in _split_by_headers(text):
            # 跳过只有标题、没有实质内容的块（如文件开头的 "# 标题" 概述）
            if _is_noise_body(body):
                continue
            doc_id = hashlib.md5(f"{md.name}:{title}".encode()).hexdigest()
            full = f"{title}\n{body}"
            docs.append(
                Document(
                    id=doc_id,
                    text=full,
                    metadata={
                        "scene": scene,
                        "title": title,
                        "language": "zh",
                        "content_type": "text",
                        "source": md.name,
                    },
                )
            )

    await store.add(docs)
    logger.info("知识库索引完成：{} 个文档块", len(docs))
    return len(docs)


def _is_noise_body(body: str) -> bool:
    """正文是否只有标题（无实质内容）。"""
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not lines:
        return True
    return all(ln.startswith("#") for ln in lines)
