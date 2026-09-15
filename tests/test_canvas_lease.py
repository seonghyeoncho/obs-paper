from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / "plugins/obspaper/scripts"
sys.path.insert(0, str(SCRIPTS))

from canvas_lease import (  # noqa: E402
    LEASE_FILE,
    LeaseError,
    acquire_lease,
    device_name,
    lease_status,
    release_lease,
)
from obs_paper_engine import PreconditionError, apply_patch, compile_request  # noqa: E402
from obs_project import configure_vault, init_project, record_repository, set_frontmatter_value  # noqa: E402
from preflight import preflight  # noqa: E402

T0 = datetime(2026, 9, 15, 9, 0, tzinfo=timezone.utc)


class LeaseTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        environ = {key: value for key, value in os.environ.items() if key not in {"OBS_PAPER_VAULT", "OBS_PAPER_DEVICE"}}
        environ["OBS_PAPER_CONFIG"] = str(self.root / "config" / "config.json")
        self.env = patch.dict("os.environ", environ, clear=True)
        self.env.start()
        self.vault = self.root / "NLP"
        self.vault.mkdir()
        project = init_project(self.vault, "Honorific")
        self.project = Path(project["root"])
        self.canvas = Path(project["canvas"])
        self.canvas.write_text(
            json.dumps({
                "nodes": [{"id": "flow", "type": "group", "x": 0, "y": 0, "width": 2000, "height": 2000, "label": "research_flow"}],
                "edges": [],
            }),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.env.stop()
        self.directory.cleanup()

    def patch_for(self, key: str = "rq1") -> dict:
        return compile_request(self.canvas, {
            "schema_version": 1,
            "workflow": "research-flow",
            "target": {"group_id": "flow"},
            "actions": [{"op": "add_research_flow", "nodes": [{"key": key, "kind": "rq", "text": "RQ", "x": 100, "y": 100}], "links": []}],
        })


class LeaseTest(LeaseTestCase):
    def test_lease_is_markdown_frontmatter_beside_the_action_log(self) -> None:
        acquire_lease(self.canvas, device="mac", now=T0, purpose="RQ2 cards")
        path = self.project / LEASE_FILE
        self.assertTrue((self.project / "CANVAS_ACTION_LOG.md").is_file())
        lines = path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], "---")
        entry = json.loads(lines[1].split(": ", 1)[1])
        self.assertEqual(entry, {
            "canvas": "Honorific.canvas",
            "device": "mac",
            "acquired_at": "2026-09-15T09:00:00Z",
            "expires_at": "2026-09-15T09:30:00Z",
            "purpose": "RQ2 cards",
        })
        self.assertEqual(lines[2], "---")

    def test_acquire_renew_and_refuse_another_device(self) -> None:
        first = acquire_lease(self.canvas, device="mac", now=T0)
        self.assertEqual((first["action"], first["state"]), ("acquired", "held-by-me"))
        renewed = acquire_lease(self.canvas, device="mac", minutes=60, now=T0 + timedelta(minutes=20))
        self.assertEqual(renewed["action"], "renewed")
        self.assertEqual(renewed["acquired_at"], "2026-09-15T09:00:00Z")
        self.assertEqual(renewed["expires_at"], "2026-09-15T10:20:00Z")
        with self.assertRaises(LeaseError) as raised:
            acquire_lease(self.canvas, device="sh_con", now=T0 + timedelta(minutes=30))
        self.assertIn("'mac'", str(raised.exception))
        self.assertIn("2026-09-15T10:20:00Z", str(raised.exception))
        other = lease_status(self.canvas, device="sh_con", now=T0 + timedelta(minutes=30))
        self.assertEqual((other["state"], other["holder"]), ("held-by-other", "mac"))

    def test_an_expired_lease_counts_as_absent(self) -> None:
        acquire_lease(self.canvas, device="mac", now=T0)
        later = T0 + timedelta(minutes=30)
        self.assertEqual(lease_status(self.canvas, device="sh_con", now=later)["state"], "expired")
        taken = acquire_lease(self.canvas, device="sh_con", now=later)
        self.assertEqual((taken["action"], taken["holder"]), ("acquired", "sh_con"))
        self.assertEqual(lease_status(self.canvas, device="mac", now=later)["state"], "held-by-other")

    def test_release_own_refuse_foreign_and_force(self) -> None:
        acquire_lease(self.canvas, device="mac", now=T0)
        with self.assertRaisesRegex(LeaseError, "--force"):
            release_lease(self.canvas, device="sh_con", now=T0)
        forced = release_lease(self.canvas, device="sh_con", force=True, now=T0)
        self.assertEqual((forced["action"], forced["state"]), ("force-released", "free"))
        self.assertIn("force-release-lease", (self.project / "CANVAS_ACTION_LOG.md").read_text(encoding="utf-8"))

        acquire_lease(self.canvas, device="mac", now=T0)
        self.assertEqual(release_lease(self.canvas, device="mac", now=T0)["action"], "released")
        self.assertEqual(release_lease(self.canvas, device="mac", now=T0)["action"], "not-held")

    def test_merged_lines_from_two_devices_block_both(self) -> None:
        stamp = {"acquired_at": "2026-09-15T09:00:00Z", "expires_at": "2026-09-15T09:30:00Z"}
        lines = [json.dumps({"canvas": "Honorific.canvas", "device": device, **stamp}) for device in ("mac", "sh_con")]
        (self.project / LEASE_FILE).write_text(
            "---\n" + "".join(f'"Honorific.canvas": {line}\n' for line in lines) + "---\n", encoding="utf-8"
        )
        for device in ("mac", "sh_con"):
            self.assertEqual(lease_status(self.canvas, device=device, now=T0)["state"], "held-by-other")

    def test_device_name_precedence(self) -> None:
        with patch("canvas_lease.socket.gethostname", return_value="host-a"):
            self.assertEqual(device_name(), ("host-a", "hostname"))
            configure_vault(self.vault, device="sh_con")
            self.assertEqual(device_name(), ("sh_con", "config"))
            configure_vault(self.vault)
            self.assertEqual(device_name(), ("sh_con", "config"))
            with patch.dict("os.environ", {"OBS_PAPER_DEVICE": "override"}):
                self.assertEqual(device_name(), ("override", "OBS_PAPER_DEVICE"))


class ApplyLeaseTest(LeaseTestCase):
    def test_apply_is_refused_under_a_foreign_lease(self) -> None:
        acquire_lease(self.canvas, device="mac", now=T0)
        before = self.canvas.read_text(encoding="utf-8")
        with self.assertRaisesRegex(PreconditionError, "leased by device 'mac'"):
            apply_patch(self.canvas, self.patch_for(), device="sh_con", now=T0)
        self.assertEqual(self.canvas.read_text(encoding="utf-8"), before)
        self.assertEqual(apply_patch(self.canvas, self.patch_for(), device="mac", now=T0)["lease"], "held-by-me")

    def test_required_lease_refuses_apply_without_one(self) -> None:
        set_frontmatter_value(self.project / "project.md", "canvas_lease", "required")
        with self.assertRaisesRegex(PreconditionError, "canvas_lease: required"):
            apply_patch(self.canvas, self.patch_for(), device="sh_con", now=T0)
        acquire_lease(self.canvas, device="sh_con", now=T0)
        result = apply_patch(self.canvas, self.patch_for(), device="sh_con", now=T0 + timedelta(minutes=5))
        self.assertEqual(result["status"], "applied")
        self.assertNotIn("warning", result)

    def test_apply_without_a_lease_is_allowed_with_a_warning_when_not_required(self) -> None:
        result = apply_patch(self.canvas, self.patch_for(), device="sh_con", now=T0)
        self.assertEqual((result["status"], result["lease"]), ("applied", "free"))
        self.assertIn("canvas_lease: required", result["warning"])


class PreflightTest(LeaseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.repo = self.root / "repo"
        (self.repo / ".git").mkdir(parents=True)
        (self.repo / "src").mkdir()
        self.fake_obsidian = str(self.root / "no-such-bin" / "obsidian")

    def run_preflight(self, now: datetime = T0) -> dict:
        return preflight(self.repo / "src", executable=self.fake_obsidian, now=now)

    def test_no_vault_points_at_headless_setup(self) -> None:
        result = self.run_preflight()
        self.assertEqual(result, self.run_preflight())
        self.assertEqual((result["can_write"], result["blocked_by"]), (False, "no-vault"))
        self.assertIsNone(result["project"])
        self.assertIsNone(result["lease"])
        steps = "\n".join(result["next_steps"])
        for expected in ("approval", "obsidian-headless", "ob login", "--device-name", "vault-config"):
            self.assertIn(expected, steps)

    def test_lease_states(self) -> None:
        configure_vault(self.vault, device="sh_con")
        self.assertEqual(self.run_preflight()["blocked_by"], "project-unmapped")
        record_repository(self.vault, "Honorific", self.repo)

        free = self.run_preflight()
        self.assertEqual(free["device"], {"name": "sh_con", "source": "config"})
        self.assertEqual((free["can_write"], free["lease"]["state"], free["lease"]["required"]), (True, "free", False))
        self.assertEqual(free["project"]["groups"], [{"id": "flow", "label": "research_flow"}])

        set_frontmatter_value(self.project / "project.md", "canvas_lease", "required")
        required = self.run_preflight()
        self.assertEqual((required["can_write"], required["blocked_by"]), (False, "lease-required"))
        self.assertIn("lease acquire", "\n".join(required["next_steps"]))

        acquire_lease(self.canvas, device="mac", now=T0, purpose="RQ2 cards")
        held = self.run_preflight()
        self.assertEqual((held["blocked_by"], held["lease"]["holder"]), ("lease-held-by-other", "mac"))
        self.assertIn("2026-09-15T09:30:00Z", held["next_steps"][0])

        expired = self.run_preflight(T0 + timedelta(hours=1))
        self.assertEqual((expired["lease"]["state"], expired["blocked_by"]), ("expired", "lease-required"))

        acquire_lease(self.canvas, device="sh_con", now=T0 + timedelta(hours=1))
        mine = self.run_preflight(T0 + timedelta(hours=1))
        self.assertEqual((mine["can_write"], mine["lease"]["state"]), (True, "held-by-me"))


if __name__ == "__main__":
    unittest.main()
