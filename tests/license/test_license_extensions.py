import importlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "license" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


BACKEND_MODULES = [
    "main",
    "crud",
    "database",
    "key_store",
    "license_signer",
    "models",
    "schemas",
    "routers.capabilities",
    "routers.customers",
    "routers.keys",
    "routers.licenses",
    "routers.prod_tokens",
]


class LicenseAuthorizationExtensionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.temp_path = Path(cls.tempdir.name)
        cls.db_path = cls.temp_path / "license.db"
        cls.licenses_dir = cls.temp_path / "licenses"
        cls.private_keys_dir = cls.temp_path / "private_keys"
        cls.logs_dir = cls.temp_path / "logs"
        cls.admin_token = "test-admin-token"
        cls._original_env = {key: os.environ.get(key) for key in [
            "AI_LICENSE_DB",
            "LICENSES_DIR",
            "PRIVATE_KEYS_DIR",
            "LOG_DIR",
            "AI_ADMIN_TOKEN",
        ]}
        os.environ["AI_LICENSE_DB"] = str(cls.db_path)
        os.environ["LICENSES_DIR"] = str(cls.licenses_dir)
        os.environ["PRIVATE_KEYS_DIR"] = str(cls.private_keys_dir)
        os.environ["LOG_DIR"] = str(cls.logs_dir)
        os.environ["AI_ADMIN_TOKEN"] = cls.admin_token
        cls._unload_backend_modules()
        cls.backend_main = importlib.import_module("main")
        cls.client = TestClient(cls.backend_main.app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        for key, value in cls._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        cls._unload_backend_modules()
        cls.tempdir.cleanup()

    @classmethod
    def _unload_backend_modules(cls):
        database_module = sys.modules.get("database")
        if database_module is not None and hasattr(database_module, "engine"):
            database_module.engine.dispose()
        for module_name in BACKEND_MODULES:
            sys.modules.pop(module_name, None)

    def _create_customer_and_key(self):
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        suffix = self.id().split(".")[-1][-8:].upper()
        customer_id = f"CUST-{suffix}"
        customer_res = self.client.post(
            "/api/v1/customers",
            json={"customer_id": customer_id, "name": "扩展客户"},
            headers=headers,
        )
        self.assertEqual(customer_res.status_code, 201, customer_res.text)

        key_res = self.client.post(
            "/api/v1/keys",
            json={"name": f"客户专属密钥-{customer_id}"},
            headers=headers,
        )
        self.assertEqual(key_res.status_code, 201, key_res.text)
        return customer_id, key_res.json()["id"], headers

    def _remove_private_key_file(self, key_id: int):
        key_store = importlib.import_module("key_store")
        crud = importlib.import_module("crud")
        database = importlib.import_module("database")
        with database.SessionLocal() as db:
            key_pair = crud.get_key_pair(db, key_id)
            path = key_store.private_key_path_for(key_pair)
        path.unlink()

    def test_create_license_persists_and_signs_new_fields(self):
        customer_id, key_id, headers = self._create_customer_and_key()
        response = self.client.post(
            "/api/v1/licenses",
            json={
                "customer_id": customer_id,
                "key_pair_id": key_id,
                "license_type": "commercial",
                "capabilities": ["face_detect"],
                "operating_system": "linux",
                "minimum_os_version": "22.04",
                "system_architecture": "x86_64",
                "application_name": "ai-platform-prod",
                "valid_from": "2026-04-01T00:00:00+08:00",
                "valid_until": "2026-12-31T00:00:00+08:00",
                "version_constraint": ">=1.0.0",
                "max_instances": 2,
            },
            headers=headers,
        )

        self.assertEqual(response.status_code, 201, response.text)
        body = response.json()
        self.assertEqual(body["operating_system"], "linux")
        self.assertEqual(body["minimum_os_version"], "22.04")
        self.assertEqual(body["system_architecture"], "x86_64")
        self.assertEqual(body["application_name"], "ai-platform-prod")

        license_file = self.licenses_dir / f"{body['license_id']}.bin"
        self.assertTrue(license_file.exists())
        signed = json.loads(license_file.read_text(encoding="utf-8"))
        self.assertEqual(signed["operating_system"], "linux")
        self.assertEqual(signed["minimum_os_version"], "22.04")
        self.assertEqual(signed["system_architecture"], "x86_64")
        self.assertEqual(signed["application_name"], "ai-platform-prod")
        self.assertIn("signature", signed)

    def test_license_responses_include_days_remaining(self):
        customer_id, key_id, headers = self._create_customer_and_key()
        cst = timezone(timedelta(hours=8))
        valid_from = datetime.now(cst) - timedelta(days=1)
        valid_until = datetime.now(cst) + timedelta(days=10)

        create_res = self.client.post(
            "/api/v1/licenses",
            json={
                "customer_id": customer_id,
                "key_pair_id": key_id,
                "license_type": "commercial",
                "capabilities": ["face_detect"],
                "operating_system": "linux",
                "application_name": "ai-platform-prod",
                "valid_from": valid_from.isoformat(),
                "valid_until": valid_until.isoformat(),
                "version_constraint": ">=1.0.0",
                "max_instances": 2,
            },
            headers=headers,
        )
        self.assertEqual(create_res.status_code, 201, create_res.text)
        license_id = create_res.json()["license_id"]

        list_res = self.client.get("/api/v1/licenses", headers=headers)
        self.assertEqual(list_res.status_code, 200, list_res.text)
        listed = next(item for item in list_res.json() if item["license_id"] == license_id)
        self.assertEqual(listed["days_remaining"], 10)

        detail_res = self.client.get(f"/api/v1/licenses/{license_id}", headers=headers)
        self.assertEqual(detail_res.status_code, 200, detail_res.text)
        self.assertEqual(detail_res.json()["days_remaining"], 10)

    def test_create_license_rejects_invalid_operating_system(self):
        customer_id, key_id, headers = self._create_customer_and_key()
        response = self.client.post(
            "/api/v1/licenses",
            json={
                "customer_id": customer_id,
                "key_pair_id": key_id,
                "license_type": "commercial",
                "capabilities": ["face_detect"],
                "operating_system": "macos",
                "application_name": "ai-platform-prod",
                "valid_from": "2026-04-01T00:00:00+08:00",
                "valid_until": "2026-12-31T00:00:00+08:00",
                "version_constraint": ">=1.0.0",
                "max_instances": 2,
            },
            headers=headers,
        )

        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("operating_system", response.text)
        self.assertIn("must be one of: windows, linux, android, ios", response.text)

    def test_list_keys_marks_missing_private_key_as_unavailable(self):
        _, key_id, headers = self._create_customer_and_key()
        self._remove_private_key_file(key_id)

        response = self.client.get("/api/v1/keys", headers=headers)

        self.assertEqual(response.status_code, 200, response.text)
        key_data = next(item for item in response.json() if item["id"] == key_id)
        self.assertFalse(key_data["private_key_available"])

    def test_create_license_rejects_missing_private_key_with_actionable_message(self):
        customer_id, key_id, headers = self._create_customer_and_key()
        self._remove_private_key_file(key_id)

        response = self.client.post(
            "/api/v1/licenses",
            json={
                "customer_id": customer_id,
                "key_pair_id": key_id,
                "license_type": "commercial",
                "capabilities": ["face_detect"],
                "operating_system": "linux",
                "application_name": "ai-platform-prod",
                "valid_from": "2026-04-01T00:00:00+08:00",
                "valid_until": "2026-12-31T00:00:00+08:00",
                "version_constraint": ">=1.0.0",
                "max_instances": 2,
            },
            headers=headers,
        )

        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn("private key file is missing", response.text)
        self.assertIn("create/select a new key pair", response.text)

    def test_run_migrations_adds_new_license_columns(self):
        legacy_db = self.temp_path / "legacy_license.db"
        conn = sqlite3.connect(legacy_db)
        conn.execute(
            """
            CREATE TABLE license_records (
                id INTEGER PRIMARY KEY,
                license_id VARCHAR(64) NOT NULL,
                customer_id VARCHAR(32) NOT NULL,
                license_type VARCHAR(32) NOT NULL,
                capabilities TEXT NOT NULL,
                machine_fingerprint TEXT,
                valid_from DATETIME NOT NULL,
                valid_until DATETIME,
                version_constraint VARCHAR(64) NOT NULL,
                max_instances INTEGER NOT NULL,
                status VARCHAR(16) NOT NULL,
                license_content TEXT NOT NULL,
                issued_at DATETIME NOT NULL,
                created_at DATETIME
            )
            """
        )
        conn.commit()
        conn.close()

        from sqlalchemy import create_engine

        legacy_engine = create_engine(f"sqlite:///{legacy_db}", connect_args={"check_same_thread": False})
        try:
            self.backend_main._run_migrations(legacy_engine)
        finally:
            legacy_engine.dispose()

        with sqlite3.connect(legacy_db) as migrated:
            columns = {row[1] for row in migrated.execute("PRAGMA table_info(license_records)")}

        self.assertIn("operating_system", columns)
        self.assertIn("minimum_os_version", columns)
        self.assertIn("system_architecture", columns)
        self.assertIn("application_name", columns)


if __name__ == "__main__":
    unittest.main()
