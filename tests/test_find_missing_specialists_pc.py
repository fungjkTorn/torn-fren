"""Read-only original champion file recovery from nested checkout and Git."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.find_missing_specialists_pc import scan


class SourceFinderTest(unittest.TestCase):
    def test_nested_filenames_and_exclusion_without_modifying_files(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            nested=home/"old"/"research"/"specialists"
            nested.mkdir(parents=True)
            camel=nested/"camel_fast_selector.py"
            camel.write_text("SECRET_DO_NOT_READ=7\n")
            other=home/"trash"/"venv"
            other.mkdir(parents=True)
            (other/"rf_localgrid.py").write_text("ignore")
            before=camel.read_bytes()
            results=scan([home],check_git=False)
            self.assertIn(str(camel),
                results["by_item"]["uae:Camel Plushie"]["exact_name_hits"])
            self.assertEqual(results["by_item"]["uni:Red Fox Plushie"]["exact_name_hits"],[])
            self.assertEqual(camel.read_bytes(),before)
            self.assertFalse(results["files_modified"])
            self.assertFalse(results["content_or_secrets_read"])

    def test_git_tree_paths_can_find_deleted_file(self):
        with tempfile.TemporaryDirectory() as td:
            home=Path(td)
            (home/".git").mkdir()
            mocked="abc123 research/old/rf_localgrid.py\nfff777 ignored/noise.py\n"
            from subprocess import CompletedProcess
            with patch("scripts.find_missing_specialists_pc.subprocess.run",
                       return_value=CompletedProcess([],0,stdout=mocked,stderr="")):
                output=scan([home],check_git=True)
            self.assertIn("research/old/rf_localgrid.py",
                output["by_item"]["uni:Red Fox Plushie"]["exact_name_hits"])
            self.assertEqual(output["git_repositories_checked"][0]["status"],"CHECKED")
            self.assertFalse(output["original_model_equivalence_certified"])

if __name__=="__main__":
    unittest.main()
