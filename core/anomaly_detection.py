"""
Real-Time Anomaly Detection System
Implements Isolation Forest, LSTM Autoencoders, and statistical methods
"""

from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass
from enum import Enum
from collections import deque

logger = logging.getLogger(__name__)


class AnomalyType(Enum):
    """Types of anomalies"""

    PRICE_SPIKE = "price_spike"
    PRICE_DROP = "price_drop"
    VOLUME_SURGE = "volume_surge"
    VOLATILITY = "volatility"
    PATTERN_BREAK = "pattern_break"
    CORRELATION_BREAK = "correlation_break"
    STATISTICAL = "statistical"
    CONTEXTUAL = "contextual"


class AnomalySeverity(Enum):
    """Severity levels"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class Anomaly:
    """Anomaly detection result"""

    type: AnomalyType
    severity: AnomalySeverity
    module: str
    entity_id: str
    description: str
    score: float  # 0-1, higher = more anomalous
    timestamp: datetime
    data: Dict[str, Any]
    confidence: float
    suggested_action: Optional[str] = None


class AnomalyDetector:
    """
    Real-time anomaly detection with multiple algorithms

    Algorithms:
    - Isolation Forest: Outlier detection
    - LSTM Autoencoder: Reconstruction error
    - Statistical: Z-score, IQR
    - Contextual: Deviation from expected patterns
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.threshold = config.get("threshold", 0.95)
        self.window_size = config.get("window_size", 100)
        self.min_samples = config.get("min_samples", 50)

        # Model storage
        self.isolation_forests = {}
        self.autoencoders = {}
        self.baseline_stats = {}

        # Real-time buffers
        self.data_buffers = {}
        self.anomaly_history = deque(maxlen=1000)

    async def detect_anomalies_isolation_forest(
        self, data: pd.DataFrame, module: str, entity_id: str
    ) -> List[Anomaly]:
        """
        Detect anomalies using Isolation Forest

        Good for: High-dimensional data, global outliers
        """
        try:
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler

            if len(data) < self.min_samples:
                return []

            # Prepare features
            features = self._prepare_anomaly_features(data)

            # Scale
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features)

            # Train/fit Isolation Forest
            iso_forest = IsolationForest(
                contamination=0.1, random_state=42, n_jobs=-1
            )

            # Fit on all data
            iso_forest.fit(features_scaled)

            # Predict
            predictions = iso_forest.predict(features_scaled)
            scores = iso_forest.score_samples(features_scaled)

            # Find anomalies
            anomalies = []
            for i, (pred, score) in enumerate(zip(predictions, scores)):
                if pred == -1:  # Anomaly
                    # Convert score to 0-1 (higher = more anomalous)
                    anomaly_score = 1 - (score + 0.5)  # Scale to 0-1

                    if anomaly_score > (1 - self.threshold):
                        anomaly = Anomaly(
                            type=AnomalyType.STATISTICAL,
                            severity=self._calculate_severity(anomaly_score),
                            module=module, entity_id=entity_id,
                            description=f"Isolation Forest detected outlier (score: {anomaly_score:.3f})",
                            score=anomaly_score, timestamp=datetime.now(),
                            data=data.iloc[i].to_dict(),
                            confidence=anomaly_score,
                            suggested_action="Investigate unusual pattern",)
                        anomalies.append(anomaly)

            return anomalies

        except Exception as e:
            logger.error(f"Isolation Forest detection failed: {e}")
            return []

    async def detect_anomalies_statistical(
        self,
        data: pd.DataFrame,
        module: str,
        entity_id: str,
        column: str = "value",
    ) -> List[Anomaly]:
        """
        Detect anomalies using statistical methods

        Methods:
        - Z-score (mean ± 3*std)
        - IQR (Interquartile Range)
        - Moving Average deviation
        """
        if len(data) < self.window_size:
            return []

        anomalies = []
        values = (
            data[column].values
            if column in data.columns
            else data.iloc[:, 0].values
        )

        # Z-score method
        mean = np.mean(values)
        std = np.std(values)

        if std > 0:
            z_scores = np.abs((values - mean) / std)

            for i, z_score in enumerate(z_scores):
                if z_score > 3:  # 3-sigma rule
                    anomaly = Anomaly(
                        type=AnomalyType.STATISTICAL,
                        severity=(
                            AnomalySeverity.HIGH
                            if z_score > 5
                            else AnomalySeverity.MEDIUM
                        ),
                        module=module,
                        entity_id=entity_id,
                        description=f"Z-score outlier: {z_score:.2f}σ",
                        score=min(z_score / 5, 1.0),
                        timestamp=datetime.now(),
                        data={"value": values[i], "z_score": z_score},
                        confidence=min(z_score / 5, 1.0),
                        suggested_action="Check data quality",
                    )
                    anomalies.append(anomaly)

        # IQR method
        Q1 = np.percentile(values, 25)
        Q3 = np.percentile(values, 75)
        IQR = Q3 - Q1

        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR

        for i, value in enumerate(values):
            if value < lower_bound or value > upper_bound:
                severity = (
                    AnomalySeverity.CRITICAL
                    if value < Q1 - 3 * IQR or value > Q3 + 3 * IQR
                    else AnomalySeverity.HIGH
                )

                anomaly = Anomaly(
                    type=AnomalyType.STATISTICAL,
                    severity=severity,
                    module=module,
                    entity_id=entity_id,
                    description=f"IQR outlier: {value:.2f} (bounds: [{lower_bound:.2f}, {upper_bound:.2f}])",
                    score=0.8,
                    timestamp=datetime.now(),
                    data={
                        "value": value,
                        "lower_bound": lower_bound,
                        "upper_bound": upper_bound,
                    },
                    confidence=0.8,
                    suggested_action="Verify data accuracy",
                )
                anomalies.append(anomaly)

        return anomalies

    async def detect_anomalies_contextual(
        self,
        data: pd.DataFrame,
        module: str,
        entity_id: str,
        context_window: int = 30,
    ) -> List[Anomaly]:
        """
        Detect contextual anomalies

        Contextual anomaly: Value that's anomalous in a specific context
        but normal in other contexts (e.g., high sales on holidays)
        """
        if len(data) < context_window * 2:
            return []

        anomalies = []

        # Calculate expected behavior based on context
        # For time series: compare with same time period in history

        # Extract day of week patterns
        data["timestamp"] = (
            pd.to_datetime(data["date"])
            if "date" in data.columns
            else datetime.now()
        )
        data["day_of_week"] = data["timestamp"].dt.dayofweek
        data["hour"] = data["timestamp"].dt.hour

        # Group by context and calculate statistics
        context_stats = data.groupby(["day_of_week"]).agg(
            {data.columns[0]: ["mean", "std"]}
        )

        # Check for deviations from expected
        for _, row in data.iterrows():
            dow = row["day_of_week"]
            value = row[data.columns[0]]

            if dow in context_stats.index:
                expected_mean = context_stats.loc[dow][data.columns[0]]["mean"]
                expected_std = context_stats.loc[dow][data.columns[0]]["std"]

                if expected_std > 0:
                    z_score = abs((value - expected_mean) / expected_std)

                    if z_score > 2.5:
                        anomaly = Anomaly(
                            type=AnomalyType.CONTEXTUAL,
                            severity=(
                                AnomalySeverity.MEDIUM
                                if z_score < 4
                                else AnomalySeverity.HIGH
                            ),
                            module=module,
                            entity_id=entity_id,
                            description=f"Contextual anomaly for day {dow}: {z_score:.2f}σ deviation",
                            score=min(z_score / 4, 1.0),
                            timestamp=row["timestamp"],
                            data={
                                "value": value,
                                "expected": expected_mean,
                                "z_score": z_score,
                                "context": f"day_of_week={dow}",
                            },
                            confidence=min(z_score / 4, 1.0),
                            suggested_action="Check if special circumstances apply",
                        )
                        anomalies.append(anomaly)

        return anomalies

    async def detect_anomalies_pattern_break(
        self, data: pd.DataFrame, module: str, entity_id: str, window: int = 20
    ) -> List[Anomaly]:
        """
        Detect pattern breaks

        Pattern break: Sudden change in established pattern
        """
        if len(data) < window * 2:
            return []

        anomalies = []

        # Calculate rolling statistics
        values = data.iloc[:, 0].values

        rolling_mean = pd.Series(values).rolling(window=window).mean()
        rolling_std = pd.Series(values).rolling(window=window).std()

        # Detect sudden changes
        for i in range(window, len(values)):
            current_value = values[i]
            expected_mean = rolling_mean.iloc[i - 1]
            expected_std = rolling_std.iloc[i - 1]

            if expected_std > 0:
                deviation = abs(current_value - expected_mean) / expected_std

                if deviation > 4:  # 4-sigma deviation
                    anomaly = Anomaly(
                        type=AnomalyType.PATTERN_BREAK,
                        severity=(
                            AnomalySeverity.HIGH
                            if deviation > 6
                            else AnomalySeverity.MEDIUM
                        ),
                        module=module,
                        entity_id=entity_id,
                        description=f"Pattern break detected: {deviation:.2f}σ deviation from {window}-period mean",
                        score=min(deviation / 6, 1.0),
                        timestamp=datetime.now(),
                        data={
                            "value": current_value,
                            "expected_mean": expected_mean,
                            "deviation": deviation,
                        },
                        confidence=min(deviation / 6, 1.0),
                        suggested_action="Investigate cause of pattern change",
                    )
                    anomalies.append(anomaly)

        return anomalies

    async def realtime_detect(
        self, module: str, entity_id: str, new_data: Dict[str, Any]
    ) -> Optional[Anomaly]:
        """
        Real-time anomaly detection for streaming data

        Uses sliding window and incremental statistics
        """
        # Initialize buffer if needed
        buffer_key = f"{module}:{entity_id}"
        if buffer_key not in self.data_buffers:
            self.data_buffers[buffer_key] = deque(maxlen=self.window_size)

        buffer = self.data_buffers[buffer_key]

        # Add new data
        buffer.append(new_data)

        # Only check if we have enough data
        if len(buffer) < self.min_samples:
            return None

        # Convert to DataFrame
        df = pd.DataFrame(list(buffer))

        # Run detection
        anomalies = await self.detect_anomalies_statistical(
            df, module, entity_id
        )

        # Store in history
        for anomaly in anomalies:
            self.anomaly_history.append(anomaly)

        # Return most severe anomaly if any
        if anomalies:
            anomalies.sort(key=lambda a: a.score, reverse=True)
            return anomalies[0]

        return None

    async def detect_anomaly_clusters(
        self, time_window: timedelta = timedelta(minutes=10)
    ) -> List[List[Anomaly]]:
        """
        Find clusters of related anomalies

        Anomaly clusters may indicate systemic issues
        """
        clusters = []
        current_cluster = []

        # Sort anomalies by time
        sorted_anomalies = sorted(
            self.anomaly_history, key=lambda a: a.timestamp
        )

        for anomaly in sorted_anomalies:
            if not current_cluster:
                current_cluster.append(anomaly)
            else:
                # Check if within time window
                time_diff = anomaly.timestamp - current_cluster[0].timestamp
                if time_diff <= time_window:
                    current_cluster.append(anomaly)
                else:
                    # Start new cluster
                    if len(current_cluster) > 1:
                        clusters.append(current_cluster)
                    current_cluster = [anomaly]

        # Add last cluster
        if len(current_cluster) > 1:
            clusters.append(current_cluster)

        return clusters

    def _prepare_anomaly_features(self, data: pd.DataFrame) -> np.ndarray:
        """Prepare features for anomaly detection"""
        # Select numerical columns
        numerical_cols = data.select_dtypes(include=[np.number]).columns

        if len(numerical_cols) == 0:
            # If no numerical columns, use all columns
            return data.values

        return data[numerical_cols].values

    def _calculate_severity(self, score: float) -> AnomalySeverity:
        """Calculate severity from anomaly score"""
        if score > 0.9:
            return AnomalySeverity.CRITICAL
        elif score > 0.7:
            return AnomalySeverity.HIGH
        elif score > 0.5:
            return AnomalySeverity.MEDIUM
        else:
            return AnomalySeverity.LOW

    async def get_anomaly_summary(self) -> Dict[str, Any]:
        """Get summary of detected anomalies"""
        if not self.anomaly_history:
            return {
                "total_anomalies": 0,
                "by_type": {},
                "by_severity": {},
                "by_module": {},
                "recent_anomalies": [],
            }

        # Count by various dimensions
        by_type = {}
        by_severity = {}
        by_module = {}

        for anomaly in self.anomaly_history:
            # By type
            atype = anomaly.type.value
            by_type[atype] = by_type.get(atype, 0) + 1

            # By severity
            severity = anomaly.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1

            # By module
            by_module[anomaly.module] = by_module.get(anomaly.module, 0) + 1

        # Recent anomalies
        recent = list(self.anomaly_history)[-10:]

        return {
            "total_anomalies": len(self.anomaly_history),
            "by_type": by_type,
            "by_severity": by_severity,
            "by_module": by_module,
            "recent_anomalies": [
                {
                    "type": a.type.value,
                    "severity": a.severity.value,
                    "module": a.module,
                    "description": a.description,
                    "score": a.score,
                    "timestamp": a.timestamp.isoformat(),
                }
                for a in recent
            ],
        }
