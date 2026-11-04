# ============================================================
# persistent_knowledge.py —— docs 目录 + Chroma 持久化知识库
# ============================================================
"""启动时扫描本地文档，入库后由页面刷新复用同一个 Chroma 实例。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import streamlit as st

import config
from rag import chunk_text, extract_text, model
from vectorstore import ChromaVectorStore


@dataclass(frozen=True)
class ImportResult:
    """一次文件导入的结果。"""

    status: str
    chunks: int = 0
    message: str = ""
    source: str = ""


class PersistentKnowledge:
    """docs 目录为核心来源，网页上传作为补充来源。"""

    def __init__(self) -> None:
        self.store = ChromaVectorStore(config.CHROMA_DIR, client_id="webapp")
        self.store.persist()
        self.last_sync_errors: list[str] = []
        self.sync_documents()

    def _source_id(self, origin: str, filename: str, digest: str) -> str:
        return f"{origin}|{filename}|{digest}"

    @staticmethod
    def _display_name(source: str) -> str:
        parts = source.split("|")
        return parts[1] if len(parts) >= 3 else source

    @staticmethod
    def _content_digest(raw: bytes) -> str:
        return hashlib.sha256(raw).hexdigest()[:16]

    def _has_content(self, digest: str) -> bool:
        suffix = f"|{digest}"
        return any(source.endswith(suffix) for source in self.store.sources())

    def _remove_old_versions(
        self,
        origin: str,
        filename: str,
        keep_source: str | None = None,
    ) -> None:
        prefix = f"{origin}|{filename}|"
        for source in self.store.sources():
            if source.startswith(prefix) and source != keep_source:
                self.store.remove_source(source)

    def _remove_missing_documents(self, current_names: set[str]) -> None:
        """docs 中被删除的 PDF/TXT 同步清理，上传文档不受影响。"""
        for source in self.store.sources():
            if not source.startswith("docs|"):
                continue
            filename = self._display_name(source)
            if filename not in current_names:
                self.store.remove_source(source)

    def add_document(
        self,
        filename: str,
        raw: bytes,
        origin: str = "upload",
    ) -> ImportResult:
        """解析并向量化文件；内容哈希相同则复用已有向量。"""
        origin = origin.strip() or "upload"
        digest = self._content_digest(raw)
        if self._has_content(digest):
            return ImportResult(
                "exists",
                source=self._source_id(origin, filename, digest),
            )

        text = extract_text(filename, raw)
        if text is None:
            return ImportResult("failed", message="无法解析文件或格式不受支持。")

        chunks = chunk_text(text)
        if not chunks:
            return ImportResult("empty", message="文件中没有可用的文字内容。")

        try:
            vectors = model.encode(chunks)
        except Exception as exc:
            return ImportResult("error", message=f"生成向量失败：{exc}")

        source = self._source_id(origin, filename, digest)
        # 先写新版本，再删旧版本；Embedding 短暂失败时不会丢掉旧文档。
        self.store.add(chunks, vectors, source=source)
        self._remove_old_versions(origin, filename, keep_source=source)
        return ImportResult("added", len(chunks), source=source)

    def sync_documents(self) -> list[tuple[str, ImportResult]]:
        """只扫描 docs 下的 .txt 和 .pdf；旧文件靠内容哈希跳过。"""
        config.DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
        document_paths = sorted(
            path
            for path in config.DOCUMENTS_DIR.rglob("*")
            if path.is_file() and path.suffix.lower() in {".txt", ".pdf"}
        )
        current_names = {
            path.relative_to(config.DOCUMENTS_DIR).as_posix()
            for path in document_paths
        }
        self._remove_missing_documents(current_names)

        results: list[tuple[str, ImportResult]] = []
        self.last_sync_errors = []
        for path in document_paths:
            filename = path.relative_to(config.DOCUMENTS_DIR).as_posix()
            try:
                result = self.add_document(filename, path.read_bytes(), origin="docs")
            except Exception as exc:
                result = ImportResult("error", message=str(exc))

            if result.status == "error":
                self.last_sync_errors.append(f"{filename}: {result.message}")
            results.append((filename, result))
        return results

    def clear_uploads(self) -> None:
        """只清空网页上传来源，docs 里的核心知识库保持不变。"""
        for source in self.store.sources():
            if source.startswith("upload|"):
                self.store.remove_source(source)

    def search(self, vector, limit: int) -> list[str]:
        return self.store.query(vector, limit)

    def count(self) -> int:
        return self.store.count()

    def info(self) -> dict:
        sources = self.store.sources()
        return {
            "documents": sum(source.startswith("docs|") for source in sources),
            "uploads": sum(source.startswith("upload|") for source in sources),
            "chunks": self.store.count(),
        }


@st.cache_resource(show_spinner="正在加载本地知识库...")
def get_persistent_knowledge() -> PersistentKnowledge:
    """进程级缓存 Chroma；页面刷新直接复用已入库向量。"""
    return PersistentKnowledge()
