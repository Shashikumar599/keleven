"""Draws interview/project-on-a-page.svg and .png: the whole project on one page (question, v1 to v3, results, judging, stack, decisions, limits, demos).
    python3 docs/architecture-poster/make_summary.py
Numbers come from findings/phase-3.md, findings/v1-v2-grading-analysis.md and the graded verdicts."""
import html
import os
import re
import subprocess
import sys
import textwrap

here = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(here, "..", "..", "interview")
OUT_SVG, OUT_PNG = os.path.join(OUT_DIR, "project-on-a-page.svg"), os.path.join(OUT_DIR, "project-on-a-page.png")
W, H = 1800, 1930
INK, MUTED, LINE = "#1b2430", "#5f6b7c", "#7b879a"
SEC = {"why": ("#fdf3e1", "#e6bd6e", "#fbe3b4"), "v1": ("#eaf1fd", "#9db7ec", "#d3e2fb"), "v2": ("#e8f5ec", "#8ccaa1", "#cdebd8"),
       "v3": ("#e2f4f1", "#7cc9bd", "#c3ebe4"), "res": ("#f4f0e9", "#cdbf9f", "#e8dfc9"), "judge": ("#edf0f5", "#a3aec0", "#dbe1ea"),
       "stack": ("#e6f2fb", "#93bde0", "#cbe2f5"), "dec": ("#f1ecfa", "#b7a6dc", "#ddd3f2"), "lim": ("#fdeeee", "#e2a3a3", "#f7d0d0"),
       "demo": ("#eef6e7", "#a9cf8a", "#d7ebc3")}
els = []


def e(s):
    return html.escape(s, quote=False)


def read(name):
    return open(os.path.join(here, "icons", name + ".svg")).read()


def inner(svg):
    return re.sub(r"^<svg[^>]*>|</svg>\s*$", "", svg.strip())


def icon(kind, name, cx, cy, size, fill=INK):
    x, y = cx - size / 2, cy - size / 2
    if kind == "ph":
        return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 256 256" fill="{fill}">{inner(read(name))}</svg>'
    if kind == "dev":
        return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 128 128">{inner(read(name))}</svg>'
    d = re.search(r' d="([^"]+)"', read(name)).group(1)
    f = "url(#gem)" if name == "googlegemini" else fill
    return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 24 24"><path d="{d}" fill="{f}"/></svg>'


def text(x, y, s, cls, anchor="start"):
    els.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{e(s)}</text>')


def para(x, y, s, cls, width_px, size, lh=None, bullet=False):
    """Wrapped text; returns the y after the last line."""
    lh = lh or size * 1.38
    chars = max(8, int(width_px / (size * 0.50)))
    first = True
    for ln in textwrap.wrap(s, width=chars - (2 if bullet else 0)):
        if bullet and first:
            els.append(f'<circle cx="{x+3}" cy="{y-size*0.32}" r="2.6" fill="{LINE}"/>')
        text(x + (12 if bullet else 0), y, ln, cls)
        y += lh
        first = False
    return y


def panel(x, y, w, h, sec, title, sub=""):
    fill, stroke, _ = SEC[sec]
    els.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    text(x + 26, y + 36, title, "zt")
    if sub:
        text(x + w - 26, y + 36, sub, "zs", "end")


def disc(cx, cy, r, sec, ic):
    els.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{SEC[sec][2]}" stroke="{SEC[sec][1]}" stroke-width="1.4"/>')
    els.append(icon(ic[0], ic[1], cx, cy, r * 1.15, ic[2] if len(ic) > 2 else INK))


def label_block(x, y, w, tag, color, body, size=14.5):
    """A small coloured tag (WHAT IT ADDED, WHAT FAILED, ...) and wrapped text; returns next y."""
    els.append(f'<rect x="{x}" y="{y-14}" width="{22+8.0*len(tag)}" height="21" rx="10.5" fill="{color}" opacity=".9"/>')
    text(x + 11, y + 1, tag, "tg")
    return para(x, y + 26, body, "bd", w, size)


# ---------------- title
text(50, 64, "Keleven in one page: a measured study of RAG", "title")
text(50, 96, "Question answering over the transcripts of The Office (US): three versions, each added only after the last one's failures were measured.", "sub")

# ---------------- journey cards
CY, CH, CW, GAP = 128, 420, 410, 26
cards = [
    ("why", ("ph", "lightbulb"), "The question", "why this project exists", None,
     [("THE AIM", "#e6bd6e", "Learn RAG by measuring every step, not by assembling a demo: where does a model's memory fail, and what does each retrieval method add?"),
      ("THE DATA", "#e6bd6e", "A TV show stands in for private documents: the model half-remembers it, and 186 episodes (57,973 lines) are big enough to need real search.")]),
    ("v1", ("ph", "magnifying-glass"), "v1 · Vector search", "8 chunks closest in meaning", "7.62",
     [("WHAT IT ADDED", "#9db7ec", "Scenes packed into 4,658 chunks, Voyage embeddings, exact cosine search, answers with scene citations."),
      ("WHAT FAILED", "#e2a3a3", "Counts guessed from 8 chunks (2.3 out of 10), such as 'six or seven' where the real count was in the twenties. Rare phrases diluted inside long chunks.")]),
    ("v2", ("ph", "magic-wand"), "v2 · Enhancer, hybrid, SQL", "rewrite · keyword + vector · count", "8.65",
     [("WHAT IT ADDED", "#8ccaa1", "One call rewrites the question; keyword search merged with vector search; model-written read-only SQL for counts."),
      ("RESULT", "#8ccaa1", "Counts 2.3 to 9.7. Right scene in the top 8 for 53 of 55 known questions (v1: 44)."),
      ("STILL FAILED", "#e2a3a3", "Whole-show and relationship questions.")]),
    ("v3", ("ph", "graph"), "v3 · Graph and scenes", "facts from every episode", "8.88",
     [("WHAT IT ADDED", "#7cc9bd", "Graph of characters, events and relationships from all 186 episodes; links only when proven; scenes attached to matched lines."),
      ("RESULT", "#7cc9bd", "Graph-shaped questions 5.6 to 7.6, no harm elsewhere."),
      ("FOUND AFTER", "#e2a3a3", "'Conversation before I quit' failed, so scene attach was added.")]),
]
for i, (sec, ic, title, sub, score, blocks) in enumerate(cards):
    x = 40 + i * (CW + GAP)
    fill, stroke, _ = SEC[sec]
    els.append(f'<rect x="{x}" y="{CY}" width="{CW}" height="{CH}" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    disc(x + 52, CY + 58, 32, sec, ic)
    text(x + 100, CY + 54, title, "ct")
    text(x + 100, CY + 76, sub, "zs")
    if score:
        els.append(f'<rect x="{x+26}" y="{CY+CH-72}" width="{CW-52}" height="50" rx="14" fill="#ffffff" stroke="{stroke}" stroke-width="1.4"/>')
        text(x + 46, CY + CH - 39, score, "sc")
        text(x + 128, CY + CH - 39, "out of 10 · original 80 questions", "zs")
    yy = CY + 122
    for tag, color, body in blocks:
        yy = label_block(x + 26, yy, CW - 52, tag, color, body) + 10
    if i:
        els.append(f'<path d="M{x-GAP/2-4},{CY+58-8} L{x-GAP/2+4},{CY+58} L{x-GAP/2-4},{CY+58+8}" fill="none" stroke="{LINE}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
text(900, CY + CH + 24, "Scores are for transcript-only answers. The model's own memory scores about 7 out of 10 on the same questions.", "zs", "middle")

# ---------------- results, judging, stack
BY, BH = 596, 490
panel(40, BY, 560, BH, "res", "RESULTS", "0 to 10")


def bars(x, y, w, title, rows):
    text(x, y, title, "bt")
    yy = y + 20
    for lab, val, color in rows:
        text(x, yy + 15, lab, "bl")
        bx, bw = x + 150, w - 150 - 54
        els.append(f'<rect x="{bx}" y="{yy}" width="{bw}" height="20" rx="10" fill="#ffffff" stroke="#d8d3c6"/>')
        els.append(f'<rect x="{bx}" y="{yy}" width="{bw*val/10:.1f}" height="20" rx="10" fill="{color}"/>')
        text(bx + bw + 10, yy + 15, f"{val:.2f}", "bv")
        yy += 30
    return yy


yy = bars(66, BY + 70, 510, "Three versions, original 80 questions", [("v1 vector", 7.62, "#9db7ec"), ("v2 + hybrid + SQL", 8.65, "#8ccaa1"), ("v3 + graph", 8.88, "#7cc9bd")])
yy = bars(66, yy + 22, 510, "All 92 questions: model alone vs the system", [("LLM alone", 6.73, "#d8a8a8"), ("v3 transcripts only", 8.71, "#7cc9bd"), ("v3 LLM + RAG", 9.04, "#3fae9d")])
yy += 24
yy = para(66, yy, "The full system was clearly better than the model alone on 44 of 92 questions, about equal on 47, clearly worse on 1.", "bd", 500, 14.5)
para(66, yy + 4, "Biggest wins: exact details (Creed's cupcakes 0 to 10) and counts (+4.5 on average).", "bd", 500, 14.5)

panel(620, BY, 580, BH, "judge", "HOW IT WAS JUDGED")
items = [("question", "92 questions", "Quotes to multi-hop, each with a transcript-only reference answer reviewed by the owner."),
         ("stack-simple", "Three answers each", "Memory only, transcripts only, transcripts plus labelled memory; the memory answer is a control."),
         ("users-three", "A council of graders", "Fact, faithfulness and reader lenses plus a chair (Claude); a fact error weighs most."),
         ("eye-slash", "Blind, one session", "Both versions shuffled together, because separate sessions drifted by up to 4 points on identical text."),
         ("scales", "Noise measured", "Same memory text scored differently on 37 of 80 questions; under 0.5 on a mean counts as nothing.")]
yy = BY + 62
for ic, title, body in items:
    disc(660, yy + 18, 22, "judge", ("ph", ic))
    text(698, yy + 14, title, "bt")
    yy = para(698, yy + 34, body, "bd", 470, 13.5, lh=17.5) + 14

panel(1220, BY, 540, BH, "stack", "WHAT IT RUNS ON")
stack = [(("dev", "postgresql"), "PostgreSQL 17 + pgvector", "text, vectors, graph and question log in one 65 MB database"),
         (("si", "googlegemini"), "Gemini Flash", "enhancer, answers, graph extraction (free tier)"),
         (("ph", "vector-three"), "Voyage embeddings", "1,024-dimension vectors via a free allowance"),
         (("si", "anthropic", "#d97757"), "Claude Sonnet 5.5", "the grading council (a different model family)"),
         (("dev", "fastapi"), "FastAPI + plain JavaScript", "one small server, no framework front end"),
         (("dev", "docker"), "AWS: EC2, Docker, CloudFront", "free tier, HTTPS with no domain")]
yy = BY + 62
for ic, title, body in stack:
    els.append(f'<circle cx="1262" cy="{yy+18}" r="22" fill="#ffffff" stroke="{SEC["stack"][1]}" stroke-width="1.4"/>')
    els.append(icon(ic[0], ic[1], 1262, yy + 18, 28, ic[2] if len(ic) > 2 else INK))
    text(1298, yy + 14, title, "bt")
    yy = para(1298, yy + 34, body, "bd", 440, 13.5, lh=17.5) + 14

# ---------------- decisions and limits
DY2, DH = 1116, 470
panel(40, DY2, 1090, DH, "dec", "KEY DECISIONS, AND WHY")
decs = [("stack", "Scenes are the chunks", "Talking-head lines make no sense without their scene; up to 300 tokens and 3 scenes, never across an episode."),
        ("funnel", "Hybrid search", "Vector and keyword search failed on different questions: 44 and 46 of 55 alone, 49 together."),
        ("database", "Exact search, no index", "At 4,658 vectors a scan takes milliseconds with perfect recall; an index would only add risk."),
        ("link", "Never merge a guess", "Characters are linked only when the data proves it; weak links stay 'possible', because a wrong merge corrupts every answer."),
        ("lock-key", "Read-only, always", "Model-written SQL runs through a read-only role: one SELECT, 50 rows, 5 seconds."),
        ("target", "Measure before building", "SQL and the graph were added only after specific questions failed without them."),
        ("scales", "Honest grading", "A memory control, independent references, and one blind session for both versions."),
        ("coins", "Free-tier choices, stated plainly", "Gemini and Voyage free allowances and AWS free tier made it affordable; not benchmarked against alternatives.")]
colw = 520
for i, (ic, title, body) in enumerate(decs):
    cx0 = 66 + (i % 2) * (colw + 14)
    cy0 = DY2 + 62 + (i // 2) * 98
    disc(cx0 + 22, cy0 + 20, 22, "dec", ("ph", ic))
    text(cx0 + 58, cy0 + 16, title, "bt")
    para(cx0 + 58, cy0 + 36, body, "bd", colw - 70, 13.2, lh=17)

panel(1150, DY2, 610, DH, "lim", "HONEST LIMITS")
lims = ["One run, one grader family; single-answer scores are noisy by 1 to 2 points.",
        "The 80 original questions were used to find v2's problems; the 12 added later are the cleaner test, and they suit the graph, so 5.6 to 7.6 is a best case.",
        "The graph is incomplete: 31 of 186 episodes have no relation rows.",
        "The transcripts are fan-made and incomplete; counts mean 'in this data'. 'That's what she said' is 37 here, 40 to 43 elsewhere.",
        "No re-ranker, no chunk-size sweep, no embedding-model comparison.",
        "The model alone is a small model; a bigger one would narrow the gap.",
        "Scores describe the earlier v3; scene attach was added afterwards."]
yy = DY2 + 62
for s in lims:
    yy = para(1176, yy, s, "bd", 560, 15, lh=20.5, bullet=True) + 12

# ---------------- demos
GY = 1616
panel(40, GY, 1720, 270, "demo", "THREE QUESTIONS THAT SHOW IT", "scene and detail are measured; the history is what the graph holds")
demos = [("film-slate", "The scene", "Give me the conversation before Michael says I quit.",
          "Finds S5E18 scene 34 and quotes the four lines before 'I quit', each cited; all 4 quotes verified, nothing from memory."),
         ("graph", "The history", "What is the history between Dwight and Angela?",
          "The graph holds their dating, married and engaged periods, each with the transcript lines behind it. Graph-shaped questions went 5.6 to 7.6; rehearse this one before showing it."),
         ("question", "The detail the model gets wrong", "How much does Creed say one of Packer's cupcakes costs?",
          "The model alone scores 0 out of 10 (wrong); the system scores 10, quoting the line. On exact details the average gain was +4.1.")]
for i, (ic, tag, q, a) in enumerate(demos):
    x = 66 + i * 566
    els.append(f'<rect x="{x}" y="{GY+58}" width="540" height="186" rx="16" fill="#ffffff" stroke="{SEC["demo"][1]}" stroke-width="1.4"/>')
    disc(x + 40, GY + 100, 24, "demo", ("ph", ic))
    text(x + 78, GY + 106, tag, "bt")
    yy = para(x + 24, GY + 146, "“" + q + "”", "qt", 492, 16, lh=21)
    para(x + 24, yy + 8, a, "bd", 492, 13.5, lh=18)

style = f"""<style>
text {{ font-family: -apple-system, "SF Pro Display", "Helvetica Neue", Arial, sans-serif; }}
.title {{ font-size: 40px; font-weight: 700; fill: {INK}; }} .sub {{ font-size: 17px; fill: {MUTED}; }}
.zt {{ font-size: 14px; font-weight: 700; letter-spacing: 1.4px; fill: {INK}; }} .zs {{ font-size: 13px; fill: {MUTED}; }}
.ct {{ font-size: 21px; font-weight: 700; fill: {INK}; }} .sc {{ font-size: 26px; font-weight: 700; fill: {INK}; }}
.tg {{ font-size: 11.5px; font-weight: 700; letter-spacing: .8px; fill: #1b2430; }}
.bd {{ font-size: 14.5px; fill: {INK}; }} .bt {{ font-size: 16px; font-weight: 650; fill: {INK}; }} .bl {{ font-size: 13.5px; fill: {INK}; }} .bv {{ font-size: 14px; font-weight: 700; fill: {INK}; }}
.qt {{ font-size: 16px; font-weight: 600; font-style: italic; fill: {INK}; }}
</style>
<defs><linearGradient id="gem" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#4285f4"/><stop offset=".55" stop-color="#9b72cb"/><stop offset="1" stop-color="#d96570"/></linearGradient></defs>"""
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Keleven on one page">\n'
       f'<title>Keleven in one page</title>{style}\n<rect width="{W}" height="{H}" fill="#fbfbfd"/>\n' + "\n".join(els) + "\n</svg>\n")
open(OUT_SVG, "w").write(svg)
print("wrote", os.path.normpath(OUT_SVG))
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if os.path.exists(chrome) and "--no-png" not in sys.argv:
    subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2", f"--window-size={W},{H}",
                    f"--screenshot={os.path.normpath(OUT_PNG)}", "file://" + os.path.normpath(OUT_SVG)], capture_output=True)
    print("wrote", os.path.normpath(OUT_PNG))
