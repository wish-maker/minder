"""RAG method orchestration for the rag-pipeline service.

The live query endpoint delegates to :func:`rag.runner.run_query`, which selects a
retrieval/generation strategy per request. Each method lives in its own module under
``rag.methods`` and is invoked through the runner — see #45.
"""
