import unittest
from pathlib import Path

from deploy.scripts.prepare_shared_experimental_page import prepare_html

ROOT=Path(__file__).resolve().parents[1]


class SiteShellV171Tests(unittest.TestCase):
    def test_v2_has_shared_navigation(self):
        html=(ROOT/'web/static/index.html').read_text(encoding='utf-8')
        self.assertIn('/site_shell.css',html)
        self.assertIn('data-tf-section="overview"',html)
        self.assertIn('data-tf-section="detail"',html)
        self.assertIn('data-tf-section="travel"',html)
        self.assertIn('Browse all items',html)
        self.assertIn('Plan a trip',html)

    def test_travel_has_shared_navigation(self):
        html=(ROOT/'web/travel_decisions.html').read_text(encoding='utf-8')
        self.assertIn('/site_shell.css',html)
        self.assertIn('Overview',html)
        self.assertIn('Item detail',html)
        self.assertIn('Travel decisions',html)
        self.assertIn('Plan the earliest supported trip.',html)

    def test_verified_experimental_patch_adds_shared_navigation(self):
        src=(ROOT/'tests/fixtures/experimental_owner_20261012.html').read_bytes()
        html=prepare_html(src)
        self.assertIn('/site_shell.css',html)
        self.assertIn('Foreign stock opportunities',html)
        self.assertIn('Overview',html)
        self.assertIn('Travel decisions',html)
        self.assertIn('<th>Leave</th>',html)
        self.assertIn('<th>Land</th>',html)


if __name__=='__main__':
    unittest.main()
