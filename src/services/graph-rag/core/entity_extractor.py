"""
Entity Extraction Module for Graph RAG

Hybrid entity extraction using spaCy and GLiNER for advanced NER.
"""

import logging
from typing import Any, Dict, List

import spacy

logger = logging.getLogger(__name__)


class EntityExtractor:
    """Hybrid entity extraction using spaCy and GLiNER"""

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

        # TODO: Add GLiNER support in Phase 2
        # try:
        #     from gliner import GLiNER
        #     self.gliner_model = GLiNER.from_pretrained("urchade/gliner_medium")
        # except ImportError:
        #     logger.warning("GLiNER not available, using spaCy only")
        #     self.gliner_model = None

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

            # Extract noun phrases as additional entities
            noun_phrases = list(doc.noun_chunks)
            for np in noun_phrases[:10]:  # Limit to top 10
                if len(np.text) > 2:  # Skip short phrases
                    entity = {
                        "text": np.text,
                        "label": "NOUN_PHRASE",
                        "start": np.start_char,
                        "end": np.end_char,
                        "description": "Noun phrase",
                    }
                    entities.append(entity)

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
