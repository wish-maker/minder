"""
Entity Extraction Module for Graph RAG

spaCy-based entity extraction and relationship inference.
"""

import logging
from typing import Any, Dict, List

import spacy
from core.entity_dedup import filter_noun_phrases

logger = logging.getLogger(__name__)


class EntityExtractor:
    """spaCy-based entity extraction"""

    def __init__(self, spacy_model: str = "en_core_web_sm"):
        """Initialize entity extractor with spaCy"""
        try:
            self.nlp = spacy.load(spacy_model)
            logger.info(f"✅ Loaded spaCy model: {spacy_model}")
        except OSError:
            logger.warning(
                f"⚠️  spaCy model {spacy_model} not found, using blank model"
            )
            self.nlp = spacy.blank("en")

    def extract_entities(
        self, text: str, extract_relationships: bool = True
    ) -> Dict[str, Any]:
        """
        Extract entities and relationships from text

        Args:
            text: Input text to extract entities from
            extract_relationships: Whether to extract relationships

        Returns:
            Dict with entities and relationships
        """
        try:
            doc = self.nlp(text)

            entities = []
            for ent in doc.ents:
                entity = {
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "description": spacy.explain(ent.label_),
                }
                entities.append(entity)

            # Extract noun phrases as additional entities — but dedup them against
            # the NER entities above (#669): a noun chunk that duplicates or
            # overlaps an NER entity used to be emitted as a second Entity node
            # under the NOUN_PHRASE label, and since relationships match entities
            # by text alone that made relationship linking ambiguous.
            np_candidates = [
                {
                    "text": np.text,
                    "start": np.start_char,
                    "end": np.end_char,
                }
                for np in list(doc.noun_chunks)[:10]  # top 10 (as before)
            ]
            entities.extend(filter_noun_phrases(entities, np_candidates))

            # Extract relationships
            relationships = []
            if extract_relationships:
                relationships = self._extract_relationships(doc, entities)

            result = {
                "entities": entities,
                "relationships": relationships,
                "entity_count": len(entities),
                "relationship_count": len(relationships),
            }

            logger.info(
                f"📊 Extracted {len(entities)} entities, {len(relationships)} relationships"
            )
            return result

        except Exception as e:
            logger.error(f"❌ Entity extraction failed: {e}")
            return {
                "entities": [],
                "relationships": [],
                "entity_count": 0,
                "relationship_count": 0,
            }

    def _extract_relationships(
        self, doc: spacy.tokens.Doc, entities: List[Dict]
    ) -> List[Dict[str, Any]]:
        """Extract relationships between entities"""
        relationships = []

        try:
            # Find subject-verb-object patterns
            for token in doc:
                if token.dep_ in ["nsubj", "nsubjpass"]:
                    subject = token.text
                    verb = token.head.text

                    # Find object
                    obj = None
                    for child in token.head.children:
                        if child.dep_ in ["dobj", "iobj", "obj"]:
                            obj = child.text
                            break

                    if obj:
                        relationship = {
                            "subject": subject,
                            "predicate": verb,
                            "object": obj,
                            "type": "SVO",
                        }
                        relationships.append(relationship)

            # Find co-occurrence relationships
            entity_texts = [e["text"] for e in entities]
            for i, e1 in enumerate(entity_texts):
                for e2 in entity_texts[i + 1 :]:
                    if e1.lower() != e2.lower():
                        relationship = {
                            "subject": e1,
                            "predicate": "CO_OCCURS_WITH",
                            "object": e2,
                            "type": "CO_OCCURRENCE",
                        }
                        relationships.append(relationship)

        except Exception as e:
            logger.warning(f"⚠️  Relationship extraction failed: {e}")

        return relationships
