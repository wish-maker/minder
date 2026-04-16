"""
Knowledge Graph Population System
Automatically extracts and stores entities and relationships from module data
"""

from typing import Dict, List, Any
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import logging

from .knowledge_graph import (
    KnowledgeGraph,
    Entity,
    Relation,
    EntityType,
    RelationType,
)

logger = logging.getLogger(__name__)


class KnowledgeGraphPopulator:
    """
    Automatically populate knowledge graph from module data

    Extracts:
    - Entities (funds, network nodes, weather stations, etc.)
    - Relationships (correlations, causality, dependencies)
    - Attributes and metadata
    """

    def __init__(self, kg: KnowledgeGraph, config: Dict[str, Any]):
        self.kg = kg
        self.config = config
        self.batch_size = config.get("batch_size", 100)

    async def populate_from_fund_module(self, fund_data: pd.DataFrame, fund_analysis: Dict[str, Any]) -> Dict[str, int]:
        """Extract and populate fund entities and relationships"""
        entities_added = 0
        relations_added = 0

        try:
            # Extract fund entities
            for fund_code in fund_data["fund_code"].unique():
                # Create fund entity
                fund_entity = Entity(
                    id=f"fund:{fund_code}",
                    type=EntityType.FUND,
                    name=f"Fund {fund_code}",
                    attributes={
                        "code": fund_code,
                        "type": "mutual_fund",
                        "market": "TEFAS",
                    },
                    module="fund",
                )

                await self.kg.add_entity(fund_entity)
                entities_added += 1

            # Extract performance entities
            for _, row in fund_analysis.get("top_performers", []).iterrows():
                perf_entity = Entity(
                    id=f"performance:{row['fund_code']}",
                    type=EntityType.CONCEPT,
                    name=f"Performance metrics for {row['fund_code']}",
                    attributes={
                        "avg_return": float(row["avg_return"]),
                        "volatility": float(row["volatility"]),
                        "sharpe_ratio": float(row["sharpe_ratio"]),
                        "rank": "top_performer",
                    },
                    module="fund",
                )

                await self.kg.add_entity(perf_entity)
                entities_added += 1

                # Link fund to performance
                perf_relation = Relation(
                    source=await self.kg.get_entity(f"fund:{row['fund_code']}"),
                    target=perf_entity,
                    relation_type=RelationType.RELATED_TO,
                    weight=0.8,
                    attributes={"metric": "performance"},
                )

                await self.kg.add_relation(perf_relation)
                relations_added += 1

            logger.info(f"✅ Added {entities_added} fund entities, {relations_added} relations")

            return {
                "entities_added": entities_added,
                "relations_added": relations_added,
            }

        except Exception as e:
            logger.error(f"Failed to populate fund entities: {e}")
            return {"entities_added": 0, "relations_added": 0}

    async def populate_from_network_module(self, network_metrics: Dict[str, Any]) -> Dict[str, int]:
        """Extract and populate network entities and relationships"""
        entities_added = 0
        relations_added = 0

        try:
            # Create network entities
            for metric_name, value in network_metrics.get("metrics", {}).items():
                network_entity = Entity(
                    id=f"network_metric:{metric_name}",
                    type=EntityType.NETWORK,
                    name=f"Network {metric_name}",
                    attributes={
                        "value": float(value),
                        "unit": self._get_metric_unit(metric_name),
                    },
                    module="network",
                )

                await self.kg.add_entity(network_entity)
                entities_added += 1

            # Add network relationships
            if entities_added > 1:
                # Connect latency to throughput
                latency_entity = await self.kg.get_entity("network_metric:avg_latency_ms")
                throughput_entity = await self.kg.get_entity("network_metric:throughput_mbps")

                if latency_entity and throughput_entity:
                    relation = Relation(
                        source=latency_entity,
                        target=throughput_entity,
                        relation_type=RelationType.AFFECTS,
                        weight=0.7,
                        attributes={"type": "inverse_correlation"},
                    )

                    await self.kg.add_relation(relation)
                    relations_added += 1

            logger.info(f"✅ Added {entities_added} network entities, {relations_added} relations")

            return {
                "entities_added": entities_added,
                "relations_added": relations_added,
            }

        except Exception as e:
            logger.error(f"Failed to populate network entities: {e}")
            return {"entities_added": 0, "relations_added": 0}

    async def populate_cross_module_relationships(self, correlations: Dict[str, List[Dict]]) -> Dict[str, int]:
        """Populate relationships discovered between modules"""
        relations_added = 0

        try:
            for pair_key, correlation_list in correlations.items():
                module_a, module_b = pair_key.split(":")

                for corr in correlation_list:
                    # Create entities if they don't exist
                    entity_a_id = f"{module_a}:{corr['field_a'].replace('.', '_')}"
                    entity_b_id = f"{module_b}:{corr['field_b'].replace('.', '_')}"

                    entity_a = Entity(
                        id=entity_a_id,
                        type=EntityType.CONCEPT,
                        name=corr["field_a"],
                        attributes={"module": module_a},
                        module=module_a,
                    )

                    entity_b = Entity(
                        id=entity_b_id,
                        type=EntityType.CONCEPT,
                        name=corr["field_b"],
                        attributes={"module": module_b},
                        module=module_b,
                    )

                    await self.kg.add_entity(entity_a)
                    await self.kg.add_entity(entity_b)

                    # Create relationship
                    relation = Relation(
                        source=entity_a,
                        target=entity_b,
                        relation_type=self._map_correlation_type(corr["correlation_type"]),
                        weight=corr["strength"],
                        attributes={
                            "description": corr["description"],
                            "discovered_at": corr.get("discovered_at", datetime.now()).isoformat(),
                        },
                    )

                    await self.kg.add_relation(relation)
                    relations_added += 1

            logger.info(f"✅ Added {relations_added} cross-module relations")

            return {"relations_added": relations_added}

        except Exception as e:
            logger.error(f"Failed to populate cross-module relationships: {e}")
            return {"relations_added": 0}

    async def populate_from_anomalies(self, anomalies: List[Dict[str, Any]]) -> Dict[str, int]:
        """Populate anomaly entities and their relationships"""
        entities_added = 0
        relations_added = 0

        try:
            for anomaly in anomalies:
                # Create anomaly entity
                anomaly_entity = Entity(
                    id=f"anomaly:{anomaly.get('type', 'unknown')}:{datetime.now().timestamp()}",
                    type=EntityType.EVENT,
                    name=f"{anomaly.get('type', 'Anomaly')} - {anomaly.get('severity', 'unknown')}",
                    attributes={
                        "type": anomaly.get("type"),
                        "severity": anomaly.get("severity"),
                        "description": anomaly.get("description"),
                        "score": anomaly.get("score"),
                        "timestamp": anomaly.get("detected_at", datetime.now()).isoformat(),
                    },
                    module=anomaly.get("module", "unknown"),
                )

                await self.kg.add_entity(anomaly_entity)
                entities_added += 1

                # Link to source entity
                source_id = anomaly.get("entity_id")
                if source_id:
                    source_entity = await self.kg.get_entity(source_id)
                    if source_entity:
                        relation = Relation(
                            source=source_entity,
                            target=anomaly_entity,
                            relation_type=RelationType.CONTAINS,
                            weight=0.9,
                            attributes={"detected_at": anomaly.get("detected_at")},
                        )

                        await self.kg.add_relation(relation)
                        relations_added += 1

            logger.info(f"✅ Added {entities_added} anomaly entities, {relations_added} relations")

            return {
                "entities_added": entities_added,
                "relations_added": relations_added,
            }

        except Exception as e:
            logger.error(f"Failed to populate anomaly entities: {e}")
            return {"entities_added": 0, "relations_added": 0}

    async def populate_temporal_relationships(
        self,
        time_series_data: Dict[str, pd.DataFrame],
        window: timedelta = timedelta(days=7),
    ) -> Dict[str, int]:
        """Populate temporal relationships between time-series events"""
        relations_added = 0

        try:
            # For each pair of time series, find temporal patterns
            series_names = list(time_series_data.keys())

            for i, name1 in enumerate(series_names):
                for name2 in series_names[i + 1 :]:
                    df1 = time_series_data[name1]
                    df2 = time_series_data[name2]

                    # Find events (peaks, valleys) in both series
                    events1 = self._find_temporal_events(df1)
                    events2 = self._find_temporal_events(df2)

                    # Find temporal proximity
                    for event1 in events1:
                        for event2 in events2:
                            time_diff = abs((event1["timestamp"] - event2["timestamp"]).total_seconds())

                            if time_diff <= window.total_seconds():
                                # Create temporal relationship
                                entity1_id = f"event:{name1}:{event1['timestamp'].timestamp()}"
                                entity2_id = f"event:{name2}:{event2['timestamp'].timestamp()}"

                                entity1 = Entity(
                                    id=entity1_id,
                                    type=EntityType.EVENT,
                                    name=f"{event1['type']} in {name1}",
                                    attributes={
                                        "timestamp": event1["timestamp"].isoformat(),
                                        "value": float(event1["value"]),
                                    },
                                    module=name1,
                                )

                                entity2 = Entity(
                                    id=entity2_id,
                                    type=EntityType.EVENT,
                                    name=f"{event2['type']} in {name2}",
                                    attributes={
                                        "timestamp": event2["timestamp"].isoformat(),
                                        "value": float(event2["value"]),
                                    },
                                    module=name2,
                                )

                                await self.kg.add_entity(entity1)
                                await self.kg.add_entity(entity2)

                                # Create temporal relation
                                relation = Relation(
                                    source=entity1,
                                    target=entity2,
                                    relation_type=(
                                        RelationType.PRECEDES
                                        if event1["timestamp"] < event2["timestamp"]
                                        else RelationType.PRECEDES
                                    ),
                                    weight=max(
                                        0,
                                        1 - time_diff / window.total_seconds(),
                                    ),
                                    attributes={
                                        "time_difference_seconds": time_diff,
                                        "window": window.total_seconds(),
                                    },
                                )

                                await self.kg.add_relation(relation)
                                relations_added += 1

            logger.info(f"✅ Added {relations_added} temporal relations")

            return {"relations_added": relations_added}

        except Exception as e:
            logger.error(f"Failed to populate temporal relationships: {e}")
            return {"relations_added": 0}

    async def enrich_entities_with_embeddings(
        self, qdrant_client, collection_name: str = "minder_entities"
    ) -> Dict[str, int]:
        """
        Enrich entities with vector embeddings for semantic search

        Stores embeddings in Qdrant for fast similarity search
        """
        entities_enriched = 0

        try:
            # Get all entities
            all_entities = list(self.kg.entities.values())

            # Prepare batches
            for i in range(0, len(all_entities), self.batch_size):
                batch = all_entities[i : i + self.batch_size]

                # Create embeddings
                texts = [
                    f"{ent.name} {ent.type.value} " + " ".join([f"{k}={v}" for k, v in ent.attributes.items()])
                    for ent in batch
                ]

                # Generate embeddings (using Ollama)
                embeddings = await self._generate_embeddings(texts)

                # Store in Qdrant
                points = [
                    {
                        "id": ent.id,
                        "vector": emb,
                        "payload": {
                            "name": ent.name,
                            "type": ent.type.value,
                            "module": ent.module,
                            "attributes": ent.attributes,
                        },
                    }
                    for ent, emb in zip(batch, embeddings)
                ]

                # Upsert to Qdrant
                await qdrant_client.upsert(collection_name=collection_name, points=points)

                entities_enriched += len(batch)

            logger.info(f"✅ Enriched {entities_enriched} entities with embeddings")

            return {"entities_enriched": entities_enriched}

        except Exception as e:
            logger.error(f"Failed to enrich entities with embeddings: {e}")
            return {"entities_enriched": 0}

    async def query_semantic_similar_entities(
        self,
        query: str,
        qdrant_client,
        collection_name: str = "minder_entities",
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Query entities by semantic similarity

        Uses vector embeddings to find conceptually similar entities
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_embeddings([query])
            query_vector = query_embedding[0]

            # Search Qdrant
            results = await qdrant_client.search(
                collection_name=collection_name,
                query_vector=query_vector,
                limit=limit,
            )

            return [
                {
                    "entity_id": r.id,
                    "name": r.payload["name"],
                    "type": r.payload["type"],
                    "module": r.payload["module"],
                    "score": r.score,
                }
                for r in results
            ]

        except Exception as e:
            logger.error(f"Semantic query failed: {e}")
            return []

    def _find_temporal_events(self, df: pd.DataFrame, window: int = 5, threshold: float = 2.0) -> List[Dict[str, Any]]:
        """Find significant events in time series"""
        events = []

        if "date" not in df.columns:
            return events

        # Get value column
        value_col = df.select_dtypes(include=[np.number]).columns[0]

        # Calculate z-scores
        mean = df[value_col].mean()
        std = df[value_col].std()

        if std == 0:
            return events

        df["z_score"] = (df[value_col] - mean) / std

        # Find events
        for _, row in df.iterrows():
            if abs(row["z_score"]) > threshold:
                event_type = "peak" if row["z_score"] > 0 else "valley"
                events.append(
                    {
                        "timestamp": pd.to_datetime(row["date"]),
                        "type": event_type,
                        "value": row[value_col],
                        "z_score": row["z_score"],
                    }
                )

        return events

    def _get_metric_unit(self, metric_name: str) -> str:
        """Get unit for network metric"""
        unit_map = {
            "avg_latency_ms": "ms",
            "packet_loss_pct": "%",
            "throughput_mbps": "Mbps",
            "active_connections": "count",
        }
        return unit_map.get(metric_name, "unknown")

    def _map_correlation_type(self, corr_type: str) -> RelationType:
        """Map correlation type string to RelationType enum"""
        type_map = {
            "temporal": RelationType.PRECEDES,
            "causal": RelationType.CAUSES,
            "semantic": RelationType.RELATED_TO,
            "statistical": RelationType.CORRELATES,
        }
        return type_map.get(corr_type, RelationType.RELATED_TO)

    async def _generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings using Ollama"""
        try:
            import httpx

            embeddings = []

            for text in texts:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        "http://ollama:11434/api/embed",
                        json={"model": "nomic-embed-text", "input": text},
                    )

                    if response.status_code == 200:
                        result = response.json()
                        embeddings.append(result["embedding"])
                    else:
                        # Fallback: zero vector
                        embeddings.append([0.0] * 768)

            return embeddings

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            # Fallback: zero vectors
            return [[0.0] * 768 for _ in texts]
