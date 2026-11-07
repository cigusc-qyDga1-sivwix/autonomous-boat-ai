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

    def test_quiet_site_deploy_and_fast_canonical_data_poll(self):
        publisher = (WORKFLOWS / PUBLISHER).read_text()
        # Bot data writers every ~3-5 min cannot each publish hundreds of MB.
        # Pages is a 15-min fallback and a push-triggered static release.
        self.assertIn("  schedule:", publisher)
        self.assertIn("    - cron: '0,15,30,45 21-23 * * *'", publisher)
        self.assertIn("    - cron: '0,15,30,45 0-14 * * *'", publisher)
        self.assertIn("  workflow_dispatch:", publisher)
        self.assertNotIn("  workflow_run:", publisher)
        self.assertIn("    if: github.ref == 'refs/heads/main'", publisher)
        self.assertIn("build_pages_site.py --app app", publisher)
        # Current formal data is fetched directly from immutable main via a
        # small forecast-sync marker; historical ledgers stay on GitHub.
        app = (ROOT / "app" / "app.js").read_text()
        feed = (ROOT / "app" / "canonical-exhibition-feed.js").read_text()
        self.assertIn("setInterval(pollCanonicalForecast,60000)", app)
        self.assertIn("forecast-sync-latest.json", feed)
        self.assertIn("raw.githubusercontent.com", feed)

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
