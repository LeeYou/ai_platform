import importlib
import json
import os
import sqlite3
import sys
import tempfile
import unittest
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
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.tempdir.name)
        self.db_path = self.temp_path / "license.db"
        self.licenses_dir = self.temp_path / "licenses"
        self.private_keys_dir = self.temp_path / "private_keys"
        self.logs_dir = self.temp_path / "logs"
        self.admin_token = "test-admin-token"
        self._original_env = {key: os.environ.get(key) for key in [
            "AI_LICENSE_DB",
            "LICENSES_DIR",
            "PRIVATE_KEYS_DIR",
            "LOG_DIR",
            "AI_ADMIN_TOKEN",
        ]}

    def tearDown(self):
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._unload_backend_modules()
        self.tempdir.cleanup()

    def _unload_backend_modules(self):
        for module_name in BACKEND_MODULES:
            sys.modules.pop(module_name, None)

    def _load_backend_main(self):
        os.environ["AI_LICENSE_DB"] = str(self.db_path)
        os.environ["LICENSES_DIR"] = str(self.licenses_dir)
        os.environ["PRIVATE_KEYS_DIR"] = str(self.private_keys_dir)
        os.environ["LOG_DIR"] = str(self.logs_dir)
        os.environ["AI_ADMIN_TOKEN"] = self.admin_token
        self._unload_backend_modules()
        return importlib.import_module("main")

    def _create_customer_and_key(self, client: TestClient):
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        customer_res = client.post(
            "/api/v1/customers",
            json={"customer_id": "CUST-EXT", "name": "扩展客户"},
            headers=headers,
        )
        self.assertEqual(customer_res.status_code, 201, customer_res.text)

        key_res = client.post(
            "/api/v1/keys",
            json={"name": "客户专属密钥"},
            headers=headers,
        )
        self.assertEqual(key_res.status_code, 201, key_res.text)
        return key_res.json()["id"], headers

    def test_create_license_persists_and_signs_new_fields(self):
        backend_main = self._load_backend_main()

        with TestClient(backend_main.app) as client:
            key_id, headers = self._create_customer_and_key(client)
            response = client.post(
                "/api/v1/licenses",
                json={
                    "customer_id": "CUST-EXT",
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

    def test_create_license_rejects_invalid_operating_system(self):
        backend_main = self._load_backend_main()

        with TestClient(backend_main.app) as client:
            key_id, headers = self._create_customer_and_key(client)
            response = client.post(
                "/api/v1/licenses",
                json={
                    "customer_id": "CUST-EXT",
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

    def test_run_migrations_adds_new_license_columns(self):
        conn = sqlite3.connect(self.db_path)
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

        backend_main = self._load_backend_main()
        backend_main._run_migrations(backend_main.engine)

        with sqlite3.connect(self.db_path) as migrated:
            columns = {row[1] for row in migrated.execute("PRAGMA table_info(license_records)")}

        self.assertIn("operating_system", columns)
        self.assertIn("minimum_os_version", columns)
        self.assertIn("system_architecture", columns)
        self.assertIn("application_name", columns)


if __name__ == "__main__":
    unittest.main()
