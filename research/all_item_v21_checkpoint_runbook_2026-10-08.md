# All-item V21 checkpoint tournament — local runbook (2026-10-08)

## What this does
This is **research only**, not a website/Discord change. It takes the original 236-key V19 catalog, independently verified V19 corrected labels, the already completed 10-item V21 challenger, and the *same frozen database* and processes the rest under V21's corrected quantity-at-arrival scorer.

Initial catalog phases calculated against the frozen DB (30 items at landing/within +10s):
- 37 **strong V19 incumbents** stay untouched initially (V19 >=90%, excluding previously seeded V21 and specialist).
- 10 **completed seeded V21 tests** are reused.
- 28 **historically quantity-limited** items never reached 30 units; this is not a predictor accuracy failure. Test alternate requested quantity in a separate matched benchmark later.
- 1 **Japan Xanax specialist** is kept outside the generic competition.
- **160 new V21 test attempts**: 28 genuinely weak V19 (<60%), 49 moderate V19 (60%–<90%), 83 previously insufficient (candidate sparse fallback).

Results may not all finish overnight. The job is restartable: one durable atomic JSON checkpoint after every new result; --resume skips **all already attempted** items, including insufficient/no-history/error unless --retry-failures is specified. It does not touch the user's ongoing V20 files.

## Starting from PowerShell on the user's Windows machine
Open a NEW terminal while the existing V20 terminal continues (do not interrupt V20). Run:

```powershell
cd C:\Users\fungb\Desktop\torn-fren
.\venv\Scripts\Activate.ps1
git pull --ff-only
python -m py_compile services\all_item_v21_checkpoint.py
python -m unittest discover -s tests -p "test_all_item_v21_checkpoint.py" -v
```

**Short smoke test** (a completely separate new checkpoint file; does not touch previous V21):
```powershell
python -u -m services.all_item_v21_checkpoint run `
  --db "data\torn-fren-stock-history-fresh.db" `
  --v19 "data\all_item_v19\master.json" `
  --audit "data\remaining_item_v21\truth_audit.json" `
  --seed-v21 "data\remaining_item_v21\corrected_master.json" `
  --output "data\all_item_v21\full_master.json" `
  --workers 2 --max-new 2 --resume
```
If tests and the two-item smoke run pass, **continue the same output** without max-new:
```powershell
python -u -m services.all_item_v21_checkpoint run `
  --db "data\torn-fren-stock-history-fresh.db" `
  --v19 "data\all_item_v19\master.json" `
  --audit "data\remaining_item_v21\truth_audit.json" `
  --seed-v21 "data\remaining_item_v21\corrected_master.json" `
  --output "data\all_item_v21\full_master.json" `
  --workers 2 --resume
```

If another process is already writing the same **V21 full_master.json**, do NOT launch a second run on that path; wait/inspect instead. For progress, open an additional terminal:
```powershell
python -u -m services.all_item_v21_checkpoint report `
  --db "data\torn-fren-stock-history-fresh.db" `
  --v19 "data\all_item_v19\master.json" `
  --audit "data\remaining_item_v21\truth_audit.json" `
  --seed-v21 "data\remaining_item_v21\corrected_master.json" `
  --output "data\all_item_v21\full_master.json" --resume
```
The report action rewrites the checkpoint and should **not be run while the main tournament is writing**. Prefer reading the file directly while the runner works:
```powershell
python -c "import json,collections; x=json.load(open(r'data\all_item_v21\full_master.json')); print(x['summary'])"
```

## What the benchmark actually means
- Core target: >=30 units at actual recorded arrival or within the next 10s, with gap-invalid decisions excluded.
- V19 and new V21 candidates are compared on shared chronological decision **start times** where possible; requires >=30 matched starts to support an initial change.
- V21 is selected when it gains at least three successful decisions and >=2 percentage points in paired performance, or tied successful arrivals with materially earlier departures.
- **Natural waiting for next viable restock never reduces arrival-success score.** There is no global naive penalty per waited hour. The leave-time median is used only to break equal-success ties.
- A separate immediate departure baseline (no future knowledge) helps classify sparse availability; this does not magically predict next restock.
- Old/V21 holdouts and the paired comparative set **have been used to choose provisional candidates**. A subsequent period or shadow-replay is required to report honest new champion performance.
- Store V19 incumbent and V21 challenger separately, and compare V20 only after its output is delivered; don't assume V20 training selection is corrected, because it used old labels.
- Existing V2 website's *next drop/window/confidence* forecasting remains separate. V21 arrival-only accuracy does not establish forecast accuracy.
- No production model is activated. A future **opt-in/shadow deployment**, maintaining V2 fallback and logging forecast-vs-actual, can be considered only after merged outcomes, smoke tests, data-quality checks and a supported unified two-layer response. Do not silently replace current production logic.

## Files
- Runner: `services/all_item_v21_checkpoint.py`
- Test module: `tests/test_all_item_v21_checkpoint.py`
- Durable research output: `data/all_item_v21/full_master.json`
- Independent V19 truth audit: `data/remaining_item_v21/truth_audit.json`
- Frozen DB checksum: `9f39d40e4f255d310ea0a4e20a68d179af2ec145f7b43a02faf10a03d1359761`.


## Overnight eight-worker run (2026-10-08)

Additional capacity confirmed: user's ongoing V20 has four workers; for the independent V21 sweep, set **eight** if CPU and memory headroom permit. Eight plus four is **12 competing processes**; reduce V21 to four/six by restarting with the same --resume if the PC begins paging or slowing substantially.

V21 candidate scoring now sets the generic per-hour delay penalty to **zero** during the research run. This preserves natural waits for slow restocks; it does **not** change V19/V20 production behavior. It does not alter the 12-hour computational search horizon; forecast opportunities beyond it need their own out-of-horizon status and are not grounds for calling the item a poor predictor.

Preflight on the user's exact frozen DB:
- 236 total keys
- 37 already strong corrected V19 incumbents (retain)
- 10 completed seeded V21 runs (reuse)
- 28 historically below requested 30 units (quantity-infeasible at this threshold)
- 1 specialized Japan Xanax
- 160 remaining attempts in the original broad runner: 112 have >=6 cycles and qualify for substantive V21 modeling, while the other 48 have <6 completed cycles and typically return insufficient quickly before sparse fallback.

### Commands
```powershell
cd C:\Users\fungb\Desktop\torn-fren
.\venv\Scripts\Activate.ps1
git pull --ff-only
python -m py_compile services\all_item_v21_checkpoint.py
python -m unittest discover -s tests -p "test_all_item_v21_checkpoint.py" -v
```

One-time two-item smoke test on separate research files (safe to resume):
```powershell
python -u -m services.all_item_v21_checkpoint run `
  --db "data\torn-fren-stock-history-fresh.db" `
  --v19 "data\all_item_v19\master.json" `
  --audit "data\remaining_item_v21\truth_audit.json" `
  --seed-v21 "data\remaining_item_v21\corrected_master.json" `
  --output "data\all_item_v21\full_master.json" `
  --workers 2 --max-new 2 --resume
```

Then restart with eight workers:
```powershell
python -u -m services.all_item_v21_checkpoint run `
  --db "data\torn-fren-stock-history-fresh.db" `
  --v19 "data\all_item_v19\master.json" `
  --audit "data\remaining_item_v21\truth_audit.json" `
  --seed-v21 "data\remaining_item_v21\corrected_master.json" `
  --output "data\all_item_v21\full_master.json" `
  --workers 8 --resume
```

Important: Old 10-item V21 seed uses its original config penalties, so this tournament uses a distinct selection policy for *newly processed* items. Assess head-to-head on matched starts and retain previous champions as separate candidates.

**No assistant-side continuous overnight process is running.** The assistant can inspect the frozen DB and do research preflight, but its four-core environment is not suitable for uninterrupted broad sweep compared with the user's PC.
