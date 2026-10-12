"""Draws docs/architecture.svg (and, with Chrome, docs/architecture.png): the v3 system as icon tiles in zones.
    python3 docs/architecture-poster/make_poster.py
Icons: Phosphor (MIT) for generic symbols; PostgreSQL, FastAPI, Docker logos from devicon (MIT); Gemini, Anthropic, AWS marks from Simple Icons (CC0)."""
import html
import os
import re
import subprocess
import sys

here = os.path.dirname(os.path.abspath(__file__))
OUT_SVG = os.path.join(here, "..", "architecture.svg")
OUT_PNG = os.path.join(here, "..", "architecture.png")
W, H = 1800, 1185
INK, MUTED, LINE = "#1b2430", "#5f6b7c", "#7b879a"
SEC = {  # panel fill, border, icon-disc fill
    "data": ("#eaf1fd", "#9db7ec", "#d3e2fb"), "graph": ("#e8f5ec", "#8ccaa1", "#cdebd8"), "models": ("#fdf3e1", "#e6bd6e", "#fbe3b4"),
    "db": ("#edf0f5", "#a3aec0", "#dbe1ea"), "ask": ("#e2f4f1", "#7cc9bd", "#c3ebe4"), "eval": ("#f4f0e9", "#cdbf9f", "#e8dfc9"),
    "host": ("#e6f2fb", "#93bde0", "#cbe2f5"), "key": ("#f4f5f8", "#cfd5df", "#e5e8ee"),
}
els = []


def e(s):
    return html.escape(s, quote=False)


def read(name):
    return open(os.path.join(here, "icons", name + ".svg")).read()


def inner(svg):
    return re.sub(r"^<svg[^>]*>|</svg>\s*$", "", svg.strip())


def draw_icon(kind, name, cx, cy, size, fill=INK):
    x, y = cx - size / 2, cy - size / 2
    if kind == "ph":
        return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 256 256" fill="{fill}">{inner(read(name))}</svg>'
    if kind == "dev":
        return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 128 128">{inner(read(name))}</svg>'
    d = re.search(r' d="([^"]+)"', read(name)).group(1)          # simple-icons: a single path
    f = "url(#gem)" if name == "googlegemini" else fill
    return f'<svg x="{x}" y="{y}" width="{size}" height="{size}" viewBox="0 0 24 24"><path d="{d}" fill="{f}"/></svg>'


def text(x, y, s, cls, anchor="middle"):
    els.append(f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">{e(s)}</text>')


def zone(x, y, w, h, sec, title, sub=""):
    fill, stroke, _ = SEC[sec]
    els.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="{fill}" stroke="{stroke}" stroke-width="1.6"/>')
    text(x + 26, y + 36, title, "zt", "start")
    if sub:
        text(x + w - 26, y + 36, sub, "zs", "end")


PROV = {"Gemini": ("ic", "googlegemini"), "Claude": ("si", "anthropic"), "Voyage": ("ph", "vector-three")}


def pill(x, y, provider):
    """A small pill saying which external model this step calls; x is the right edge."""
    w = 30 + 7.6 * len(provider)
    px = x - w
    els.append(f'<rect x="{px}" y="{y}" width="{w}" height="24" rx="12" fill="#fff6dd" stroke="#e3b35d" stroke-width="1.2"/>')
    kind, name = PROV[provider]
    if provider == "Gemini":
        els.append(draw_icon("si", name, px + 14, y + 12, 15))
    elif provider == "Claude":
        els.append(draw_icon("si", name, px + 14, y + 12, 15, "#d97757"))
    else:
        els.append(draw_icon("ph", name, px + 14, y + 12, 15, "#8a5a00"))
    text(px + 24, y + 16.5, provider, "pv", "start")


def tile(x, y, sec, label, sub, icon, num=None, badge=None, w=128, h=150):
    _, stroke, disc = SEC[sec]
    els.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#ffffff" stroke="{stroke}" stroke-width="1.5" filter="url(#sh)"/>')
    cx = x + w / 2
    els.append(f'<circle cx="{cx}" cy="{y+58}" r="37" fill="{disc}"/>')
    kind, name = icon[0], icon[1]
    fill = icon[2] if len(icon) > 2 else INK
    els.append(draw_icon(kind, name, cx, y + 58, 46 if kind == "ph" else 44, fill))
    text(cx, y + 124, label, "tl")
    text(cx, y + 142, sub, "ts")
    if num:
        els.append(f'<circle cx="{x+17}" cy="{y+17}" r="12" fill="{stroke}"/>')
        text(x + 17, y + 22, str(num), "tn")
    if badge:
        pill(x + w - 6, y - 12, badge)


def chevron(x, y):
    els.append(f'<path d="M{x-4},{y-7} L{x+4},{y} L{x-4},{y+7}" fill="none" stroke="{LINE}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>')


def row(x0, y, sec, items, start_num=1, gap=16, w=128, chevrons=True):
    xs = []
    for i, it in enumerate(items):
        tx = x0 + i * (w + gap)
        tile(tx, y, sec, *it[:3], num=start_num + i if start_num else None, badge=it[3] if len(it) > 3 else None)
        xs.append(tx)
        if chevrons and i:
            chevron(tx - gap / 2, y + 58)
    return xs


def dashed(x1, y1, x2, y2, label=None, lx=None, ly=None):
    els.append(f'<path d="M{x1},{y1} L{x2},{y2}" stroke="{LINE}" stroke-width="2" stroke-dasharray="3 7" stroke-linecap="round" fill="none"/>')
    if label:
        text(lx if lx is not None else x1 + 10, ly if ly is not None else (y1 + y2) / 2 + 4, label, "dl", "start")


# ---------------- title
text(50, 64, "Keleven: how the v3 RAG system fits together", "title", "start")
text(50, 96, "A question-answering system over the transcripts of The Office (US): from raw text to a cited answer, measured version by version.", "sub", "start")

TH = 150
# ---------------- zone A, B, models
ZY = 126
zone(40, ZY, 608, 218, "data", "BUILD · PREPARE THE DATA", "offline, rerunnable")
row(64, ZY + 52, "data", [("Transcripts", "186 episodes", ("ph", "file-text")), ("Clean", "790 → 733 speakers", ("ph", "broom")),
                          ("Chunk", "4,658 scene chunks", ("ph", "stack")), ("Embed", "1,024-d vectors", ("ph", "vector-three"), "Voyage")])
zone(668, ZY, 608, 218, "graph", "BUILD · THE GRAPH", "the step that makes v3")
row(692, ZY + 52, "graph", [("Extract", "per-episode JSON", ("ph", "brackets-curly"), "Gemini"), ("Review", "removes over-reach", ("ph", "check-circle"), "Gemini"),
                           ("Link", "proof or no merge", ("ph", "link")), ("Build", "1,698 events", ("ph", "graph"))])
zone(1296, ZY, 464, 218, "models", "EXTERNAL MODELS", "over an API")
mx = 1320
for i, (lab, sub, ic) in enumerate([("Gemini Flash", "enhance · answer", ("si", "googlegemini")), ("Voyage", "embeddings", ("ph", "vector-three")),
                                    ("Claude 5.5", "grading council", ("si", "anthropic", "#d97757"))]):
    tile(mx + i * 144, ZY + 52, "models", lab, sub, ic)

# ---------------- database zone
DY = 392
zone(40, DY, 1720, 176, "db", "STORE · ONE DATABASE", "text, vectors, graph and question log together")
els.append(draw_icon("dev", "postgresql", 150, DY + 100, 104))
text(232, DY + 92, "PostgreSQL 17 + pgvector", "dbt", "start")
text(232, DY + 118, "24 tables · 7 views · 65 MB", "dbs", "start")
text(232, DY + 140, "read-only role for the app and every generated query", "dbs", "start")
for i, (lab, sub) in enumerate([("Transcripts", "episodes · lines"), ("Chunks + vectors", "exact cosine search"), ("Graph", "tables · views"), ("Question log", "every run, feedback")]):
    gx = 640 + i * 280
    els.append(f'<rect x="{gx}" y="{DY+58}" width="256" height="92" rx="16" fill="#ffffff" stroke="{SEC["db"][1]}" stroke-width="1.5" filter="url(#sh)"/>')
    els.append(f'<circle cx="{gx+42}" cy="{DY+104}" r="26" fill="{SEC["db"][2]}"/>')
    els.append(draw_icon("ph", "database", gx + 42, DY + 104, 32))
    text(gx + 82, DY + 98, lab, "tl", "start")
    text(gx + 82, DY + 120, sub, "ts", "start")

# writes lines
dashed(344, ZY + 218, 344, DY, "writes", 354, ZY + 218 + 28)
dashed(972, ZY + 218, 972, DY, "writes", 982, ZY + 218 + 28)

# ---------------- ask zone
AY = 620
zone(40, AY, 1720, 246, "ask", "ASK · ONE QUESTION, END TO END", "online, about 10 to 20 seconds")
ty = AY + 76
x = 66
step = 152
sequence = [("You", "browser", ("ph", "browser")), ("CloudFront", "free HTTPS", ("ph", "cloud")), ("Gate", "password · limits", ("ph", "lock-key")),
            ("Enhancer", "search · SQL · graph", ("ph", "magic-wand"), "Gemini")]
for i, it in enumerate(sequence):
    tile(x + i * step, ty, "ask", *it[:3], num=i + 1, badge=it[3] if len(it) > 3 else None)
    if i:
        chevron(x + i * step - 8, ty + 58)
# parallel group
gx0 = x + 4 * step + 8
els.append(f'<rect x="{gx0-12}" y="{ty-50}" width="{3*step-4}" height="{TH+66}" rx="18" fill="none" stroke="{SEC["ask"][1]}" stroke-width="1.6" stroke-dasharray="7 6"/>')
text(gx0 + 3 * step / 2 - 14, ty - 30, "READ THE DATABASE IN PARALLEL", "gl")
par = [("Search", "vector + keyword", ("ph", "magnifying-glass"), "Voyage"), ("SQL", "counts · phrases", ("ph", "table")), ("Graph", "relationships", ("ph", "graph"))]
chevron(x + 4 * step - 8 + 4, ty + 58)
for i, it in enumerate(par):
    tile(gx0 + i * step, ty, "ask", *it[:3], num=5 + i, badge=it[3] if len(it) > 3 else None)
x2 = gx0 + 3 * step + 22
tail = [("Scene", "attach + neighbours", ("ph", "film-slate")), ("Answer", "cited, from sources", ("ph", "chat-circle-text"), "Gemini"), ("Check", "do quotes exist?", ("ph", "quotes"))]
chevron(x2 - 17, ty + 58)
for i, it in enumerate(tail):
    tile(x2 + i * step, ty, "ask", *it[:3], num=8 + i, badge=it[3] if len(it) > 3 else None)
    if i:
        chevron(x2 + i * step - 8, ty + 58)
# reads line
dashed(gx0 + 1.5 * step - 14, DY + 176, gx0 + 1.5 * step - 14, ty - 50, "reads", gx0 + 1.5 * step - 4, DY + 176 + 30)

# ---------------- footer zones
FY = 912
zone(40, FY, 608, 218, "eval", "EVALUATE", "offline")
row(64, FY + 52, "eval", [("92 questions", "with references", ("ph", "question")), ("Batch runs", "3 answers each", ("ph", "stack-simple"), "Gemini"),
                          ("Council", "3 lenses + chair", ("ph", "users-three"), "Claude"), ("Findings", "v1 → v3 scores", ("ph", "chart-bar"))], start_num=None, chevrons=True)
zone(668, FY, 608, 218, "host", "HOST · AWS", "inside the free tier")
row(692, FY + 52, "host", [("EC2 + Docker", "t3.small, 2 containers", ("dev", "docker")), ("deploy.sh", "build · ship · restart", ("ph", "rocket-launch")),
                          ("CloudFront", "HTTPS, no domain", ("ph", "cloud")), ("Secrets", ".env on the server", ("ph", "shield-check"))], start_num=None, chevrons=False)
zone(1296, FY, 464, 218, "key", "HOW TO READ THIS")
pill(1420, FY + 62, "Gemini")
text(1436, FY + 80, "a step that calls an external model", "kt", "start")
els.append(f'<circle cx="1338" cy="{FY+112}" r="12" fill="{SEC["ask"][1]}"/>')
text(1338, FY + 117, "5", "tn")
text(1360, FY + 117, "the order of the steps in a zone", "kt", "start")
els.append(f'<path d="M1324,{FY+148} L1360,{FY+148}" stroke="{LINE}" stroke-width="2" stroke-dasharray="3 7" stroke-linecap="round"/>')
text(1370, FY + 153, "the database is written or read", "kt", "start")
text(1322, FY + 190, "v1 = vector search · v2 adds the enhancer, keyword", "kt", "start")
text(1322, FY + 208, "search and SQL · v3 adds the graph (shown here)", "kt", "start")

style = f"""<style>
text {{ font-family: -apple-system, "SF Pro Display", "Helvetica Neue", Arial, sans-serif; }}
.title {{ font-size: 40px; font-weight: 700; fill: {INK}; }} .sub {{ font-size: 17px; fill: {MUTED}; }}
.zt {{ font-size: 14px; font-weight: 700; letter-spacing: 1.4px; fill: {INK}; }} .zs {{ font-size: 13px; fill: {MUTED}; }}
.tl {{ font-size: 16px; font-weight: 650; fill: {INK}; }} .ts {{ font-size: 12px; fill: {MUTED}; }} .tn {{ font-size: 13px; font-weight: 700; fill: #fff; text-anchor: middle; }}
.pv {{ font-size: 12px; font-weight: 700; fill: #7a5200; }} .dl {{ font-size: 12px; font-style: italic; fill: {MUTED}; }} .gl {{ font-size: 11.5px; font-weight: 700; letter-spacing: 1.1px; fill: {MUTED}; }}
.dbt {{ font-size: 26px; font-weight: 700; fill: {INK}; }} .dbs {{ font-size: 14px; fill: {MUTED}; }} .kt {{ font-size: 14px; fill: {INK}; }}
</style>
<defs>
<linearGradient id="gem" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#4285f4"/><stop offset=".55" stop-color="#9b72cb"/><stop offset="1" stop-color="#d96570"/></linearGradient>
<filter id="sh" x="-10%" y="-10%" width="120%" height="125%"><feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#1b2430" flood-opacity=".10"/></filter>
</defs>"""
svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Architecture of the Keleven v3 RAG system">\n'
       f'<title>Keleven: how the v3 RAG system fits together</title>{style}\n<rect width="{W}" height="{H}" fill="#fbfbfd"/>\n' + "\n".join(els) + "\n</svg>\n")
open(OUT_SVG, "w").write(svg)
print("wrote", os.path.normpath(OUT_SVG))
chrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
if os.path.exists(chrome) and "--no-png" not in sys.argv:
    subprocess.run([chrome, "--headless", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2", f"--window-size={W},{H}",
                    f"--screenshot={os.path.normpath(OUT_PNG)}", "file://" + os.path.normpath(OUT_SVG)], capture_output=True)
    print("wrote", os.path.normpath(OUT_PNG))
