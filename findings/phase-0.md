# Phase 0: Data

## What was built
- `compare-dataset.py`: compares the Kaggle and Hugging Face transcripts (report in `phase-0-comparison.md`).
- `ingest/clean.py`: cleans the raw HF data into `data/processed/lines.parquet` and `episodes.parquet`.
- `ingest/speaker_map.csv`: hand-checked speaker name fixes (`ok` rows applied, `review` rows pending).

## Setup
- Python 3.12 venv (`.venv`, created with uv). pandas, datasets, pyarrow, kagglehub.
- Raw data in `data/raw/` (not committed): HF `jxm/the_office_lines` parquet files as downloaded, Kaggle `The-Office-Lines-V4.csv`.

## Results

### Dataset choice: Hugging Face `jxm/the_office_lines`
Kaggle and HF are the **same fan transcript** (scraped from officequotes.net). After stripping stage directions from HF,
92.8% of Kaggle lines are byte-identical to an HF line and about 98% match after normalizing punctuation.
The differences are in processing:

| | Kaggle | HF |
|---|---|---|
| Stage directions | stripped | kept (~10k lines) |
| Deleted scenes | not included | 1,936 lines, flagged |
| Two-part episodes | split into two episode numbers | one episode (standard numbering) |
| Episode titles | yes | no |
| Scene numbers | run through the season | restart per episode |
| Encoding | mostly repaired | 2,583 lines with `���` mojibake |
| Artifacts | trailing colons in 171 speakers, 17 lines split into a 7th column, 6 empty lines | clean columns |

HF was chosen because stage directions and deleted scenes can't be recovered from Kaggle, while HF's two gaps
(encoding, titles) can be filled from Kaggle. `schrute` was not evaluated yet; it may be useful later for
air date, writer, director and IMDb rating.

### Cleaning (from `ingest/clean.py`)
| Fix | Lines |
|---|---|
| Mojibake repaired from Kaggle's version of the same line | 2,235 |
| Mojibake guessed from context (no Kaggle match: deleted scenes, stage directions, edited lines) | 348 |
| Speaker names mapped (typos, full names) | 307 |
| `[on phone]`-style directions moved from speaker into text | 14 |
| Whitespace collapsed | 4,562 |
| Unbalanced brackets (flagged, not fixed) | 20 |
| Broken speaker fields with dialogue inside (flagged, not fixed) | 3 |

Distinct speakers: 797 → 740. Remaining `�` characters: 0. All 186 episodes have a title.

_Update 2026-10-03:_ cleaning now drops deleted scenes and renumbers scenes 1..N per episode (see decisions.md).
Current run: 57,973 lines, speakers 790 → 733, 1,183 lines renumbered; the other counts above are unchanged
except whitespace (4,481).

Decisions: multi-speaker labels (`Michael and Dwight`, 131 lines) are kept as one label, with no speaker-list
column. Repeated identical lines in a scene (363) are left unchanged. Each line keeps `text_raw` and a
`fix_flags` column so any answer can be traced back to what cleaning changed.

## Where it worked
- Matching lines between datasets by their letters only (ignoring punctuation and case) was robust enough to repair mojibake
  and map episode numbering without any manual table.

## Where it failed
1. Per-episode comparison was misleading at first: matching by (season, episode) gave a 50% overlap, because
   Kaggle numbers two-part episodes as two. Matching lines across the whole dataset gave 98%.
2. Kaggle's "Happy Hour" (6x21) has the first two characters cut off every line (`ichael grunts...`,
   `w many is that?`), so it matched nothing; its title had to be inferred from neighbouring episodes.
3. Mojibake can't be decoded: the original bytes are lost, so `’`, `…` and `—` are indistinguishable without
   a second source. 348 lines rely on context rules (contraction → `'`, paired → `"`, otherwise `...`).
4. Speaker names need human judgement: `Molly` vs Holly, `Joan` vs Jan, `David` vs David Wallace, `Bert` (unknown).
   22 mappings are still marked `review`.

## What surprised us
- The two "different" datasets are one transcript; the choice is about processing, not content.
- About 7% of Kaggle lines were edited relative to HF (typo fixes, rewording), and 421 longer Kaggle lines are not
  in HF at all.

## Decision: what the next phase should address
- Phase 1 builds on `data/processed/lines.parquet`. Scenes (season, episode, scene) are the natural chunk unit:
  scene numbers restart per episode and never go backwards; in some episodes deleted scenes come after aired ones, but in 24 episodes they are numbered between aired scenes, so the aired-only data has 73 gaps in scene numbers (corrected 2026-10-03, see decisions.md).
- Open items that can be done during Phase 1: review the `review` rows in `speaker_map.csv`, the 3 broken speaker
  fields and the 20 unbalanced-bracket lines, then re-run `clean.py`.
