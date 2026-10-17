"""V147 fails closed without exact source and preserves original V2 bytes."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research import v147_deployed_24_view_preview_patch as m


def source():
    return '''<!doctype html>
<th>Item</th><th>Model</th><th>State</th><th>Departure (your time)</th><th>Arrival (your time)</th><th>Valid until</th>
<script>
if(!snap||!snap.actionable||!ch.scales.x)return;
</script>
<script>
const fields=["item_key","model_config","status","departure","arrival","valid_until"];
const tbody=document.getElementById("rows"), state=document.getElementById("state");
function paint(rows){
 tbody.replaceChildren();
 if(!Array.isArray(rows)||rows.length===0){state.textContent="No snapshots.";return;}
 for(const item of rows){
  const tr=document.createElement("tr");
  for(const field of fields){
   const td=document.createElement("td");
   let v=item[field];
   if(["departure","arrival","valid_until"].includes(field))v=when(v);
   if(field==="status"){v=item.actionable?"Ready · experimental":v;td.className=item.actionable?"good":"warn";}
   td.textContent=v==null?"—":String(v);
   tr.appendChild(td);
  }
  tbody.appendChild(tr);
 }
 state.textContent="Last refreshed: "+new Date().toLocaleTimeString()+". "+rows.filter(x=>x.actionable).length+" actionable experimental proposals out of "+rows.length+" snapshot rows.";
}
async function refresh(){
 if(!response.ok){state.textContent=response.status===404?"Experimental preview is not enabled.":"Snapshot endpoint unavailable (HTTP "+response.status+").";return;}
}
refresh();setInterval(refresh,30000);
</script>'''


class SourcePinnedPreviewTests(unittest.TestCase):
    def test_passive_graph_and_expiry_guard_in_preview_source(self):
        html=m.build_candidate(source())
        self.assertIn("Leave in · provisional",html)
        self.assertIn("model_family",html)
        self.assertIn("DEPARTURE PASSED · RECHECK",html)
        self.assertIn("WATCH · RECONFIRM BEFORE DEPARTURE",html)
        self.assertIn("setInterval(tickBetaRows,1000)",html)
        self.assertIn("snap.valid_until<=Date.now()/1000",html)
        self.assertNotIn("Ready · experimental",html)
        self.assertNotIn("actionable experimental proposals",html)

    def test_duplicate_sentinel_and_unknown_source_fail_closed(self):
        with self.assertRaises(ValueError):
            m.build_candidate(source().replace(m.OLD_FIELDS,
                         m.OLD_FIELDS+m.OLD_FIELDS))
        with self.assertRaises(ValueError):
            m.build_candidate(source().replace(m.OLD_HEADER,
                                              "other columns"))

    def test_exact_three_deployed_fingerprints_and_never_in_place(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"original";dst=Path(temp)/"preview"
            src.mkdir()
            files={
                "app.py":b"original FastAPI application",
                "index.html":b"original full Prediction V2 graph",
                "experimental.html":source().encode("utf8"),
            }
            for name,blob in files.items():
                (src/name).write_bytes(blob)
            expected={k:hashlib.sha256(v).hexdigest()
                      for k,v in files.items()}
            with patch.object(m,"EXPECTED",expected):
                result=m.stage(src,dst)
                self.assertTrue(result["original_graph_source_byte_identical"])
                self.assertTrue(result["deployed_server_source_byte_identical"])
                self.assertFalse(result["live_site_modified"])
                self.assertEqual((src/"experimental.html").read_bytes(),
                                 files["experimental.html"])
                self.assertNotEqual((dst/"experimental.html").read_bytes(),
                                    files["experimental.html"])
                with self.assertRaises(ValueError):
                    m.stage(src,dst)

    def test_unmatched_hash_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            src=Path(temp)/"source";dst=Path(temp)/"preview"
            src.mkdir()
            for name in m.EXPECTED:
                (src/name).write_text("not current deployed source")
            with self.assertRaises(ValueError):
                m.stage(src,dst)
            with self.assertRaises(ValueError):
                m.stage(src,src)


if __name__=="__main__":
    unittest.main()
