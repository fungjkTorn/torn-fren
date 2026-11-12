import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from services import admin_health as health
class VersionedReleaseMetadata(unittest.TestCase):
 def test_immutable_metadata_used_without_git(self):
  with tempfile.TemporaryDirectory() as td,patch.object(health,'ROOT',Path(td)),patch.object(health.subprocess,'check_output',side_effect=OSError):
   (Path(td)/'DEPLOYED_RELEASE.json').write_text(json.dumps({'source_commit':'a'*40,'github_main_merge_commit':'b'*40}))
   self.assertEqual(health._git_commit(),'b'*12);self.assertEqual(health._git_branch(),'main (versioned release)')
 def test_invalid_metadata_is_not_reported(self):
  with tempfile.TemporaryDirectory() as td,patch.object(health,'ROOT',Path(td)),patch.object(health.subprocess,'check_output',side_effect=OSError):
   (Path(td)/'DEPLOYED_RELEASE.json').write_text('{"source_commit":"unexpected"}')
   self.assertIsNone(health._git_commit());self.assertIsNone(health._git_branch())
 def test_real_git_identity_retained(self):
  with patch.object(health.subprocess,'check_output',return_value='actual-git-value\n'):
   self.assertEqual(health._git_commit(),'actual-git-value');self.assertEqual(health._git_branch(),'actual-git-value')
