"""
Advanced Correlation Algorithms
Implements Granger Causality, DTW, Cross-Correlation, and Mutual Information
"""

from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import logging
from scipy import signal
from scipy.stats import pearsonr, spearmanr, entropy
from scipy.spatial.distance import euclidean
from dtaidistance import dtw
import asyncio

logger = logging.getLogger(__name__)


class AdvancedCorrelationEngine:
    """
    Advanced correlation discovery algorithms

    Algorithms:
    - Granger Causality: Temporal causality testing
    - DTW (Dynamic Time Warping): Similarity in time series with different speeds
    - Cross-Correlation: Lagged correlations
    - Mutual Information: Non-linear dependencies
    - Cointegration: Long-term relationship in non-stationary series
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.significance_level = config.get("significance_level", 0.05)
        self.max_lag = config.get("max_lag", 30)
        self.min_samples = config.get("min_samples", 100)

    async def granger_causality_test(
        self, series1: np.ndarray, series2: np.ndarray, max_lag: int = 10
    ) -> Dict[str, Any]:
        """
        Test if series1 Granger-causes series2

        Granger causality: Past values of X help predict Y better than past values of Y alone

        Returns:
            p_value: Significance of causality
            f_statistic: Test statistic
            is_significant: Whether causality is significant
        """
        try:
            from statsmodels.tsa.stattools import grangercausalitytests

            # Prepare data
            data = np.column_stack([series1, series2])

            # Ensure we have enough data
            if len(data) < max_lag + self.min_samples:
                return {
                    "error": "Insufficient data for Granger causality test",
                    "min_required": max_lag + self.min_samples,
                    "actual": len(data),
                }

            # Perform test
            result = grangercausalitytests(data, max_lag, verbose=False)

            # Extract p-values for each lag
            p_values = [test[0]["ssr_ftest"][1] for test in result]

            # Minimum p-value across all lags
            min_p_value = min(p_values)
            best_lag = p_values.index(min_p_value) + 1

            # F-statistic for best lag
            f_statistic = result[best_lag - 1][0]["ssr_ftest"][0]

            return {
                "p_value": min_p_value,
                "f_statistic": f_statistic,
                "best_lag": best_lag,
                "is_significant": min_p_value < self.significance_level,
                "confidence": 1 - min_p_value,
                "all_p_values": p_values,
                "interpretation": self._interpret_granger(
                    min_p_value, best_lag
                ),
            }

        except Exception as e:
            logger.error(f"Granger causality test failed: {e}")
            return {"error": str(e)}

    async def dynamic_time_warping(
        self,
        series1: np.ndarray,
        series2: np.ndarray,
        window: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculate DTW distance between two time series

        DTW measures similarity between two sequences that may vary in speed
        Lower distance = more similar
        """
        try:
            # Normalize series
            series1_norm = (series1 - np.mean(series1)) / (
                np.std(series1) + 1e-8
            )
            series2_norm = (series2 - np.mean(series2)) / (
                np.std(series2) + 1e-8
            )

            # Calculate DTW distance
            if window:
                distance = dtw.distance(
                    series1_norm, series2_norm, window=window
                )
            else:
                distance = dtw.distance(series1_norm, series2_norm)

            # Normalize by length
            normalized_distance = distance / (len(series1) + len(series2))

            # Calculate similarity score (0-1, higher = more similar)
            similarity = max(0, 1 - normalized_distance / 10)

            return {
                "dtw_distance": float(distance),
                "normalized_distance": float(normalized_distance),
                "similarity_score": float(similarity),
                "window": window,
                "interpretation": self._interpret_dtw(similarity),
            }

        except Exception as e:
            logger.error(f"DTW calculation failed: {e}")
            return {"error": str(e)}

    async def cross_correlation(
        self, series1: np.ndarray, series2: np.ndarray, max_lag: int = 30
    ) -> Dict[str, Any]:
        """
        Calculate cross-correlation between two series

        Finds lag at which correlation is maximized
        """
        try:
            # Ensure same length
            min_len = min(len(series1), len(series2))
            series1 = series1[:min_len]
            series2 = series2[:min_len]

            # Calculate cross-correlation
            correlation = signal.correlate(series1, series2, mode="same")
            lags = signal.correlation_lags(
                len(series1), len(series2), mode="same"
            )

            # Normalize
            correlation = correlation / (
                np.std(series1) * np.std(series2) * min_len
            )

            # Find maximum correlation and its lag
            max_idx = np.argmax(np.abs(correlation))
            max_corr = correlation[max_idx]
            best_lag = lags[max_idx]

            # Calculate significance
            # Approximate confidence interval
            n = len(series1)
            se = 1 / np.sqrt(n)
            ci = 1.96 * se  # 95% confidence interval

            return {
                "max_correlation": float(max_corr),
                "best_lag": int(best_lag),
                "is_significant": abs(max_corr) > ci,
                "confidence_interval": float(ci),
                "all_correlations": dict(
                    zip(lags.tolist(), correlation.tolist())
                ),
                "interpretation": self._interpret_cross_correlation(
                    max_corr, best_lag
                ),
            }

        except Exception as e:
            logger.error(f"Cross-correlation failed: {e}")
            return {"error": str(e)}

    async def mutual_information(
        self, series1: np.ndarray, series2: np.ndarray, bins: int = 50
    ) -> Dict[str, Any]:
        """
        Calculate mutual information between two series

        MI measures non-linear dependence
        Higher MI = more dependent
        """
        try:
            # Discretize data
            hist_2d, x_edges, y_edges = np.histogram2d(
                series1, series2, bins=bins
            )

            # Calculate joint and marginal probabilities
            pxy = hist_2d / float(np.sum(hist_2d))
            px = np.sum(pxy, axis=1)
            py = np.sum(pxy, axis=0)

            # Calculate mutual information
            mi = 0.0
            for i in range(len(px)):
                for j in range(len(py)):
                    if pxy[i, j] > 0:
                        mi += pxy[i, j] * np.log(
                            pxy[i, j] / (px[i] * py[j] + 1e-10) + 1e-10
                        )

            # Normalize MI
            # Maximum possible MI is min(entropy(X), entropy(Y))
            entropy_x = entropy(px + 1e-10)
            entropy_y = entropy(py + 1e-10)
            max_mi = min(entropy_x, entropy_y)

            normalized_mi = mi / (max_mi + 1e-10)

            return {
                "mutual_information": float(mi),
                "normalized_mi": float(normalized_mi),
                "entropy_x": float(entropy_x),
                "entropy_y": float(entropy_y),
                "interpretation": self._interpret_mi(normalized_mi),
            }

        except Exception as e:
            logger.error(f"Mutual information calculation failed: {e}")
            return {"error": str(e)}

    async def cointegration_test(
        self, series1: np.ndarray, series2: np.ndarray
    ) -> Dict[str, Any]:
        """
        Test if two series are cointegrated

        Cointegration: Long-term relationship in non-stationary series
        """
        try:
            from statsmodels.tsa.stattools import coint

            # Perform test
            t_stat, p_value, crit_value = coint(series1, series2)

            return {
                "t_statistic": float(t_stat),
                "p_value": float(p_value),
                "critical_value": float(crit_value),
                "is_cointegrated": p_value < self.significance_level,
                "confidence": 1 - p_value,
                "interpretation": self._interpret_cointegration(p_value),
            }

        except Exception as e:
            logger.error(f"Cointegration test failed: {e}")
            return {"error": str(e)}

    async def comprehensive_correlation_analysis(
        self,
        series1: np.ndarray,
        series2: np.ndarray,
        series1_name: str = "series1",
        series2_name: str = "series2",
    ) -> Dict[str, Any]:
        """
        Run all correlation algorithms and synthesize results

        Returns comprehensive correlation analysis
        """
        results = {}

        # 1. Pearson correlation
        pearson_corr, pearson_p = pearsonr(series1, series2)
        results["pearson"] = {
            "correlation": float(pearson_corr),
            "p_value": float(pearson_p),
            "is_significant": pearson_p < self.significance_level,
        }

        # 2. Spearman correlation
        spearman_corr, spearman_p = spearmanr(series1, series2)
        results["spearman"] = {
            "correlation": float(spearman_corr),
            "p_value": float(spearman_p),
            "is_significant": spearman_p < self.significance_level,
        }

        # 3. Cross-correlation
        results["cross_correlation"] = await self.cross_correlation(
            series1, series2
        )

        # 4. Granger causality (both directions)
        results["granger_1_to_2"] = await self.granger_causality_test(
            series1, series2
        )
        results["granger_2_to_1"] = await self.granger_causality_test(
            series2, series1
        )

        # 5. DTW
        results["dtw"] = await self.dynamic_time_warping(series1, series2)

        # 6. Mutual Information
        results["mutual_information"] = await self.mutual_information(
            series1, series2
        )

        # 7. Cointegration
        results["cointegration"] = await self.cointegration_test(
            series1, series2
        )

        # Synthesize overall correlation strength
        overall_strength = self._calculate_overall_strength(results)

        # Determine relationship type
        relationship_type = self._determine_relationship_type(results)

        return {
            "series1": series1_name,
            "series2": series2_name,
            "overall_strength": overall_strength,
            "relationship_type": relationship_type,
            "detailed_results": results,
            "summary": self._generate_summary(results, relationship_type),
            "timestamp": datetime.now().isoformat(),
        }

    async def discover_complex_correlations(
        self, data_dict: Dict[str, np.ndarray], min_strength: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Discover correlations across multiple data series

        Uses all algorithms and finds strongest relationships
        """
        correlations = []

        series_names = list(data_dict.keys())

        # Compare all pairs
        for i, name1 in enumerate(series_names):
            for name2 in series_names[i + 1 :]:
                series1 = data_dict[name1]
                series2 = data_dict[name2]

                # Ensure same length
                min_len = min(len(series1), len(series2))
                series1 = series1[:min_len]
                series2 = series2[:min_len]

                # Comprehensive analysis
                result = await self.comprehensive_correlation_analysis(
                    series1, series2, name1, name2
                )

                # Filter by strength
                if result["overall_strength"] >= min_strength:
                    correlations.append(result)

        # Sort by strength
        correlations.sort(key=lambda x: x["overall_strength"], reverse=True)

        return correlations

    def _interpret_granger(self, p_value: float, lag: int) -> str:
        """Interpret Granger causality results"""
        if p_value < 0.01:
            return f"Strong evidence of Granger causality at lag {lag}"
        elif p_value < 0.05:
            return f"Moderate evidence of Granger causality at lag {lag}"
        elif p_value < 0.1:
            return f"Weak evidence of Granger causality at lag {lag}"
        else:
            return "No significant Granger causality detected"

    def _interpret_dtw(self, similarity: float) -> str:
        """Interpret DTW similarity"""
        if similarity > 0.9:
            return "Very strong pattern similarity"
        elif similarity > 0.7:
            return "Strong pattern similarity"
        elif similarity > 0.5:
            return "Moderate pattern similarity"
        else:
            return "Weak pattern similarity"

    def _interpret_cross_correlation(self, corr: float, lag: int) -> str:
        """Interpret cross-correlation results"""
        direction = "leads" if lag < 0 else "lags"
        if abs(corr) > 0.8:
            strength = "Very strong"
        elif abs(corr) > 0.6:
            strength = "Strong"
        elif abs(corr) > 0.4:
            strength = "Moderate"
        else:
            strength = "Weak"

        return f"{strength} {'positive' if corr > 0 else 'negative'} correlation, {direction} by {abs(lag)} periods"

    def _interpret_mi(self, mi: float) -> str:
        """Interpret mutual information"""
        if mi > 0.7:
            return "Very strong dependence"
        elif mi > 0.5:
            return "Strong dependence"
        elif mi > 0.3:
            return "Moderate dependence"
        else:
            return "Weak dependence"

    def _interpret_cointegration(self, p_value: float) -> str:
        """Interpret cointegration test"""
        if p_value < 0.01:
            return "Strong evidence of cointegration (long-term relationship)"
        elif p_value < 0.05:
            return "Moderate evidence of cointegration"
        elif p_value < 0.1:
            return "Weak evidence of cointegration"
        else:
            return "No significant cointegration detected"

    def _calculate_overall_strength(self, results: Dict[str, Any]) -> float:
        """Calculate overall correlation strength (0-1)"""
        scores = []

        # Pearson correlation
        if "pearson" in results:
            pearson_strength = abs(results["pearson"]["correlation"])
            scores.append(pearson_strength)

        # Cross-correlation max
        if (
            "cross_correlation" in results
            and "max_correlation" in results["cross_correlation"]
        ):
            cc_strength = abs(results["cross_correlation"]["max_correlation"])
            scores.append(cc_strength)

        # DTW similarity
        if "dtw" in results and "similarity_score" in results["dtw"]:
            dtw_strength = results["dtw"]["similarity_score"]
            scores.append(dtw_strength)

        # Mutual information (normalized)
        if (
            "mutual_information" in results
            and "normalized_mi" in results["mutual_information"]
        ):
            mi_strength = results["mutual_information"]["normalized_mi"]
            scores.append(mi_strength)

        # Average of all scores
        return np.mean(scores) if scores else 0.0

    def _determine_relationship_type(self, results: Dict[str, Any]) -> str:
        """Determine type of relationship"""
        # Check Granger causality
        gc_1_to_2 = results.get("granger_1_to_2", {})
        gc_2_to_1 = results.get("granger_2_to_1", {})

        if gc_1_to_2.get("is_significant") and not gc_2_to_1.get(
            "is_significant"
        ):
            return "unidirectional_causality"
        elif gc_2_to_1.get("is_significant") and not gc_1_to_2.get(
            "is_significant"
        ):
            return "reverse_causality"
        elif gc_1_to_2.get("is_significant") and gc_2_to_1.get(
            "is_significant"
        ):
            return "bidirectional_causality"

        # Check cointegration
        if results.get("cointegration", {}).get("is_cointegrated"):
            return "long_term_relationship"

        # Check correlation strength
        pearson = results.get("pearson", {}).get("correlation", 0)
        if abs(pearson) > 0.7:
            return "strong_correlation"
        elif abs(pearson) > 0.4:
            return "moderate_correlation"
        else:
            return "weak_correlation"

    def _generate_summary(
        self, results: Dict[str, Any], relationship_type: str
    ) -> str:
        """Generate human-readable summary"""
        summary_parts = []

        # Add relationship type
        summary_parts.append(f"Relationship type: {relationship_type}")

        # Add Pearson correlation
        if "pearson" in results:
            corr = results["pearson"]["correlation"]
            summary_parts.append(f"Pearson correlation: {corr:.3f}")

        # Add Granger causality
        if "granger_1_to_2" in results:
            gc = results["granger_1_to_2"]
            if gc.get("is_significant"):
                summary_parts.append(
                    f"Granger causality detected at lag {gc.get('best_lag')}"
                )

        # Add DTW
        if "dtw" in results:
            dtw_sim = results["dtw"].get("similarity_score", 0)
            summary_parts.append(f"Pattern similarity: {dtw_sim:.2%}")

        # Add cointegration
        if "cointegration" in results:
            coint = results["cointegration"]
            if coint.get("is_cointegrated"):
                summary_parts.append("Cointegrated (long-term relationship)")

        return " | ".join(summary_parts)
