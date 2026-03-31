"""A/B Testing Framework for AI Models

Enables gradual rollout and traffic splitting between model versions.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from typing import Any


class ABTestConfig:
    """Configuration for A/B testing between model versions.

    Example config.json:
    {
      "capability": "face_detect",
      "variants": [
        {"version": "v1.0.0", "weight": 70},
        {"version": "v1.1.0", "weight": 30}
      ],
      "strategy": "random",  // or "sticky_session"
      "enabled": true
    }
    """

    def __init__(self, config_path: str) -> None:
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)

        self.capability = cfg["capability"]
        self.variants = cfg["variants"]
        self.strategy = cfg.get("strategy", "random")
        self.enabled = cfg.get("enabled", True)

        # Normalize weights to percentages
        total_weight = sum(v["weight"] for v in self.variants)
        for v in self.variants:
            v["weight_pct"] = v["weight"] / total_weight * 100.0

    def select_version(self, session_id: str | None = None) -> str:
        """Select model version based on A/B testing strategy.

        Args:
            session_id: Optional session identifier for sticky sessions

        Returns:
            Selected model version (e.g., "v1.0.0")
        """
        if not self.enabled or len(self.variants) == 0:
            return "current"  # Default fallback

        if len(self.variants) == 1:
            return self.variants[0]["version"]

        if self.strategy == "sticky_session" and session_id:
            # Use hash of session_id for deterministic selection
            hash_val = int(hashlib.md5(session_id.encode()).hexdigest(), 16)
            rand_pct = (hash_val % 10000) / 100.0  # 0-99.99
        else:
            # Random selection
            rand_pct = random.uniform(0, 100)

        cumulative = 0.0
        for variant in self.variants:
            cumulative += variant["weight_pct"]
            if rand_pct <= cumulative:
                return variant["version"]

        # Fallback to last variant
        return self.variants[-1]["version"]


class ABTestManager:
    """Manages A/B test configurations for all capabilities."""

    def __init__(self, config_dir: str = "/mnt/ai_platform/ab_tests") -> None:
        self.config_dir = config_dir
        self._configs: dict[str, ABTestConfig] = {}
        self._load_configs()

    def _load_configs(self) -> None:
        """Load all A/B test configs from directory."""
        if not os.path.exists(self.config_dir):
            return

        for filename in os.listdir(self.config_dir):
            if filename.endswith(".json"):
                capability = filename[:-5]  # Remove .json
                config_path = os.path.join(self.config_dir, filename)
                try:
                    self._configs[capability] = ABTestConfig(config_path)
                except Exception as e:
                    print(f"[ABTest] Failed to load config for {capability}: {e}")

    def reload(self) -> None:
        """Reload all A/B test configurations."""
        self._configs.clear()
        self._load_configs()

    def get_version_for_request(
        self,
        capability: str,
        session_id: str | None = None
    ) -> str:
        """Get model version to use for a request.

        Args:
            capability: Capability name (e.g., "face_detect")
            session_id: Optional session ID for sticky sessions

        Returns:
            Model version path (e.g., "v1.0.0" or "current")
        """
        config = self._configs.get(capability)
        if config is None or not config.enabled:
            return "current"

        return config.select_version(session_id)

    def get_test_info(self, capability: str) -> dict[str, Any]:
        """Get A/B test information for a capability.

        Returns:
            Dict with test configuration details or empty dict if no test
        """
        config = self._configs.get(capability)
        if config is None:
            return {}

        return {
            "enabled": config.enabled,
            "strategy": config.strategy,
            "variants": [
                {
                    "version": v["version"],
                    "weight": v["weight"],
                    "weight_pct": round(v["weight_pct"], 2)
                }
                for v in config.variants
            ]
        }

    def list_active_tests(self) -> dict[str, dict]:
        """List all active A/B tests.

        Returns:
            Dict mapping capability -> test info
        """
        return {
            cap: self.get_test_info(cap)
            for cap, cfg in self._configs.items()
            if cfg.enabled
        }


# ============================================================================
# Example A/B Test Configuration Files
# ============================================================================

# /mnt/ai_platform/ab_tests/face_detect.json
EXAMPLE_CONFIG_1 = """
{
  "capability": "face_detect",
  "variants": [
    {
      "version": "v1.0.0",
      "weight": 70,
      "description": "Stable baseline model"
    },
    {
      "version": "v1.1.0",
      "weight": 30,
      "description": "New model with improved accuracy"
    }
  ],
  "strategy": "random",
  "enabled": true,
  "created_at": "2026-03-30T10:00:00Z",
  "notes": "Gradual rollout of v1.1.0 - monitoring for 7 days before full deployment"
}
"""

# /mnt/ai_platform/ab_tests/desktop_recapture_detect.json
EXAMPLE_CONFIG_2 = """
{
  "capability": "desktop_recapture_detect",
  "variants": [
    {
      "version": "v1.0.0",
      "weight": 50
    },
    {
      "version": "v1.1.0",
      "weight": 50
    }
  ],
  "strategy": "sticky_session",
  "enabled": true,
  "created_at": "2026-03-31T08:00:00Z",
  "notes": "50/50 split with sticky sessions for consistent user experience"
}
"""

# Usage in production main.py:
#
# from ab_testing import ABTestManager
#
# ab_manager = ABTestManager()
#
# @app.post("/api/v1/infer/{capability}")
# async def infer(capability: str, request: Request, ...):
#     session_id = request.headers.get("X-Session-ID")
#
#     # Get version via A/B test
#     version = ab_manager.get_version_for_request(capability, session_id)
#     model_dir = resolve_model_dir(capability, version)
#
#     engine = _engines[capability]
#     result = engine.infer(image, options)
#     result["_ab_test_version"] = version  # Include in response for analytics
#
#     return result
#
# @app.get("/api/v1/admin/ab_tests")
# async def list_ab_tests(token: str = Depends(verify_admin_token)):
#     return ab_manager.list_active_tests()
#
# @app.post("/api/v1/admin/ab_tests/reload")
# async def reload_ab_tests(token: str = Depends(verify_admin_token)):
#     ab_manager.reload()
#     return {"status": "reloaded", "active_tests": len(ab_manager._configs)}
