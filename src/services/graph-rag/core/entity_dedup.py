"""Noun-phrase vs. NER deduplication for entity extraction (#669).

Kept spaCy-free (plain dicts in/out) on purpose: the extractor pulls BOTH named
entities (``doc.ents``) and noun chunks (``doc.noun_chunks``), and the two
overlap constantly — spaCy tags "Tesla" as an ORG entity *and* surfaces it as a
noun chunk. Emitting both produced two ``Entity`` nodes for the same text under
different labels (``ORG`` vs ``NOUN_PHRASE``). Because relationships are matched
to entities by ``text`` alone (``MATCH (s:Entity {text: $subject})`` in
graph_constructor), that duplication made relationship linking ambiguous — an
edge could attach to either node — and inflated co-occurrence noise.

This drops any noun-phrase candidate that duplicates (same text, case-insensitive)
or textually overlaps (shares a character span with) an already-extracted NER
entity, or an earlier accepted phrase. Being a pure function it is unit-tested
without spaCy installed.
"""

from typing import Any, Dict, List


def filter_noun_phrases(
    ner_entities: List[Dict[str, Any]], np_candidates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Return the noun-phrase entity dicts to keep, deduped against ``ner_entities``.

    Args:
        ner_entities: already-extracted NER entities; each needs ``text``/``start``/``end``.
        np_candidates: raw noun-chunk candidates; each needs ``text``/``start``/``end``.

    Returns:
        A list of NOUN_PHRASE entity dicts (``text``/``label``/``start``/``end``/
        ``description``) safe to append — no text- or span-duplicate of an NER
        entity, and no duplicate text among themselves.
    """
    seen = {e["text"].strip().lower() for e in ner_entities}
    ner_spans = [(e["start"], e["end"]) for e in ner_entities]
    kept: List[Dict[str, Any]] = []
    for np in np_candidates:
        text = np["text"].strip()
        if len(text) <= 2:  # skip trivially short phrases (matches prior behavior)
            continue
        key = text.lower()
        if key in seen:  # exact cross-label duplicate of an NER ent / earlier phrase
            continue
        start, end = np["start"], np["end"]
        # Half-open span overlap: skip a chunk that shares any character span with
        # an NER entity (e.g. NER "Tesla" vs chunk "the Tesla car").
        if any(start < e_end and e_start < end for e_start, e_end in ner_spans):
            continue
        kept.append(
            {
                "text": np["text"],
                "label": "NOUN_PHRASE",
                "start": start,
                "end": end,
                "description": "Noun phrase",
            }
        )
        seen.add(key)
    return kept
