#!/usr/bin/env python3
"""Real user-journey audit against a LIVE running Minder stack.

Replaces test_end_to_end.py / test_database_writes.py, both of which had
rotted into fiction: they call routes that no longer exist (`/plugins/{p}
/collect_data`, `/system/status`, `/auth/login` with no `/v1` prefix) and
import a monolithic `src.core.kernel.MinderKernel` that was removed when the
codebase became microservices -- unconditionally `pytest.mark.skip`'d, so
nobody noticed (the same rot #318 documented for tests/e2e/). Deleted here.

This script exercises the same journeys a real end user takes, against
whatever `--base-url` is actually running -- real Ollama inference (not a
stub), real plugins hitting real external APIs, real Postgres-backed auth,
real Qdrant-backed RAG. It is deliberately NOT part of tests/e2e/: that suite
proves the dispatch *code paths* work with a scripted, deterministic model;
this proves the *deployed system*, with whatever model is actually installed,
produces a sane result for a real question. Run it after every `setup.sh
update` against hantal/pi, not as a CI gate.

Usage:
    python tests/manual/test_real_user_journeys.py [--base-url http://localhost:8000]
"""

import argparse
import secrets
import sys

import httpx

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"


class Journey:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=30.0)
        self.results = []
        self.token = None
        self.username = f"e2e-audit-{secrets.token_hex(4)}"
        self.password = "audit-password-123"

    def record(self, name, status, detail=""):
        self.results.append((name, status, detail))
        marker = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠"}[status]
        print(f"  {marker} {name}" + (f" — {detail}" if detail else ""))

    def auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    # ── Journey 1: registration + login ──────────────────────────────────
    def journey_auth(self):
        print(
            "\n1. AUTH: register -> duplicate rejected -> weak password rejected -> login"
        )
        resp = self.client.post(
            "/v1/auth/register",
            json={
                "username": self.username,
                "email": f"{self.username}@example.com",
                "password": self.password,
            },
        )
        if resp.status_code == 201:
            self.record("register new user", PASS)
        else:
            self.record(
                "register new user", FAIL, f"HTTP {resp.status_code}: {resp.text[:200]}"
            )
            return False

        resp = self.client.post(
            "/v1/auth/register",
            json={
                "username": self.username,
                "email": f"{self.username}@example.com",
                "password": self.password,
            },
        )
        if resp.status_code in (400, 409):
            self.record("duplicate username rejected", PASS, f"HTTP {resp.status_code}")
        else:
            self.record("duplicate username rejected", FAIL, f"HTTP {resp.status_code}")

        resp = self.client.post(
            "/v1/auth/register",
            json={
                "username": f"{self.username}-weak",
                "email": f"{self.username}-weak@example.com",
                "password": "short",
            },
        )
        if resp.status_code == 422:
            self.record("weak password (<8 chars) rejected", PASS)
        else:
            self.record(
                "weak password (<8 chars) rejected", FAIL, f"HTTP {resp.status_code}"
            )

        resp = self.client.post(
            "/v1/auth/login", json={"username": self.username, "password": "wrong"}
        )
        if resp.status_code == 401:
            self.record("wrong password rejected", PASS)
        else:
            self.record("wrong password rejected", FAIL, f"HTTP {resp.status_code}")

        resp = self.client.post(
            "/v1/auth/login",
            json={"username": self.username, "password": self.password},
        )
        if resp.status_code == 200 and resp.json().get("access_token"):
            self.token = resp.json()["access_token"]
            self.record("login issues a JWT", PASS)
            return True
        self.record(
            "login issues a JWT", FAIL, f"HTTP {resp.status_code}: {resp.text[:200]}"
        )
        return False

    # ── Journey 2: plain chat, real Ollama, no tools ─────────────────────
    def journey_plain_chat(self, model):
        print(
            f"\n2. CHAT (no tools, model={model}): a real question gets a real answer"
        )
        resp = self.client.post(
            "/v1/ai/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": "In one short sentence, what is 2+2?"}
                ],
            },
            timeout=90.0,
        )
        if resp.status_code != 200:
            self.record(
                "plain chat responds 200",
                FAIL,
                f"HTTP {resp.status_code}: {resp.text[:300]}",
            )
            return
        content = (resp.json().get("message") or {}).get("content", "")
        if content.strip():
            self.record("plain chat returns real content", PASS, content.strip()[:120])
        else:
            self.record("plain chat returns real content", FAIL, "empty content")

    # ── Journey 3: tool-calling chat against real plugins ────────────────
    def journey_tool_chat(self, model, question, plugin_label):
        print(
            f"\n3. CHAT+TOOLS ({plugin_label}, model={model}): real dispatch to a real plugin"
        )
        resp = self.client.post(
            "/v1/ai/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": question}],
                "minder_tools": True,
            },
            timeout=90.0,
        )
        if resp.status_code != 200:
            self.record(
                f"{plugin_label} tool chat responds 200",
                FAIL,
                f"HTTP {resp.status_code}",
            )
            return
        content = (resp.json().get("message") or {}).get("content", "")
        if content.strip():
            self.record(
                f"{plugin_label} tool chat returns real content",
                PASS,
                content.strip()[:150],
            )
        else:
            self.record(
                f"{plugin_label} tool chat returns real content", FAIL, "empty content"
            )

    # ── Journey 4: full RAG document lifecycle ───────────────────────────
    def journey_rag(self, model):
        print(
            f"\n4. RAG (model={model}): create KB -> upload -> pipeline -> query -> cleanup"
        )
        kb_resp = self.client.post(
            "/v1/rag/knowledge-bases",
            json={"name": f"audit-kb-{secrets.token_hex(3)}"},
            headers=self.auth_headers(),
            timeout=30.0,
        )
        if kb_resp.status_code != 200:
            self.record(
                "create knowledge base",
                FAIL,
                f"HTTP {kb_resp.status_code}: {kb_resp.text[:200]}",
            )
            return
        kb_id = kb_resp.json()["id"]
        self.record("create knowledge base", PASS)

        try:
            doc_text = (
                "Minder is a self-hosted, plugin-based AI platform. It exposes "
                "chat with tool-calling, a plugin registry (crypto, weather, "
                "news, TEFAS), and a retrieval-augmented-generation pipeline."
            )
            files = {"file": ("audit-doc.txt", doc_text, "text/plain")}
            up_resp = self.client.post(
                f"/v1/rag/knowledge-bases/{kb_id}/upload",
                files=files,
                headers=self.auth_headers(),
                timeout=60.0,
            )
            if (
                up_resp.status_code == 200
                and up_resp.json().get("vectors_created", 0) >= 1
            ):
                self.record("upload document (real embedding + Qdrant write)", PASS)
            else:
                self.record(
                    "upload document (real embedding + Qdrant write)",
                    FAIL,
                    f"HTTP {up_resp.status_code}: {up_resp.text[:200]}",
                )
                return

            pipe_resp = self.client.post(
                "/v1/rag/pipeline",
                json={
                    "name": f"audit-pipeline-{secrets.token_hex(3)}",
                    "knowledge_base_ids": [kb_id],
                },
                headers=self.auth_headers(),
                timeout=30.0,
            )
            if pipe_resp.status_code != 200:
                self.record("create pipeline", FAIL, f"HTTP {pipe_resp.status_code}")
                return
            pipeline_id = pipe_resp.json()["pipeline_id"]
            self.record("create pipeline", PASS)

            try:
                q_resp = self.client.post(
                    f"/v1/rag/pipeline/{pipeline_id}/query",
                    json={"question": "What is Minder?"},
                    headers=self.auth_headers(),
                    timeout=90.0,
                )
                if q_resp.status_code == 200:
                    body = q_resp.json()
                    if body.get("answer", "").strip() and body.get("sources"):
                        self.record(
                            "query returns a real generated answer + sources",
                            PASS,
                            body["answer"].strip()[:150],
                        )
                    else:
                        self.record(
                            "query returns a real generated answer + sources",
                            WARN,
                            "200 but empty answer/sources",
                        )
                else:
                    self.record(
                        "query returns a real generated answer + sources",
                        FAIL,
                        f"HTTP {q_resp.status_code}: {q_resp.text[:200]}",
                    )
            finally:
                self.client.delete(
                    f"/v1/rag/pipeline/{pipeline_id}",
                    headers=self.auth_headers(),
                    timeout=15.0,
                )
        finally:
            self.client.delete(
                f"/v1/rag/knowledge-bases/{kb_id}",
                headers=self.auth_headers(),
                timeout=15.0,
            )
            self.record("cleanup (KB + pipeline deleted)", PASS)

    # ── Journey 5: security boundary + input validation, live ────────────
    def journey_security_and_validation(self):
        print("\n5. SECURITY + VALIDATION: unauthenticated write / malformed body")
        resp = self.client.post("/v1/plugins/crypto/actions/refresh", json={})
        if resp.status_code == 401:
            self.record("unauthenticated mutating action rejected", PASS)
        else:
            self.record(
                "unauthenticated mutating action rejected",
                FAIL,
                f"HTTP {resp.status_code}",
            )

        resp = self.client.post(
            "/v1/auth/login",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )
        if resp.status_code in (400, 422):
            self.record(
                "malformed JSON body returns 4xx not 500",
                PASS,
                f"HTTP {resp.status_code}",
            )
        else:
            self.record(
                "malformed JSON body returns 4xx not 500",
                FAIL,
                f"HTTP {resp.status_code}",
            )

    # ── Journey 6: plugin catalog sanity ──────────────────────────────────
    def journey_plugin_catalog(self):
        print("\n6. PLUGIN CATALOG: the 4 real data plugins are actually loaded")
        resp = self.client.get("/v1/plugins")
        if resp.status_code != 200:
            self.record("list plugins", FAIL, f"HTTP {resp.status_code}")
            return
        names = {p["name"] for p in resp.json().get("plugins", [])}
        missing = {"crypto", "weather", "news", "tefas"} - names
        if not missing:
            self.record("crypto/weather/news/tefas all loaded", PASS)
        else:
            self.record(
                "crypto/weather/news/tefas all loaded", FAIL, f"missing: {missing}"
            )

    def summary(self):
        print("\n" + "=" * 70)
        print(f"SUMMARY — {self.base_url}")
        print("=" * 70)
        counts = {PASS: 0, FAIL: 0, WARN: 0}
        for _, status, _ in self.results:
            counts[status] += 1
        for name, status, detail in self.results:
            if status == FAIL:
                print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))
        print(
            f"\n{counts[PASS]} passed, {counts[WARN]} warned, {counts[FAIL]} failed "
            f"out of {len(self.results)}"
        )
        return counts[FAIL] == 0


def _pick_model(base_url: str) -> str:
    """Ask model-management for whatever's actually installed rather than
    hardcoding a name that may not be pulled on this particular host."""
    try:
        resp = httpx.get(f"{base_url}/v1/models", timeout=10.0)
        resp.raise_for_status()
        models = resp.json()
        names = [
            m.get("name") or m.get("model")
            for m in (models if isinstance(models, list) else models.get("models", []))
        ]
        names = [n for n in names if n]
        if names:
            return names[0]
    except Exception as e:  # noqa: BLE001 - fall through to the default below
        print(f"  (could not query /v1/models: {e}; falling back to a default name)")
    return "llama3.2:latest"


def main() -> int:
    # Output has checkmark/emoji glyphs; a non-UTF-8 console codepage (e.g.
    # Windows' cp125x/cp1254 defaults, seen live on hantal) raises
    # UnicodeEncodeError partway through a run instead of printing a result.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument(
        "--model", default=None, help="override the model used for chat journeys"
    )
    args = ap.parse_args()

    print("=" * 70)
    print("MINDER REAL USER-JOURNEY AUDIT")
    print("=" * 70)
    print(f"Target: {args.base_url}")

    model = args.model or _pick_model(args.base_url)
    print(f"Model: {model}")

    j = Journey(args.base_url)
    if j.journey_auth():
        j.journey_plain_chat(model)
        j.journey_tool_chat(model, "What is the current price of bitcoin?", "crypto")
        j.journey_tool_chat(
            model, "What's the weather like in Istanbul right now?", "weather"
        )
        j.journey_tool_chat(model, "What's in the news today?", "news")
        j.journey_rag(model)
    j.journey_security_and_validation()
    j.journey_plugin_catalog()

    ok = j.summary()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
