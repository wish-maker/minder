# Minder — Vision & North Star

> **Status:** Living document. This is the *shape and direction* of the platform.
> Concrete, actionable work lives in the GitHub tracker (`wish-maker/minder`); when
> this document and the tracker disagree, **the tracker wins**. Pairs with
> [`docs/architecture/roadmap.md`](architecture/roadmap.md) (what exists + milestones)
> and [`docs/architecture/overview.md`](architecture/overview.md) (how it fits together).

---

## One sentence

**Minder is your private AI platform — local inference, your own data, and an
extensible tool ecosystem — that installs on modest hardware with a single command.**

## North Star

A person or a small team should be able to run, on hardware they own (down to a
Raspberry Pi), a complete AI system that:

- answers questions over **their own documents and data** (RAG + a knowledge graph),
- runs **local LLMs** with no cloud API keys and no data leaving the box,
- is **extended by plugins and tools** without writing or trusting arbitrary code,
- is **operated from one coherent, modern control-plane UI** — not a pile of raw forms,
- and is **honest about what it does**: every capability is real, verifiable, and
  observable, or it is clearly marked as not-yet-implemented.

If a capability can't be run end-to-end and shown working, it isn't done.

---

## Principles

1. **Local-first & private by default.** Inference, storage, and retrieval run on the
   user's own hardware. The default posture is "nothing leaves the box"; any egress
   (e.g. an online TTS fallback) is opt-in and obvious.
2. **One command to a working system.** `bash setup.sh` provisions the whole stack,
   fills secrets, and self-heals. Capability is toggled by **bundles**, not by editing
   compose files.
3. **Extensible without arbitrary code execution.** Plugins are **manifest-based**;
   new actions are fixed, reviewed handlers — never uploaded code. Safety is a design
   property, not a scanner bolted on afterward.
4. **Runs on modest hardware.** ARM/Raspberry-Pi is a first-class target, not an
   afterthought. Features are chosen and tuned to fit (e.g. Piper for offline TTS,
   optional cross-encoder reranking that degrades gracefully when torch is absent).
5. **Honest & verifiable.** Docs match reality; "done" means proven by running with
   real output. Not-yet-implemented paths fail loudly (501/clear errors), never
   silently pretend.
6. **A real product, not a demo.** A coherent, task-oriented UI; consistent APIs;
   observability from day one; secure-by-default networking.

---

## Pillars

### 1. Local inference
Ollama-backed LLM runtime, with clean local ⇄ external ⇄ failover switching
(`ollama-mode`). Model lifecycle (pull/list/delete/test) is first-class.
*Direction:* horizontal inference scaling / work-routing across backends when a real
single-host bottleneck appears (#21, deliberately deferred until then).

### 2. Knowledge — RAG *and* graph
Retrieval that goes beyond naive vector search: Standard / HyDE / Self-RAG / auto /
corrective methods, plus hybrid and parent-child retrieval and optional
rerank/compress — all capability-adaptive. A parallel **knowledge-graph** path
(spaCy NER → Neo4j) for entity/relationship exploration over the same documents.
*Direction:* RAPTOR hierarchical retrieval (#487); richer ingest-time indexing.

### 3. Extensibility — plugins, tools, marketplace
Manifest-based plugins that can write to any backend and register as **AI tools** for
Ollama function-calling. A marketplace with a dependency/conflict graph.
*Direction:* a real third-party submission/review/trust flow (#402); more first-party
data plugins on the central config API.

### 4. The control-plane UI (`minder-client`)
A bespoke React/Vite app that is the single, modern surface for everything that
isn't chat: knowledge bases, pipelines, the graph explorer, plugins & AI tools,
model/bundle/health ops, and voice. Chat itself stays in OpenWebUI.
*Direction:* a genuinely modern, task-oriented UX (see below).

### 5. Observability & operations
Prometheus/Grafana/Jaeger/InfluxDB/OTel wired in from the start; `setup.sh status
--fix` self-healing; loud, honest backups.
*Direction:* metrics hygiene (bounded-cardinality labels, #503), self-healing on the
Pi promoted from cron scripts to first-class tooling.

### 6. Security & multi-user
JWT auth, license fail-closed, Authelia SSO/2FA enforced at the edge, loopback-bound
host ports, no-arbitrary-code plugins.
*Direction:* real RBAC that actually gates on the stored role (#474), per-deployment
secrets instead of git-committed hashes (#473), closing the host-port forward-auth
bypass (#472), and true browser SSO once a real domain + TLS exist.

---

## Who it's for

- **The self-hoster / homelabber** who wants private AI on hardware they own.
- **The small team** that needs a shared, on-prem knowledge + automation base without
  sending documents to a third party.
- **The builder** who wants to extend an AI platform with tools/plugins safely.

## Non-goals (on purpose)

- **Not a cloud SaaS.** No multi-tenant billing platform; no "send us your data."
- **Not a model-training platform.** Fine-tuning was removed on purpose; Minder
  *runs and orchestrates* models, it doesn't train them.
- **Not a chat UI reinvention.** OpenWebUI owns chat; Minder owns everything around it.
- **Not maximal complexity.** Features earn their place by a real, demonstrated need
  (e.g. multi-backend routing waits for a proven bottleneck).

---

## The UX north star

The control-plane should feel like **one modern product**, not a set of service
forms. Concretely, we are steering the client toward:

- **Task-first, not endpoint-first.** Screens organised around what a user is trying
  to do (ingest a document, ask a question, turn on a capability), with the
  underlying services invisible.
- **A cohesive design system.** One typographic scale, spacing rhythm, and colour
  system; consistent cards, buttons, empty/loading/error states; light **and** dark
  parity; accessible by default (labels, focus, `aria-live` status, keyboard paths).
- **Works where the user actually is.** Every access path is real — including direct
  `localhost`/LAN over plain HTTP — so login, copy, IDs, and links never assume a
  hostname or secure context the user doesn't have.
- **Trustworthy feedback.** Clear progress, honest errors (backend-down vs. your
  input), confirmation before destructive actions, and no silent failures.
- **Tested end-to-end.** Pure logic under unit tests; key flows exercised against a
  live stack; the build/lint/typecheck gate stays green.

This UX work is tracked as an epic (client modernization) alongside the concrete
robustness follow-ups (#502) and per-screen polish.

---

## How we get there (phased, tracker-driven)

The tracker is the source of truth; this is the *shape* of the sequence.

1. **Harden what exists.** Correctness, standardization, and consistency across the
   services and the client (ongoing); make every documented flow provably work.
2. **Make it genuinely usable.** The modern control-plane UX; access-path parity;
   local login; task-oriented screens.
3. **Deepen the intelligence.** RAPTOR and richer retrieval; a stronger RAG↔graph
   story; better tool-calling ergonomics.
4. **Open the ecosystem.** A real marketplace submission/trust flow; more plugins.
5. **Real multi-user & production.** RBAC, per-deployment secrets, full browser SSO,
   production hardening for a public deploy.

---

*Keep this document honest. If Minder can't do something described here, either the
capability or this text is wrong — fix whichever one it is, in the same pass.*
