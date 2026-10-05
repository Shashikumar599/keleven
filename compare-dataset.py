#!/usr/bin/env python3
"""
Phase 0: compare the Kaggle and Hugging Face Office transcript datasets.

Usage:
    pip install pandas datasets pyarrow
    python compare_datasets.py --kaggle data/raw/The-Office-Lines-V4.csv
    # optional: --hf data/raw/hf_office_lines.parquet  (otherwise downloads jxm/the_office_lines)
    # optional: --spot 2 1   (season, episode to print side by side)

Writes a markdown report to findings/phase-0-comparison.md and prints it.
"""
import argparse
import re
from difflib import SequenceMatcher
from pathlib import Path

import pandas as pd

MAIN_CHARACTERS = [
    "Michael", "Dwight", "Jim", "Pam", "Andy", "Angela", "Kevin", "Oscar",
    "Ryan", "Kelly", "Stanley", "Phyllis", "Meredith", "Creed", "Toby",
    "Darryl", "Erin", "Jan", "Holly", "Gabe", "Nellie", "Robert",
]
MIN_WORDS_FOR_MATCH = 4  # short lines like "Yeah." match by accident, so skip them


# ---------- loading ----------

def load_kaggle(path):
    for enc in ("utf-8", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    df.columns = [c.strip().lower() for c in df.columns]
    extra_cols = [c for c in df.columns if c.startswith("unnamed")]
    df = df.rename(columns={"line": "text"})
    return df, extra_cols


def load_hf(path=None):
    if path:
        p = Path(path)
        df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    else:
        from datasets import load_dataset
        ds = load_dataset("jxm/the_office_lines")
        df = pd.concat([ds[split].to_pandas() for split in ds.keys()], ignore_index=True)
    df = df.rename(columns={"line_text": "text"})
    return df.sort_values("id") if "id" in df.columns else df


# ---------- helpers ----------

def norm_text(s):
    s = str(s).lower()
    s = re.sub(r"\[.*?\]", " ", s)          # drop stage directions
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def norm_name(s):
    return re.sub(r"[^a-z ]", "", str(s).lower()).strip()


def md_table(df):
    if df.empty:
        return "_none_\n"
    cols = list(df.columns)
    out = "| " + " | ".join(map(str, cols)) + " |\n"
    out += "|" + "---|" * len(cols) + "\n"
    for _, row in df.iterrows():
        out += "| " + " | ".join(str(row[c]) for c in cols) + " |\n"
    return out


# ---------- checks ----------

def basic_stats(name, df):
    eps = df.groupby(["season", "episode"]).size()
    return {
        "dataset": name,
        "lines": len(df),
        "seasons": df["season"].nunique(),
        "episodes": len(eps),
        "scenes (sum per episode)": int(df.groupby(["season", "episode"])["scene"].nunique().sum()),
        "distinct speakers": df["speaker"].nunique(),
        "empty lines": int(df["text"].isna().sum() + (df["text"].astype(str).str.strip() == "").sum()),
        "lines with [brackets]": int(df["text"].astype(str).str.contains(r"\[").sum()),
        "lines with non-ASCII": int(df["text"].astype(str).str.contains(r"[^\x00-\x7F]").sum()),
    }


def per_episode_comparison(kg, hf, hf_aired):
    k = kg.groupby(["season", "episode"]).size().rename("kaggle_lines")
    h = hf.groupby(["season", "episode"]).size().rename("hf_lines_all")
    ha = hf_aired.groupby(["season", "episode"]).size().rename("hf_lines_aired")
    merged = pd.concat([k, h, ha], axis=1).fillna(0).astype(int).reset_index()
    merged["diff_vs_aired_pct"] = (
        (merged["kaggle_lines"] - merged["hf_lines_aired"])
        / merged["hf_lines_aired"].replace(0, 1) * 100
    ).round(1)
    return merged


def match_rate(source_df, target_df):
    """Share of source lines (>= MIN_WORDS words) whose normalized text appears
    in the target dataset within the same season and episode."""
    target_sets = (
        target_df.assign(n=target_df["text"].map(norm_text))
        .groupby(["season", "episode"])["n"].apply(set).to_dict()
    )
    src = source_df.assign(n=source_df["text"].map(norm_text))
    src = src[src["n"].str.split().str.len() >= MIN_WORDS_FOR_MATCH]
    if src.empty:
        return None, 0
    found = src.apply(lambda r: r["n"] in target_sets.get((r["season"], r["episode"]), set()), axis=1)
    return round(found.mean() * 100, 1), len(src)


def speaker_variants(df, name):
    target = name.lower()
    counts = df["speaker"].value_counts()
    rows = []
    for spk, cnt in counts.items():
        n = norm_name(spk)
        if not n or str(spk) == name:
            continue
        if n == target or target in n.split() or SequenceMatcher(None, n, target).ratio() >= 0.8:
            rows.append(f"{spk} ({cnt})")
    return rows


def multi_speaker_labels(df):
    mask = df["speaker"].astype(str).str.contains(r"&|/|,| and ", case=False)
    return df.loc[mask, "speaker"].value_counts().head(10)


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kaggle", required=True, help="path to Kaggle CSV")
    ap.add_argument("--hf", default=None, help="optional local parquet/csv of the HF dataset")
    ap.add_argument("--spot", nargs=2, type=int, default=[2, 1], metavar=("SEASON", "EPISODE"))
    ap.add_argument("--out", default="findings/phase-0-comparison.md")
    args = ap.parse_args()

    kg, extra_cols = load_kaggle(args.kaggle)
    hf = load_hf(args.hf)
    has_deleted = "deleted" in hf.columns
    hf_aired = hf[~hf["deleted"]] if has_deleted else hf
    hf_deleted = hf[hf["deleted"]] if has_deleted else hf.iloc[0:0]

    r = ["# Phase 0: Dataset comparison (Kaggle vs Hugging Face)\n"]

    # 1. Basic stats
    r.append("## 1. Basic stats\n")
    r.append(md_table(pd.DataFrame([basic_stats("Kaggle", kg), basic_stats("HF (all)", hf),
                                    basic_stats("HF (aired only)", hf_aired)]).set_index("dataset").T.reset_index()
                      .rename(columns={"index": "metric"})))
    if has_deleted:
        r.append(f"\nHF deleted-scene lines: **{len(hf_deleted)}**\n")

    # 2. Extra Kaggle columns
    r.append("\n## 2. Unexpected Kaggle columns\n")
    if extra_cols:
        for c in extra_cols:
            non_null = kg[c].dropna()
            r.append(f"- `{c}`: {len(non_null)} non-empty values. Samples: "
                     f"{list(non_null.astype(str).head(5))}\n")
    else:
        r.append("_none_\n")

    # 3. Episode coverage
    per_ep = per_episode_comparison(kg, hf, hf_aired)
    r.append("\n## 3. Episode coverage\n")
    r.append(f"- Episodes only in Kaggle: {per_ep[per_ep['hf_lines_all'] == 0][['season','episode']].values.tolist()}\n")
    r.append(f"- Episodes only in HF: {per_ep[per_ep['kaggle_lines'] == 0][['season','episode']].values.tolist()}\n")
    big = per_ep[per_ep["diff_vs_aired_pct"].abs() > 15].sort_values("diff_vs_aired_pct")
    r.append(f"\nEpisodes where Kaggle differs from HF aired lines by more than 15% ({len(big)}):\n\n")
    r.append(md_table(big))

    # 4. Deleted scenes: does Kaggle contain them?
    r.append("\n## 4. Does Kaggle include deleted scenes?\n")
    aired_rate, aired_n = match_rate(hf_aired, kg)
    r.append(f"- HF aired lines found in Kaggle: **{aired_rate}%** (of {aired_n} lines with {MIN_WORDS_FOR_MATCH}+ words)\n")
    if has_deleted and len(hf_deleted):
        del_rate, del_n = match_rate(hf_deleted, kg)
        r.append(f"- HF deleted-scene lines found in Kaggle: **{del_rate}%** (of {del_n} lines)\n")
        r.append("- Reading: if the deleted rate is close to the aired rate, Kaggle includes deleted scenes. "
                 "If it is near zero, Kaggle is aired-only.\n")
    kg_rate, kg_n = match_rate(kg, hf)
    r.append(f"- Kaggle lines found in HF: **{kg_rate}%** (of {kg_n} lines). "
             "Low overlap means different transcription sources or different cleaning.\n")

    # 5. Speaker names
    r.append("\n## 5. Speaker name variants (main characters)\n")
    rows = []
    for name in MAIN_CHARACTERS:
        rows.append({"character": name,
                     "Kaggle variants": ", ".join(speaker_variants(kg, name)[:6]) or "-",
                     "HF variants": ", ".join(speaker_variants(hf, name)[:6]) or "-"})
    r.append(md_table(pd.DataFrame(rows)))
    r.append("\nMulti-speaker labels (top 10):\n\n")
    r.append("Kaggle: " + (", ".join(f"{k} ({v})" for k, v in multi_speaker_labels(kg).items()) or "-") + "\n\n")
    r.append("HF: " + (", ".join(f"{k} ({v})" for k, v in multi_speaker_labels(hf).items()) or "-") + "\n")

    # 6. Spot check
    s, e = args.spot
    r.append(f"\n## 6. Spot check: S{s}E{e}, first 15 lines\n")
    for label, df in (("Kaggle", kg), ("HF (aired)", hf_aired)):
        ep = df[(df["season"] == s) & (df["episode"] == e)].head(15)
        r.append(f"\n**{label}**\n\n")
        for _, row in ep.iterrows():
            r.append(f"- [scene {row['scene']}] {row['speaker']}: {str(row['text'])[:120]}\n")

    report = "".join(r)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    main()