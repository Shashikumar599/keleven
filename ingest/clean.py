#!/usr/bin/env python3
"""
Phase 0: clean the raw Hugging Face transcript (jxm/the_office_lines).

Usage:
    python ingest/clean.py

Reads:
    data/raw/hf_the_office_lines/data/*.parquet   raw HF lines (base dataset)
    data/raw/The-Office-Lines-V4.csv              Kaggle, used only to repair
                                                  corrupted characters and get titles
    ingest/speaker_map.csv                        hand-checked speaker fixes
                                                  (only rows with status=ok are applied)
Only aired scenes are kept; deleted scenes are dropped here (the raw files still have them).

Writes:
    data/processed/lines.parquet
    data/processed/episodes.parquet
    data/processed/review/*.csv                   things a human should look at
"""
import glob
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

RAW_HF = "data/raw/hf_the_office_lines/data/*.parquet"
RAW_KAGGLE = "data/raw/The-Office-Lines-V4.csv"
SPEAKER_MAP = "ingest/speaker_map.csv"
OUT = Path("data/processed")

BAD = "�"  # the '�' left behind where curly quotes, ellipses and dashes were lost
BRACKET = re.compile(r"\[[^\]]*\]")


# ---------- loading ----------

def load_hf():
    df = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(RAW_HF))])
    # the train/val/test files are a random split of lines; id restores script order
    df = df.sort_values("id").reset_index(drop=True)
    # deleted scenes are not used (see findings/decisions.md); the raw files still have them
    df = df[~df["deleted"]].drop(columns="deleted").reset_index(drop=True)
    df = df.rename(columns={"line_text": "text_raw", "speaker": "speaker_raw"})
    df["fix_flags"] = [[] for _ in range(len(df))]
    return df


def load_kaggle():
    kg = pd.read_csv(RAW_KAGGLE)
    kg.columns = [c.strip().lower() for c in kg.columns]
    # 17 lines were split at a comma into a stray extra column; glue them back
    for extra in [c for c in kg.columns if c.startswith("unnamed")]:
        has = kg[extra].notna()
        kg.loc[has, "line"] = kg.loc[has, "line"].astype(str) + "," + kg.loc[has, extra].astype(str)
    kg["line"] = kg["line"].fillna("").astype(str)
    return kg


def letters_key(s):
    return re.sub(r"[^a-z]", "", s.lower())


def flag(df, mask, name):
    for i in df.index[mask]:
        df.at[i, "fix_flags"].append(name)


# ---------- 1. corrupted characters ----------

def _pattern(hf_text):
    """Regex that matches the Kaggle version of an HF line. Stage directions are
    dropped (Kaggle removed them) and each run of '�' becomes a capture group, so
    the groups tell us what Kaggle has in those places."""
    parts = []
    for tok in re.findall(r"\[[^\]]*\]|�+|\s+|.", hf_text, flags=re.S):
        if tok.startswith("["):
            parts.append(r"\s*")
        elif tok[0] == BAD:
            parts.append(r"([^�]{0,4}?)")
        elif tok.isspace():
            parts.append(r"\s*")
        else:
            parts.append(re.escape(tok))
    return re.compile(r"\s*" + "".join(parts) + r"\s*", flags=re.S)


CONTRACTION = re.compile(r"(s|t|m|d|re|ve|ll|n)\b", re.I)          # it's, don't, rock'n'roll
DROPPED_LETTER = {"em", "cause", "cuz", "til", "sup", "bout", "round", "specially", "kay", "n"}


def _guess(text, start, end, quote_open, more_runs):
    """Fallback for a '�' run Kaggle could not resolve, from the characters around it.
    Returns (replacement, quote_open)."""
    before = text[start - 1] if start > 0 else " "
    after = text[end] if end < len(text) else " "
    if before.isalnum() and after.isalpha():
        return ("'" if CONTRACTION.match(text, end) else "..."), quote_open
    if not before.isalnum() and after.isalpha():
        word = re.match(r"[A-Za-z]+", text[end:]).group(0).lower()
        if word in DROPPED_LETTER:
            return "'", quote_open
        if more_runs and not quote_open:
            return '"', True             # opening quote, closed by a later run
        return "...", quote_open
    if quote_open and not after.isalnum():
        return '"', False                # closing quote
    return "...", quote_open             # trailing off / interrupted: gonna..., out...Hey


def _usable(fill):
    return fill is not None and fill.strip() != ""


def fix_mojibake(df, kg):
    by_key = defaultdict(list)
    for t in kg["line"]:
        by_key[letters_key(t)].append(t.strip())

    bad_rows = df.index[df["text_raw"].str.contains(BAD)]
    texts, review = df["text_raw"].copy(), []
    for i in bad_rows:
        raw = df.at[i, "text_raw"]
        runs = list(re.finditer(r"�+", raw))
        # runs inside stage directions can't be looked up (Kaggle has no directions)
        in_dir = [any(b.start() < r.start() < b.end() for b in BRACKET.finditer(raw)) for r in runs]

        fills = None
        pat = _pattern(raw)
        for cand in by_key.get(letters_key(BRACKET.sub("", raw)), []):
            m = pat.fullmatch(cand)
            if m:
                groups = iter(m.groups())
                fills = [None if d else next(groups) for d in in_dir]
                break

        out, pos, guessed, quote_open = [], 0, False, False
        for k, r in enumerate(runs):
            fill = fills[k].replace("\xa0", " ").strip() if fills and fills[k] is not None else None
            if _usable(fill):
                quote_open ^= fill.count('"') % 2 == 1
            else:
                fill, quote_open = _guess(raw, r.start(), r.end(), quote_open, k < len(runs) - 1)
                guessed = True
            out.append(raw[pos:r.start()] + fill)
            pos = r.end()
        texts[i] = "".join(out) + raw[pos:]
        df.at[i, "fix_flags"].append("mojibake_guessed" if guessed else "mojibake_kaggle")
        if guessed:
            review.append({"id": df.at[i, "id"], "season": df.at[i, "season"], "episode": df.at[i, "episode"],
                           "raw": raw, "fixed": texts[i]})
    df["text"] = texts
    return pd.DataFrame(review)


# ---------- 2. scene numbers ----------

def renumber_scenes(df):
    """Number scenes 1, 2, 3... per episode with no gaps, keeping their order.
    Gaps come from dropped deleted scenes that were numbered between aired ones (S1, S2, S3E12) and from
    numbers missing in the source (S4-S7). The original number is kept in scene_raw."""
    df["scene_raw"] = df["scene"]
    df["scene"] = df.groupby(["season", "episode"])["scene_raw"].rank(method="dense").astype(int)
    flag(df, df["scene"] != df["scene_raw"], "scene_renumbered")


# ---------- 3. speakers ----------

def clean_speakers(df):
    spk = df["speaker_raw"].str.strip()
    flag(df, spk != df["speaker_raw"], "speaker_whitespace")

    # scrape errors: dialogue ended up inside the speaker field. Left as is, listed for review.
    broken = spk.str.contains("\n")
    flag(df, broken, "speaker_broken")

    # "Pam [on phone]" -> speaker "Pam", direction moved to the start of the line
    m = spk.str.extract(r"^([^\[\n]+?)\s*(\[[^\]]*\])$")
    has_dir = m[0].notna() & ~broken
    spk = spk.where(~has_dir, m[0])
    df.loc[has_dir, "text"] = m.loc[has_dir, 1] + " " + df.loc[has_dir, "text"]
    flag(df, has_dir, "speaker_direction_moved")

    smap = pd.read_csv(SPEAKER_MAP, dtype=str).fillna("")
    ok = smap[(smap["status"] == "ok") & (smap["speaker"] != "")]
    mapping = dict(zip(ok["raw"], ok["speaker"]))
    mapped = spk.isin(mapping.keys())
    spk = spk.replace(mapping)
    flag(df, mapped, "speaker_mapped")

    df["speaker"] = spk
    return df[broken][["id", "season", "episode", "speaker_raw", "text_raw"]]


# ---------- 4. stage directions and whitespace ----------

def split_directions(df):
    t = df["text"].str.replace(r"\s+", " ", regex=True).str.strip()
    flag(df, t != df["text"], "whitespace")
    df["text"] = t

    unbalanced = t.str.count(r"\[") != t.str.count(r"\]")
    flag(df, unbalanced, "unbalanced_brackets")

    df["dialogue"] = t.str.replace(BRACKET, " ", regex=True).str.replace(r"\s+", " ", regex=True).str.strip()
    df["directions"] = t.str.findall(BRACKET).map(lambda xs: " ".join(x[1:-1].strip() for x in xs))
    return df[unbalanced][["id", "season", "episode", "speaker", "text"]]


# ---------- 5. episodes ----------

def build_episodes(df, kg):
    """Titles come from Kaggle. Kaggle numbers two-part episodes as two episodes, so
    HF and Kaggle numbering drift apart; match episodes by shared line text instead."""
    kg_key = {}
    for s, e, t in zip(kg["season"], kg["episode"], kg["line"]):
        k = letters_key(t)
        if len(k) >= 25:
            kg_key.setdefault(k, set()).add((s, e))
    kg_titles = kg.drop_duplicates(["season", "episode"]).set_index(["season", "episode"])["title"]

    rows = []
    for (s, e), g in df.groupby(["season", "episode"]):
        votes = Counter()
        for t in g["dialogue"]:
            for ke in kg_key.get(letters_key(t), ()):
                votes[ke] += 1
        total = sum(votes.values())
        matched = sorted(ke for ke, n in votes.items() if n >= max(5, 0.1 * total))
        titles = list(dict.fromkeys(kg_titles[ke] for ke in matched))
        rows.append({"season": s, "episode": e, "matched": matched,
                     "lines": len(df[(df.season == s) & (df.episode == e)]),
                     "scenes": df[(df.season == s) & (df.episode == e)]["scene"].nunique()})

    # An episode with no text match (e.g. Kaggle 6x21 lost the first 2 characters of
    # every line) gets the Kaggle episode sitting between its neighbours' matches.
    for i, r in enumerate(rows):
        if r["matched"] or i == 0 or i == len(rows) - 1:
            continue
        prev, nxt = rows[i - 1]["matched"], rows[i + 1]["matched"]
        if prev and nxt and prev[-1][0] == nxt[0][0] == r["season"] and nxt[0][1] - prev[-1][1] == 2:
            r["matched"] = [(r["season"], prev[-1][1] + 1)]
            r["title_inferred"] = True

    for r in rows:
        r["title"] = " / ".join(dict.fromkeys(kg_titles[ke] for ke in r["matched"])) or None
        r["kaggle_episodes"] = [f"{a}x{b}" for a, b in r.pop("matched")]
        r["title_inferred"] = r.get("title_inferred", False)
    return pd.DataFrame(rows)[["season", "episode", "title", "kaggle_episodes", "title_inferred",
                               "lines", "scenes"]]


# ---------- main ----------

def main():
    df, kg = load_hf(), load_kaggle()
    (OUT / "review").mkdir(parents=True, exist_ok=True)

    moj_review = fix_mojibake(df, kg)
    renumber_scenes(df)
    broken = clean_speakers(df)
    unbalanced = split_directions(df)
    episodes = build_episodes(df, kg)

    df["fix_flags"] = df["fix_flags"].map(lambda f: ",".join(f))
    cols = ["id", "season", "episode", "scene", "scene_raw", "speaker", "speaker_raw", "text", "dialogue",
            "directions", "text_raw", "fix_flags"]
    df[cols].to_parquet(OUT / "lines.parquet", index=False)
    episodes.to_parquet(OUT / "episodes.parquet", index=False)

    moj_review.to_csv(OUT / "review/mojibake_guessed.csv", index=False)
    broken.to_csv(OUT / "review/speaker_broken.csv", index=False)
    unbalanced.to_csv(OUT / "review/unbalanced_brackets.csv", index=False)
    two_part = episodes[(episodes["kaggle_episodes"].map(len) != 1) | episodes["title_inferred"]]
    two_part.to_csv(OUT / "review/episode_title_matches.csv", index=False)

    flags = Counter(f for fs in df["fix_flags"] for f in fs.split(",") if f)
    print(f"lines: {len(df)}  episodes: {len(episodes)}  speakers: {df['speaker_raw'].nunique()} -> {df['speaker'].nunique()}")
    print("fixes:")
    for k, v in flags.most_common():
        print(f"  {k:28s} {v}")
    print(f"remaining '{BAD}' in text: {df['text'].str.contains(BAD).sum()}")
    print(f"episodes without title: {episodes['title'].isna().sum()}; "
          f"matched to != 1 Kaggle episode: {len(two_part)}")
    print(f"\nwrote {OUT}/lines.parquet, {OUT}/episodes.parquet, review files in {OUT}/review/")


if __name__ == "__main__":
    main()
