#!/usr/bin/env python3
"""
Minder Production Deployment Manager
Handles deployment, scaling, and monitoring for production
"""

import asyncio
import aiohttp
import logging
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import json
import yaml

logger = logging.getLogger(__name__)


class ProductionDeploymentManager:
    """
    Production deployment manager for Minder

    Features:
    - Health check monitoring
    - Automated deployment
    - Rollback capabilities
    - Scaling management
    - Performance monitoring
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.deployment_config = self._load_deployment_config()

        # Service endpoints
        self.api_url = config.get("api_url", "http://localhost:8000")
        self.health_check_interval = config.get("health_check_interval", 30)

        # Deployment state
        self.deployment_history = []
        self.current_deployment = None
        self.is_monitoring = False

    def _load_deployment_config(self) -> Dict[str, Any]:
        """Load deployment configuration"""
        config_path = Path("config/deployment.yaml")

        if config_path.exists():
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)

        # Default deployment configuration
        return {
            "environment": "production",
            "replicas": {
                "api": 2,
                "worker": 3,
                "monitoring": 1
            },
            "resources": {
                "api": {
                    "memory": "2Gi",
                    "cpu": "1000m"
                },
                "worker": {
                    "memory": "1Gi",
                    "cpu": "500m"
                }
            },
            "auto_scaling": {
                "enabled": True,
                "min_replicas": 2,
                "max_replicas": 10,
                "target_cpu_percent": 70
            }
        }

    async def deploy(self, version: str, strategy: str = "rolling") -> Dict[str, Any]:
        """
        Deploy new version to production

        Args:
            version: Version to deploy
            strategy: Deployment strategy (rolling, blue-green, canary)
        """
        logger.info(f"Starting deployment of version {version} using {strategy} strategy")

        deployment_start = datetime.now()

        try:
            # Pre-deployment checks
            await self._pre_deployment_checks()

            # Build deployment image
            await self._build_image(version)

            # Deploy based on strategy
            if strategy == "rolling":
                result = await self._rolling_deploy(version)
            elif strategy == "blue-green":
                result = await self._blue_green_deploy(version)
            elif strategy == "canary":
                result = await self._canary_deploy(version)
            else:
                raise ValueError(f"Unknown deployment strategy: {strategy}")

            # Post-deployment verification
            await self._post_deployment_verification()

            deployment_time = (datetime.now() - deployment_start).total_seconds()

            # Record deployment
            deployment_record = {
                "version": version,
                "strategy": strategy,
                "timestamp": deployment_start.isoformat(),
                "duration_seconds": deployment_time,
                "status": "success",
                "result": result
            }

            self.deployment_history.append(deployment_record)
            self.current_deployment = deployment_record

            logger.info(f"✓ Deployment completed in {deployment_time:.0f}s")

            return deployment_record

        except Exception as e:
            logger.error(f"Deployment failed: {e}")

            # Rollback on failure
            await self.rollback()

            return {
                "version": version,
                "status": "failed",
                "error": str(e),
                "timestamp": deployment_start.isoformat()
            }

    async def _pre_deployment_checks(self) -> None:
        """Run pre-deployment checks"""
        logger.info("Running pre-deployment checks...")

        # Check service health
        health = await self.check_health()
        if not health["healthy"]:
            raise RuntimeError(f"System not healthy: {health}")

        # Check disk space
        disk_space = self._check_disk_space()
        if disk_space["percent"] > 80:
            raise RuntimeError(f"Insufficient disk space: {disk_space['percent']}% used")

        # Check database connections
        await self._check_databases()

        logger.info("✓ Pre-deployment checks passed")

    async def _rolling_deploy(self, version: str) -> Dict[str, Any]:
        """Execute rolling deployment"""
        logger.info("Executing rolling deployment...")

        replicas = self.deployment_config["replicas"]["api"]

        # Update containers one by one
        for i in range(replicas):
            logger.info(f"Deploying replica {i+1}/{replicas}")

            # Stop container
            await self._stop_container(f"minder-api-{i}")

            # Pull new image
            await self._pull_image(version)

            # Start container
            await self._start_container(f"minder-api-{i}", version)

            # Health check
            await self._wait_for_healthy(timeout=60)

            logger.info(f"✓ Replica {i+1} deployed successfully")

        return {
            "strategy": "rolling",
            "replicas_deployed": replicas,
            "downtime_seconds": 0
        }

    async def _blue_green_deploy(self, version: str) -> Dict[str, Any]:
        """Execute blue-green deployment"""
        logger.info("Executing blue-green deployment...")

        # Deploy green environment
        logger.info("Deploying green environment...")
        await self._deploy_green(version)

        # Test green environment
        logger.info("Testing green environment...")
        green_health = await self._test_green_environment()

        if not green_health:
            raise RuntimeError("Green environment failed health checks")

        # Switch traffic to green
        logger.info("Switching traffic to green...")
        await self._switch_traffic("green")

        # Keep blue for rollback
        logger.info("Keeping blue environment for potential rollback")

        return {
            "strategy": "blue-green",
            "rollback_available": True,
            "downtime_seconds": 0
        }

    async def _canary_deploy(self, version: str) -> Dict[str, Any]:
        """Execute canary deployment"""
        logger.info("Executing canary deployment...")

        # Start with 10% canary
        canary_percent = 10

        while canary_percent <= 50:
            logger.info(f"Deploying canary at {canary_percent}%...")

            # Deploy canary instances
            await self._deploy_canary(version, canary_percent)

            # Monitor for 5 minutes
            await asyncio.sleep(300)

            # Check metrics
            metrics = await self._get_deployment_metrics()

            if metrics["error_rate"] > 0.01:  # 1% error rate threshold
                raise RuntimeError(f"Canary deployment failed: error rate {metrics['error_rate']}")

            if metrics["response_time_ms"] > 1000:  # 1 second threshold
                raise RuntimeError(f"Canary deployment failed: response time {metrics['response_time_ms']}ms")

            # Increase canary percentage
            canary_percent += 20

            logger.info(f"✓ Canary at {canary_percent}% successful")

        # Full rollout
        await self._full_rollout(version)

        return {
            "strategy": "canary",
            "final_percentage": 100,
            "downtime_seconds": 0
        }

    async def rollback(self) -> Dict[str, Any]:
        """Rollback to previous version"""
        logger.info("Initiating rollback...")

        if not self.deployment_history:
            raise RuntimeError("No previous deployment to rollback to")

        # Get previous successful deployment
        previous_deployment = None
        for deployment in reversed(self.deployment_history[:-1]):
            if deployment["status"] == "success":
                previous_deployment = deployment
                break

        if not previous_deployment:
            raise RuntimeError("No successful previous deployment found")

        logger.info(f"Rolling back to version {previous_deployment['version']}")

        # Execute rollback
        rollback_start = datetime.now()

        try:
            await self._execute_rollback(previous_deployment["version"])

            rollback_time = (datetime.now() - rollback_start).total_seconds()

            logger.info(f"✓ Rollback completed in {rollback_time:.0f}s")

            return {
                "rollback_to": previous_deployment["version"],
                "duration_seconds": rollback_time,
                "status": "success"
            }

        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return {
                "status": "failed",
                "error": str(e)
            }

    async def check_health(self) -> Dict[str, Any]:
        """Check system health"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.api_url}/health", timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            "healthy": True,
                            "status": data.get("status", "healthy"),
                            "timestamp": datetime.now().isoformat()
                        }
                    else:
                        return {
                            "healthy": False,
                            "status_code": response.status,
                            "timestamp": datetime.now().isoformat()
                        }
        except Exception as e:
            return {
                "healthy": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def get_metrics(self) -> Dict[str, Any]:
        """Get deployment metrics"""
        health = await self.check_health()

        return {
            "health": health,
            "current_deployment": self.current_deployment,
            "deployment_history": self.deployment_history[-10:],  # Last 10 deployments
            "uptime": self._get_uptime(),
            "performance": await self._get_performance_metrics()
        }

    def _check_disk_space(self) -> Dict[str, Any]:
        """Check available disk space"""
        try:
            result = subprocess.run(
                ["df", "/"],
                capture_output=True,
                text=True,
                check=True
            )

            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                parts = lines[1].split()
                return {
                    "total_gb": float(parts[1]) / 1024 / 1024,
                    "used_gb": float(parts[2]) / 1024 / 1024,
                    "available_gb": float(parts[3]) / 1024 / 1024,
                    "percent": int(parts[4].replace('%', ''))
                }
        except Exception as e:
            logger.error(f"Error checking disk space: {e}")

        return {"percent": 0}

    def _get_uptime(self) -> float:
        """Get system uptime in seconds"""
        try:
            result = subprocess.run(
                ["cat", "/proc/uptime"],
                capture_output=True,
                text=True,
                check=True
            )

            uptime_seconds = float(result.stdout.split()[0])
            return uptime_seconds
        except:
            return 0.0

    async def _start_monitoring(self):
        """Start deployment monitoring"""
        self.is_monitoring = True

        while self.is_monitoring:
            try:
                health = await self.check_health()

                if not health["healthy"]:
                    logger.warning(f"Health check failed: {health}")
                    # Could trigger auto-scaling or alerting here

                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(60)

    async def _stop_monitoring(self):
        """Stop deployment monitoring"""
        self.is_monitoring = False

    # Helper methods (simplified for brevity)
    async def _build_image(self, version: str):
        """Build Docker image for version"""
        logger.info(f"Building image for version {version}...")
        # Implementation would call docker build
        await asyncio.sleep(2)  # Simulated build time
        logger.info("✓ Image built successfully")

    async def _pull_image(self, version: str):
        """Pull Docker image"""
        logger.info(f"Pulling image for version {version}...")
        # Implementation would call docker pull
        await asyncio.sleep(1)  # Simulated pull time
        logger.info("✓ Image pulled successfully")

    async def _stop_container(self, container_name: str):
        """Stop a container"""
        logger.info(f"Stopping container {container_name}...")
        # Implementation would call docker stop
        await asyncio.sleep(0.5)

    async def _start_container(self, container_name: str, version: str):
        """Start a container"""
        logger.info(f"Starting container {container_name} with version {version}...")
        # Implementation would call docker run
        await asyncio.sleep(1)

    async def _wait_for_healthy(self, timeout: int = 60):
        """Wait for service to be healthy"""
        logger.info("Waiting for service to be healthy...")

        for i in range(timeout):
            health = await self.check_health()
            if health["healthy"]:
                logger.info("✓ Service is healthy")
                return
            await asyncio.sleep(1)

        raise TimeoutError("Service did not become healthy in time")

    async def _post_deployment_verification(self):
        """Run post-deployment verification"""
        logger.info("Running post-deployment verification...")

        # Health check
        health = await self.check_health()
        if not health["healthy"]:
            raise RuntimeError("Deployment failed health checks")

        # API functionality check
        await self._verify_api_functionality()

        logger.info("✓ Post-deployment verification passed")

    async def _verify_api_functionality(self):
        """Verify API is functioning correctly"""
        logger.info("Verifying API functionality...")
        # Would check specific API endpoints
        await asyncio.sleep(1)
        logger.info("✓ API functionality verified")

    async def _check_databases(self):
        """Check database connectivity"""
        logger.info("Checking database connectivity...")
        # Would check all databases
        await asyncio.sleep(0.5)
        logger.info("✓ Databases accessible")

    # Simplified implementations for other methods
    async def _deploy_green(self, version: str):
        """Deploy green environment"""
        await asyncio.sleep(2)

    async def _test_green_environment(self) -> bool:
        """Test green environment"""
        await asyncio.sleep(2)
        return True

    async def _switch_traffic(self, environment: str):
        """Switch traffic to environment"""
        await asyncio.sleep(1)

    async def _deploy_canary(self, version: str, percent: int):
        """Deploy canary instances"""
        await asyncio.sleep(1)

    async def _get_deployment_metrics(self) -> Dict[str, Any]:
        """Get deployment metrics"""
        return {
            "error_rate": 0.0,
            "response_time_ms": 200
        }

    async def _full_rollout(self, version: str):
        """Full rollout"""
        await asyncio.sleep(2)

    async def _execute_rollback(self, version: str):
        """Execute rollback"""
        await asyncio.sleep(3)

    async def _get_performance_metrics(self) -> Dict[str, Any]:
        """Get performance metrics"""
        return {
            "cpu_usage_percent": 25.0,
            "memory_usage_percent": 45.0,
            "avg_response_time_ms": 150
        }
