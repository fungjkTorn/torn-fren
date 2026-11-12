"""Explicit release-pinned reader bound; Japan retains its original bound."""
import sys,hashlib
from pathlib import Path
from research import v128_full24_earliest_shadow as reader
if hashlib.sha256(Path(reader.__file__).read_bytes()).hexdigest()!='__READER_SHA__':
 raise ValueError('CANDIDATE_READER_CHECKSUM_MISMATCH')
if '--private-japan' not in sys.argv:reader.MAX_ITEM_ROWS=200000
from services.final_pair_live import main
if __name__=='__main__':main()
