from types import SimpleNamespace

import rag


def test_local_embeddings_encode(monkeypatch):
    class FakeSentenceTransformer:
        def __init__(self, model_name, **kwargs):
            self.model_name = model_name
            self.kwargs = kwargs

        def embed_documents(self, texts):
            return [[float(index), 1.0] for index, _ in enumerate(texts)]

    init_kwargs = {}

    def fake_sentence_transformer(model_name, **kwargs):
        init_kwargs["model_name"] = model_name
        init_kwargs.update(kwargs)
        return FakeSentenceTransformer(model_name, **kwargs)

    monkeypatch.setattr(rag, "SentenceTransformer", fake_sentence_transformer)
    embeddings = rag.LocalEmbeddings("fake-model")
    result = embeddings.encode(["一", "二", "三"])

    assert init_kwargs["model_name"] == "fake-model"
    assert init_kwargs["local_files_only"] is True
    assert result.shape == (3, 2)


def test_extract_text_handles_scanned_pdf(monkeypatch):
    warnings = []
    monkeypatch.setattr(rag.st, "warning", lambda message: warnings.append(message))

    assert rag.extract_text("scanned.pdf", b"not-a-valid-pdf") is None
    assert warnings == ["该 PDF 可能是扫描件，请上传文本版 PDF。"]
