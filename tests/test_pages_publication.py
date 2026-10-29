"""Prevent older, independent Pages artifacts from replacing newer results."""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLISHER = "boat-lab-pages.yml"
WRITERS = (
    "boat-lab-auto.yml",
    "official-results-fast.yml",
    "boat-lab-result-reconcile.yml",
)


class PagesPublicationTests(unittest.TestCase):
    def test_only_one_workflow_builds_and_deploys_pages(self):
        for action in ("upload-pages-artifact", "deploy-pages"):
            owners = [
                path.name for path in WORKFLOWS.glob("*.yml")
                if re.search(r"uses:\s*actions/" + action + r"@", path.read_text())
            ]
            self.assertEqual(owners, [PUBLISHER],
                             "Independent artifacts can publish stale result ledgers")

    def test_result_writers_wake_publisher_without_a_bot_push_event(self):
        publisher = (WORKFLOWS / PUBLISHER).read_text()
        self.assertIn("  workflow_run:", publisher)
        self.assertIn("    types: [completed]", publisher)
        for filename in WRITERS:
            writer = (WORKFLOWS / filename).read_text()
            name = re.search(r"^name:\s*(.+)$", writer, re.MULTILINE).group(1)
            self.assertIn("      - " + name + "\n", publisher)
        # workflow_run has write permissions: never publish a failed/fork branch.
        for guard in (
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.head_repository.full_name == github.repository",
        ):
            self.assertIn(guard, publisher)

    def test_queued_publisher_checks_out_latest_main_without_cancelling_deploy(self):
        publisher = (WORKFLOWS / PUBLISHER).read_text()
        self.assertIn("  group: boat-lab-pages\n", publisher)
        self.assertIn("  cancel-in-progress: false\n", publisher)
        checkout = publisher.index("uses: actions/checkout@")
        upload = publisher.index("uses: actions/upload-pages-artifact@")
        self.assertIn("          ref: main\n", publisher[checkout:upload])
        self.assertNotIn("github.event.workflow_run.head_sha", publisher[checkout:upload])


if __name__ == "__main__":
    unittest.main()
