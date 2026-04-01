#!/usr/bin/env python3
"""
Database migration script: Add hyperparams column to training_jobs table.

This migration adds a 'hyperparams' TEXT column to the training_jobs table
to store job-specific training parameters that override capability defaults.

Usage:
    python migrate_add_job_hyperparams.py
"""

import os
import sqlite3
import sys

DB_PATH = os.getenv("TRAIN_DB_PATH", "./data/train.db")


def main():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("No migration needed - database will be created with new schema on first run")
        return 0

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(training_jobs)")
        columns = [row[1] for row in cursor.fetchall()]

        if "hyperparams" in columns:
            print("✓ Column 'hyperparams' already exists in training_jobs table")
            print("  No migration needed")
            return 0

        # Add the column
        print("Adding 'hyperparams' column to training_jobs table...")
        cursor.execute("""
            ALTER TABLE training_jobs
            ADD COLUMN hyperparams TEXT NOT NULL DEFAULT '{}'
        """)
        conn.commit()

        print("✓ Migration completed successfully")
        print(f"  Added hyperparams column to training_jobs table in {DB_PATH}")
        return 0

    except sqlite3.Error as e:
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        conn.rollback()
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
