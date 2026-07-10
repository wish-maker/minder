"""Per-method RAG strategies, each in its own module.

- ``hyde``     — Hypothetical Document Embeddings query rewrite
- ``self_rag`` — quality-based iterative refinement generation
- ``decision`` — the agent decision engine for ``method=auto`` routing

Each function takes its dependencies explicitly so nothing here imports the service
entrypoint (``main``); this keeps the import graph acyclic.
"""
