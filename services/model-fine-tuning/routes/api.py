"""
Model Fine-Tuning API Routes
"""
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict

from fastapi import BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from core.fine_tuning_engine import FineTuningEngine
from models.schemas import (
    DatasetUploadResponse,
    TrainingJobCreate,
    TrainingJobResponse,
)

logger = logging.getLogger(__name__)

# Configuration (will be moved to config module)
TRAINING_DATA_PATH = Path("/app/training-data")
MODELS_OUTPUT_PATH = Path("/app/models")

# Create directories
TRAINING_DATA_PATH.mkdir(parents=True, exist_ok=True)
MODELS_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

# In-Memory Storage (use PostgreSQL in production)
training_jobs: Dict[str, Dict] = {}
datasets: Dict[str, Dict] = {}


async def health_check_handler():
    """Service health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "training_jobs": len(training_jobs),
        "datasets": len(datasets),
    }


async def metrics_handler():
    """Prometheus metrics endpoint"""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


async def initialize_engine_handler(engine: FineTuningEngine):
    """Initialize fine-tuning engine endpoint"""
    try:
        await engine.initialize()
        return {"message": "Fine-tuning engine initialized successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def upload_dataset_handler(file: UploadFile = File(...)):
    """Upload training dataset endpoint"""
    # Validate file format
    if not file.filename.endswith((".json", ".jsonl")):
        raise HTTPException(status_code=400, detail="Dataset must be JSON or JSONL format")

    # Save file
    dataset_id = str(uuid.uuid4())
    dataset_path = TRAINING_DATA_PATH / f"{dataset_id}_{file.filename}"

    content = await file.read()
    dataset_path.write_bytes(content)

    # Validate dataset
    validation_passed = True
    errors = []
    samples_count = 0

    try:
        import json

        if file.filename.endswith(".json"):
            data = json.loads(content)
            samples_count = len(data)

            # Validate structure
            if not isinstance(data, list):
                errors.append("JSON must contain a list of examples")
                validation_passed = False
            else:
                # Check first example
                if len(data) > 0:
                    if not isinstance(data[0], dict):
                        errors.append("Each example must be a dictionary")
                        validation_passed = False

        elif file.filename.endswith(".jsonl"):
            # Count lines
            samples_count = content.decode("utf-8").count("\n")

    except Exception as e:
        errors.append(f"Validation error: {str(e)}")
        validation_passed = False

    # Store dataset metadata
    datasets[dataset_id] = {
        "id": dataset_id,
        "filename": file.filename,
        "path": str(dataset_path),
        "samples_count": samples_count,
        "format": file.filename.split(".")[-1],
        "size_bytes": len(content),
        "validation_passed": validation_passed,
        "errors": errors,
        "uploaded_at": datetime.now().isoformat(),
    }

    logger.info(f"✅ Dataset uploaded: {file.filename} ({samples_count} samples)")

    return DatasetUploadResponse(
        filename=file.filename,
        samples_count=samples_count,
        format=file.filename.split(".")[-1],
        size_bytes=len(content),
        validation_passed=validation_passed,
        errors=errors,
    )


async def list_datasets_handler():
    """List all datasets endpoint"""
    return list(datasets.values())


async def create_training_job_handler(
    request: TrainingJobCreate,
    background_tasks: BackgroundTasks,
    engine: FineTuningEngine,
    training_jobs_total,
):
    """Create a new training job endpoint"""
    # Validate dataset exists
    dataset = None
    for ds in datasets.values():
        if ds["filename"] == request.dataset_file:
            dataset = ds
            break

    if not dataset:
        raise HTTPException(status_code=404, detail=f"Dataset not found: {request.dataset_file}")

    # Validate dataset
    if not dataset["validation_passed"]:
        raise HTTPException(
            status_code=400, detail=f"Dataset validation failed: {', '.join(dataset['errors'])}"
        )

    job_id = str(uuid.uuid4())

    # Create job
    training_jobs[job_id] = {
        "job_id": job_id,
        "job_name": request.job_name,
        "base_model": request.base_model,
        "dataset_file": request.dataset_file,
        "model_type": request.model_type,
        "epochs": request.epochs,
        "learning_rate": request.learning_rate,
        "batch_size": request.batch_size,
        "context_length": request.context_length,
        "description": request.description,
        "status": "pending",
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "completed_at": None,
        "current_epoch": 0,
        "loss": 0.0,
    }

    # Start training in background
    background_tasks.add_task(
        run_training_job_task, job_id, dataset["path"], engine, training_jobs_total, models_fine_tuned_total
    )

    training_jobs_total.labels(status="started").inc()

    logger.info(f"✅ Training job created: {job_id}")

    return TrainingJobResponse(**training_jobs[job_id])


async def run_training_job_task(
    job_id: str,
    dataset_path: str,
    engine: FineTuningEngine,
    training_jobs_total,
    models_fine_tuned_total,
):
    """Run training job in background"""
    job = training_jobs[job_id]

    try:
        # Update status
        job["status"] = "running"
        job["started_at"] = datetime.now().isoformat()

        # Run training
        result = await engine.submit_training_job(
            job_id=job_id,
            base_model=job["base_model"],
            dataset_path=dataset_path,
            model_type=job["model_type"],
            epochs=job["epochs"],
            learning_rate=job["learning_rate"],
            batch_size=job["batch_size"],
            context_length=job["context_length"],
        )

        # Update status
        job["status"] = "completed"
        job["completed_at"] = datetime.now().isoformat()
        job["fine_tuned_model_id"] = result["model_id"]
        job["final_loss"] = result.get("final_loss", 0.0)

        # Generate model card
        model_card = await engine.generate_model_card(job_id, result["model_id"])

        # Save model card
        model_card_path = MODELS_OUTPUT_PATH / f"{result['model_id']}_README.md"
        model_card_path.write_text(model_card)

        training_jobs_total.labels(status="completed").inc()
        models_fine_tuned_total.inc()

        logger.info(f"✅ Training job completed: {job_id}")

    except Exception as e:
        job["status"] = "failed"
        job["error"] = str(e)
        job["completed_at"] = datetime.now().isoformat()

        training_jobs_total.labels(status="failed").inc()
        logger.error(f"❌ Training job failed: {job_id} - {e}")


async def list_training_jobs_handler():
    """List all training jobs endpoint"""
    return list(training_jobs.values())


async def get_training_job_handler(job_id: str):
    """Get training job details endpoint"""
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Training job not found")

    return TrainingJobResponse(**training_jobs[job_id])


async def delete_training_job_handler(job_id: str):
    """Delete training job endpoint"""
    if job_id not in training_jobs:
        raise HTTPException(status_code=404, detail="Training job not found")

    del training_jobs[job_id]

    return {"message": f"Training job {job_id} deleted"}


async def list_fine_tuned_models_handler():
    """List all fine-tuned models endpoint"""
    models = []
    for job in training_jobs.values():
        if job["status"] == "completed" and "fine_tuned_model_id" in job:
            models.append(
                {
                    "model_id": job["fine_tuned_model_id"],
                    "base_model": job["base_model"],
                    "job_name": job["job_name"],
                    "job_id": job["job_id"],
                    "created_at": job["completed_at"],
                    "final_loss": job.get("final_loss", 0),
                }
            )

    return models


async def root_handler():
    """Root endpoint"""
    return {
        "name": "Minder Model Fine-Tuning Service",
        "version": "1.0.0",
        "status": "operational",
    }
