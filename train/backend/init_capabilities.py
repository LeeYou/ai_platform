"""Auto-register capabilities from training script config.json files.

This script scans /app/scripts/*/config.json and auto-registers capabilities
into the database if they don't already exist.
"""

import json
import logging
import os
from pathlib import Path

from database import SessionLocal
from models import Capability

logger = logging.getLogger("train")


def register_capabilities_from_configs() -> None:
    """Scan training scripts directory and register all capabilities."""
    scripts_dir = Path("/app/scripts")
    if not scripts_dir.exists():
        logger.warning("Scripts directory not found: %s", scripts_dir)
        return

    db = SessionLocal()
    try:
        registered_count = 0
        skipped_count = 0

        for config_file in scripts_dir.glob("*/config.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)

                capability_name = config.get("capability")
                if not capability_name:
                    logger.warning("No 'capability' field in %s", config_file)
                    continue

                # Check if already exists
                existing = db.query(Capability).filter(
                    Capability.name == capability_name
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                # Register new capability
                capability = Capability(
                    name=capability_name,
                    name_cn=config.get("capability_name_cn", ""),
                    description=config.get("description", ""),
                    dataset_path=f"/workspace/datasets/{capability_name}",
                    script_path=f"/app/scripts/{capability_name}",
                    hyperparams=json.dumps(config.get("default_hyperparams", {})),
                )
                db.add(capability)
                registered_count += 1
                logger.info("Registered capability: %s (%s)", capability_name, capability.name_cn)

            except Exception as e:
                logger.error("Failed to process %s: %s", config_file, e)
                continue

        db.commit()
        logger.info(
            "Capability auto-registration complete: %d registered, %d skipped",
            registered_count, skipped_count
        )

    except Exception as e:
        logger.error("Capability auto-registration failed: %s", e)
        db.rollback()
    finally:
        db.close()
