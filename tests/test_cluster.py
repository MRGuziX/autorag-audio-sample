"""OpenShift errors and installed-pipeline identity checks without a live cluster."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from lib import openshift  # noqa: E402
from lib.pipelines import discover_endpoint, pin_pipeline  # noqa: E402
from lib.sample import OPTIMIZATION_PIPELINE  # noqa: E402


class ClusterTests(unittest.TestCase):
    def test_expired_login_is_actionable_without_echoing_sensitive_stderr(self):
        response = subprocess.CompletedProcess([], 1, "", "Unauthorized token=do-not-display")
        with patch("lib.openshift.subprocess.run", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "run oc login") as raised:
                openshift.oc("whoami", context="explicit-context")
            self.assertNotIn("do-not-display", str(raised.exception))

    def test_discovery_ignores_unrelated_routes(self):
        dspa = {"metadata": {"name": "dspa", "uid": "owned"}}
        route = {
            "metadata": {"name": "ds-pipeline-dspa", "ownerReferences": [{"uid": "owned"}]},
            "spec": {
                "host": "pipeline.example.test",
                "tls": {"termination": "reencrypt"},
                "to": {"name": "ds-pipeline-dspa"},
            },
        }
        unrelated = {
            "metadata": {"name": "console", "ownerReferences": [{"uid": "other"}]},
            "spec": {"host": "console.example.test"},
        }
        self.assertEqual(discover_endpoint([unrelated, route], dspa), "https://pipeline.example.test")
        with self.assertRaisesRegex(ValueError, "set RHOAI_KFP_URL"):
            discover_endpoint([unrelated], dspa)

    def test_explicit_versions_skip_latest_version_discovery(self):
        client = Mock()
        spec = {
            "pipelineInfo": {"name": OPTIMIZATION_PIPELINE},
            "deploymentSpec": {"executors": {"test": {}}},
        }
        client.get_pipeline_version.return_value.pipeline_spec = spec
        pinned, _ = pin_pipeline(
            client, "project", OPTIMIZATION_PIPELINE, "chosen-pipeline", "chosen-version"
        )
        self.assertEqual(pinned["version_id"], "chosen-version")
        client.list_pipeline_versions.assert_not_called()
        client.get_pipeline_version.assert_called_once_with(
            pipeline_id="chosen-pipeline", pipeline_version_id="chosen-version"
        )

    def test_wrapped_managed_spec_is_pinned_without_losing_platform_settings(self):
        client = Mock()
        package = {
            "pipeline_spec": {
                "pipelineInfo": {"name": OPTIMIZATION_PIPELINE},
                "deploymentSpec": {"executors": {"test": {}}},
            },
            "platform_spec": {"platforms": {"kubernetes": {"deploymentSpec": {}}}},
        }
        client.get_pipeline_version.return_value.pipeline_spec = package
        _, saved = pin_pipeline(client, "project", OPTIMIZATION_PIPELINE, "pipeline", "version")
        self.assertEqual(saved, package)
        package["pipeline_spec"]["pipelineInfo"]["name"] = "different-pipeline"
        with self.assertRaisesRegex(ValueError, "actual name: 'different-pipeline'"):
            pin_pipeline(client, "project", OPTIMIZATION_PIPELINE, "pipeline", "version")


if __name__ == "__main__":
    unittest.main()
