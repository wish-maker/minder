"""Unit tests for graph-rag noun-phrase/NER dedup (#669).

The extractor pulls both NER entities and noun chunks, which overlap constantly
("Tesla" is both an ORG entity and a noun chunk). Emitting both created two
Entity nodes for the same text under different labels; since relationships match
entities by text alone, that made relationship linking ambiguous. The dedup is a
pure, spaCy-free function (the extractor's spaCy import isn't installed in the
unit env — the graph-rag tests fake it), so it loads by path.
"""

import importlib.util
from pathlib import Path

_MOD = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "services"
    / "graph-rag"
    / "core"
    / "entity_dedup.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("entity_dedup_under_test", _MOD)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


filter_noun_phrases = _load().filter_noun_phrases


def _ent(text, start, end):
    return {"text": text, "start": start, "end": end}


def test_exact_text_duplicate_of_ner_entity_is_dropped():
    # "Tesla" is an ORG NER entity at 0..5; the identical noun chunk must not
    # become a second NOUN_PHRASE Entity node.
    ner = [_ent("Tesla", 0, 5)]
    nps = [_ent("Tesla", 0, 5)]
    assert filter_noun_phrases(ner, nps) == []


def test_case_insensitive_duplicate_is_dropped():
    ner = [_ent("Tesla", 0, 5)]
    nps = [_ent("tesla", 20, 25)]
    assert filter_noun_phrases(ner, nps) == []


def test_span_overlapping_noun_phrase_is_dropped():
    # NER "Tesla" (0..5); chunk "the Tesla car" (0..13) shares the span → drop.
    ner = [_ent("Tesla", 0, 5)]
    nps = [_ent("the Tesla car", 0, 13)]
    assert filter_noun_phrases(ner, nps) == []


def test_distinct_noun_phrase_is_kept_with_noun_phrase_label():
    ner = [_ent("Tesla", 0, 5)]
    nps = [_ent("the battery pack", 30, 46)]
    kept = filter_noun_phrases(ner, nps)
    assert len(kept) == 1
    assert kept[0]["text"] == "the battery pack"
    assert kept[0]["label"] == "NOUN_PHRASE"


def test_duplicate_noun_phrases_among_themselves_are_deduped():
    ner: list = []
    nps = [_ent("battery pack", 0, 12), _ent("Battery Pack", 40, 52)]
    kept = filter_noun_phrases(ner, nps)
    assert [k["text"] for k in kept] == ["battery pack"]


def test_short_phrases_are_skipped():
    ner: list = []
    nps = [_ent("AI", 0, 2), _ent("ok", 5, 7)]
    assert filter_noun_phrases(ner, nps) == []


def test_adjacent_non_overlapping_spans_are_kept():
    # Half-open spans: NER at 0..5, chunk at 5..15 touch but don't overlap → keep.
    ner = [_ent("Tesla", 0, 5)]
    nps = [_ent("battery module", 5, 19)]
    kept = filter_noun_phrases(ner, nps)
    assert len(kept) == 1
