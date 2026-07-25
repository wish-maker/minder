# Performance / load tests

Home for throughput and latency tests. These are **not** part of the default CI
suite (mark them `@pytest.mark.load` and/or `@pytest.mark.slow`).

There is no bundled load harness — write one against your own deployment, since the
LLM at `OLLAMA_BASE_URL` is almost always the limiting factor and results depend on
the model you actually run. [Locust](https://locust.io/) is a good fit:

```bash
pip install locust
# write a locustfile.py that drives your real endpoints, e.g. POST /pipeline/{id}/query
locust -f locustfile.py --host http://localhost:8000
```

See [`docs/guides/performance.md`](../../docs/guides/performance.md) for tuning notes.
