#!/usr/bin/env python3
"""
Minder Model Fine-tuning Script
Runs as a cron job instead of always-on service
"""
import asyncio
import sys
import logging
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, '/root/minder')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def check_pending_jobs():
    """Check for pending fine-tuning jobs in database"""
    try:
        # Import database connection
        from services.model_fine_tuning.config import get_settings
        from sqlalchemy import create_async_engine, text
        from sqlalchemy.ext.asyncio import AsyncSession

        settings = get_settings()
        engine = create_async_engine(settings.database_url, echo=False)

        async with engine.begin() as conn:
            # Check for pending jobs
            result = await conn.execute(
                text("SELECT COUNT(*) FROM fine_tuning_jobs WHERE status = 'pending'")
            )
            count = result.scalar()

        await engine.dispose()
        return count

    except Exception as e:
        logger.error(f"Error checking pending jobs: {e}")
        return 0


async def run_fine_tuning():
    """Run fine-tuning for pending jobs"""
    logger.info("Starting fine-tuning job check...")

    try:
        # Import fine-tuning service
        from services.model_fine_tuning.fine_tuner import ModelFineTuner

        # Create tuner instance
        tuner = ModelFineTuner()

        # Get pending jobs
        jobs = await tuner.get_pending_jobs()

        if not jobs:
            logger.info("No pending fine-tuning jobs found")
            return

        logger.info(f"Found {len(jobs)} pending job(s)")

        # Process each job
        for job in jobs:
            try:
                logger.info(f"Processing job: {job['id']}")

                # Run fine-tuning
                result = await tuner.fine_tune(job)

                logger.info(f"Job {job['id']} completed: {result}")

            except Exception as e:
                logger.error(f"Error processing job {job['id']}: {e}")

    except Exception as e:
        logger.error(f"Error in fine-tuning process: {e}")


async def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("Minder Model Fine-tuning Job")
    logger.info(f"Started at: {datetime.utcnow().isoformat()}")
    logger.info("=" * 60)

    try:
        # Check for pending jobs
        pending_count = await check_pending_jobs()
        logger.info(f"Pending jobs: {pending_count}")

        if pending_count > 0:
            # Run fine-tuning
            await run_fine_tuning()
        else:
            logger.info("No jobs to process")

    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("Fine-tuning job completed successfully")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
