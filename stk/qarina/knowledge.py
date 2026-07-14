"""
Knowledge persistence via LightRAG.
Indexes research reports into a knowledge graph for cross-session retrieval.
Uses OpenRouter for both LLM (entity extraction) and embeddings.
"""

import asyncio
import logging
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("knowledge")

KNOWLEDGE_DIR = os.environ.get(
    "KNOWLEDGE_DIR", str(Path(__file__).parent / "knowledge_store")
)
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "openai/text-embedding-3-small")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))

_rags = {}
_init_failed = set()
_loop = None
_lock = threading.Lock()
_loop_lock = threading.Lock()  # separate: _get_rag holds _lock while calling _run


def _ensure_loop():
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            t = threading.Thread(target=_loop.run_forever, daemon=True)
            t.start()
        return _loop


def _run(coro, timeout=120):
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def _namespace_key(namespace: int | str | None) -> str:
    if namespace is None:
        return "default"
    try:
        return f"user-{int(namespace)}"
    except (TypeError, ValueError) as exc:
        raise ValueError("Knowledge namespace must be a user ID") from exc


def _get_rag(namespace: int | str | None = None):
    key = _namespace_key(namespace)
    if key in _rags:
        return _rags[key]
    if key in _init_failed:
        return None

    with _lock:
        if key in _rags:
            return _rags[key]
        if key in _init_failed:
            return None

        try:
            from lightrag import LightRAG
            from lightrag.llm.openai import openai_complete_if_cache
            from lightrag.utils import EmbeddingFunc

            api_key = os.environ.get("OPENROUTER_API_KEY")
            if not api_key:
                log.warning("No OPENROUTER_API_KEY, knowledge disabled")
                _init_failed.add(key)
                return None

            base_url = "https://openrouter.ai/api/v1"
            model = os.environ.get(
                "KNOWLEDGE_MODEL", os.environ.get("MODEL", "deepseek/deepseek-chat")
            )

            async def llm_func(
                prompt, system_prompt=None, history_messages=None, **kwargs
            ):
                history_messages = history_messages or []
                return await openai_complete_if_cache(
                    model,
                    prompt,
                    system_prompt=system_prompt,
                    history_messages=history_messages,
                    api_key=api_key,
                    base_url=base_url,
                    **kwargs,
                )

            async def embed_func(texts: list[str]):
                import numpy as np
                from openai import AsyncOpenAI

                client = AsyncOpenAI(api_key=api_key, base_url=base_url)
                resp = await client.embeddings.create(
                    model=EMBEDDING_MODEL, input=texts
                )
                return np.array([d.embedding for d in resp.data])

            working_dir = Path(KNOWLEDGE_DIR) / key
            os.makedirs(working_dir, exist_ok=True)

            rag = LightRAG(
                working_dir=str(working_dir),
                llm_model_func=llm_func,
                embedding_func=EmbeddingFunc(
                    embedding_dim=EMBEDDING_DIM,
                    max_token_size=8192,
                    func=embed_func,
                ),
            )
            _run(rag.initialize_storages())
            _rags[key] = rag
            log.info(f"LightRAG initialized at {working_dir}")
            return rag

        except ImportError:
            log.warning("lightrag-hku not installed, knowledge disabled")
            _init_failed.add(key)
            return None
        except Exception as e:
            log.warning(f"LightRAG init failed: {e}")
            _init_failed.add(key)
            return None


def index_report(query: str, report: str, namespace: int | str | None = None):
    """Index a research report into the knowledge graph.

    Callers must pass the report body without the media appendix.
    """
    if not report or len(report) < 100:
        return
    clean = report.strip()
    rag = _get_rag(namespace)
    if not rag:
        return
    text = f"Research Query: {query}\n\n{clean}"
    try:
        _run(rag.ainsert(text))
        log.info(f"Indexed report for: {query[:80]}")
    except Exception as e:
        log.warning(f"Index failed: {e}")


def get_prior_knowledge(query: str, namespace: int | str | None = None) -> str | None:
    """Retrieve relevant prior knowledge for a query."""
    rag = _get_rag(namespace)
    if not rag:
        return None
    try:
        from lightrag import QueryParam

        result = _run(rag.aquery(query, param=QueryParam(mode="hybrid")))
        if not result:
            return None
        text = result.strip()
        # LightRAG returns filler text when the graph has no relevant data
        skip = (
            "sorry",
            "not able to",
            "no-context",
            "no context",
            "i don't have",
            "no information",
        )
        if len(text) < 30 or any(s in text.lower() for s in skip):
            return None
        return text[:3000]
    except Exception as e:
        log.warning(f"Knowledge query failed: {e}")
    return None


def shutdown():
    global _loop
    for rag in _rags.values():
        try:
            _run(rag.finalize_storages())
        except Exception:
            pass
    _rags.clear()
    if _loop and _loop.is_running():
        _loop.call_soon_threadsafe(_loop.stop)
        _loop = None
    _init_failed.clear()
