/* Keleven: ask view (user / dev modes), history view, admin mode, quote of the minute, theme music. */

const EXAMPLES = [
  "Which awards did Kelly, Stanley and Phyllis get at the Dundies?",
  "Why did Andy break up with Angela?",
  "What fake diseases do employees write down in Health Care?",
  "Why does Michael hate Toby?",
];
const SYSTEMS = {
  hybrid: { title: "LLM + RAG", desc: "Transcripts first, memory fills gaps (labelled)" },
  rag:    { title: "RAG",       desc: "Transcripts only, every claim cited" },
  llm:    { title: "LLM",       desc: "The model's memory only, no transcripts" },
};
const VERDICTS = ["correct", "partial", "wrong", "refused"];
const LOADING_LINES = [
  "Searching 186 episodes",
  "Dwight is fact-checking",
  "Checking with corporate",
  "Michael wants to add a joke. Denied.",
  "Comparing notes with the transcripts",
];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const store = { get(k) { try { return localStorage.getItem(k); } catch { return null; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch {} } };
const session = { get(k) { try { return sessionStorage.getItem(k); } catch { return null; } },
                  set(k, v) { try { v == null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch {} } };
const reduceMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

const state = {
  view: location.hash === "#history" ? "history" : "ask",
  mode: store.get("office-rag-mode") === "dev" ? "dev" : "user",
  data: null,
  order: ["rag", "llm"],        // RAG and LLM swap sides at random per question (unbiased voting)
  feedback: { satisfied: null, preferred: null },
  status: { satisfied: "", preferred: "" },
  showSources: false,
  sentScenes: new Set(),
  version: store.get("office-rag-version"),   // dev mode: pipeline version to ask with (null = server default)
  systems: (store.get("office-rag-systems") || "rag,llm").split(",").filter((x) => ["rag", "llm", "hybrid"].includes(x)),   // dev mode: which answers to compute
  compare: null,                // dev mode: stored answers for this question { answers, picked: [keys] }
};

/* A rendering context: which scenes were sent (for chip colours) and a prefix that keeps scene ids unique when
   several questions are on screen (history). */
const MAIN = { prefix: "cur", get sent() { return state.sentScenes; } };
/* graph rows (v3) come with the transcript lines they were extracted from; those scenes were sent to the model too */
const graphLines = (plan) => (plan?.graph_result?.lines || []).flat();
const sentSet = (passages, plan) => {
  const set = new Set();
  for (const p of passages) for (let s = p.scene_start; s <= p.scene_end; s++) set.add(`${p.season}-${p.episode}-${s}`);
  for (const l of graphLines(plan)) set.add(`${l.season}-${l.episode}-${l.scene}`);
  return set;
};

/* ---------- theme: dark by default ---------- */
function setTheme(theme) {
  if (theme === "light") document.documentElement.dataset.theme = "light";
  else delete document.documentElement.dataset.theme;
  store.set("office-rag-theme", theme);
  const next = theme === "light" ? "dark" : "light";
  $("theme-toggle").innerHTML = `<i class="ph ${theme === "light" ? "ph-moon" : "ph-sun"}"></i>`;
  $("theme-toggle").title = $("theme-toggle").ariaLabel = `Switch to ${next} mode`;
}
$("theme-toggle").addEventListener("click", () => setTheme(store.get("office-rag-theme") === "light" ? "dark" : "light"));
setTheme(store.get("office-rag-theme") === "light" ? "light" : "dark");

/* ---------- admin mode: password checked by the server; kept for this browser tab only ---------- */
let adminKey = session.get("keleven-admin");
const adminHeaders = () => (adminKey ? { "X-Admin-Password": adminKey } : {});
function renderAdmin(message = "", open = false) {
  const btn = $("admin-btn"), box = $("admin-box");
  btn.setAttribute("aria-pressed", String(!!adminKey));
  btn.innerHTML = `<i class="ph ${adminKey ? "ph-lock-open" : "ph-lock"}"></i> ${adminKey ? "Admin on" : "Admin"}`;
  if (!open) { box.hidden = true; return; }
  box.hidden = false;
  box.innerHTML = adminKey
    ? `<i class="ph ph-lock-open"></i> Admin mode is on: retrieval settings unlocked, reviews and feedback visible in History.
       <button type="button" class="pill" id="admin-off">Leave admin mode</button>`
    : `<i class="ph ph-lock"></i> Admin password
       <input type="password" id="admin-pass" aria-label="Admin password" autocomplete="off">
       <button type="button" class="pill" id="admin-on">Unlock</button><span class="msg">${esc(message)}</span>`;
  $("admin-pass")?.focus();
}
async function tryAdmin() {
  const password = $("admin-pass")?.value || "";
  try {
    const res = await fetch("/api/admin/check", { method: "POST", headers: { "Content-Type": "application/json" },
                                                    body: JSON.stringify({ password }) });
    if (!res.ok) return renderAdmin((await res.json()).detail || "Wrong password.", true);
    adminKey = password; session.set("keleven-admin", password);
    adminChanged();
  } catch { renderAdmin("Couldn't reach the server.", true); }
}
/* public deployment: visitors get both views but not History (other people's questions); retrieval settings and History need the admin password */
function applyPublic() {
  const locked = !!INFO?.public_mode && !adminKey;
  $("history-btn").hidden = locked;
  $("public-note").hidden = !INFO?.public_mode || !!adminKey;
  if (locked && state.view === "history") setView("ask");
}
function adminChanged() {
  applyPublic();
  renderAdmin();
  renderLock();
  renderExplain();
  if (state.view === "history") resetHistory();
}
$("admin-btn").addEventListener("click", () => renderAdmin("", $("admin-box").hidden));
$("admin-box").addEventListener("click", (e) => {
  if (e.target.closest("#admin-on")) tryAdmin();
  if (e.target.closest("#admin-off")) { adminKey = null; session.set("keleven-admin", null); adminChanged(); }
});
$("admin-box").addEventListener("keydown", (e) => { if (e.target.id === "admin-pass" && e.key === "Enter") tryAdmin(); });

/* ---------- retrieval settings (dev mode): only admins can change them; the server enforces it ---------- */
function renderLock() {
  $("k").disabled = $("expand").disabled = !adminKey;
  if (!adminKey) { $("k").value = 8; $("expand").value = 1; }
  $("lock-area").innerHTML = adminKey ? `<i class="ph ph-lock-open"></i> Unlocked (admin)`
                                      : `<i class="ph ph-lock"></i> Locked. Admins can change these.`;
}

/* ---------- views and modes ---------- */
function setView(view) {
  state.view = view;
  $("view-ask").hidden = view !== "ask";
  $("ask").hidden = view !== "ask";
  document.querySelector(".tabs").hidden = view !== "ask";
  $("view-history").hidden = view !== "history";
  $("history-btn").setAttribute("aria-pressed", String(view === "history"));
  $("history-btn").innerHTML = view === "history" ? `<i class="ph ph-arrow-left"></i> Back to asking`
                                                  : `<i class="ph ph-clock-counter-clockwise"></i> History`;
  if (view === "history" && !hist.started) resetHistory();
  if ((location.hash === "#history") !== (view === "history")) window.history.replaceState(null, "", view === "history" ? "#history" : location.pathname);
}
$("history-btn").addEventListener("click", () => setView(state.view === "history" ? "ask" : "history"));

function setMode(mode) {
  state.mode = mode;
  store.set("office-rag-mode", mode);
  for (const t of document.querySelectorAll(".tab")) t.setAttribute("aria-selected", String(t.dataset.mode === mode));
  $("settings").hidden = mode !== "dev";
  renderExplain();
  if (state.data) render();
}
for (const t of document.querySelectorAll(".tab")) t.addEventListener("click", () => setMode(t.dataset.mode));

/* dev-mode explainer: what this is, which model and why (filled from /api/info) */
let INFO = null;
fetch("/api/info").then((r) => r.json()).then((d) => { INFO = d; renderExplain(); renderVersions(); applyPublic(); }).catch(() => {});

/* dev mode: pick the pipeline version (v1 vector, v2 hybrid, v3 graph) to compare them on the same question */
function renderSystems() {
  const el = $("systems");
  el.innerHTML = Object.entries(SYSTEMS).map(([k, v]) => `<label title="${esc(v.desc)}"><input type="checkbox" data-sys="${k}"
    ${state.systems.includes(k) ? "checked" : ""}> ${esc(v.title)}</label>`).join("");
}
$("systems").addEventListener("change", () => {
  state.systems = [...document.querySelectorAll("#systems input:checked")].map((i) => i.dataset.sys);
  store.set("office-rag-systems", state.systems.join(","));
});
function renderVersions() {
  const versions = INFO?.versions || [];
  if (!versions.some((v) => v.version === state.version && v.ready)) state.version = INFO?.version || null;
  $("versions").innerHTML = versions.map((v) => `<button type="button" class="pill" data-version="${v.version}"
      aria-pressed="${v.version === state.version}" ${v.ready ? "" : "disabled"} title="${esc(v.description)}">
      ${v.version} · ${esc(v.label)}${v.ready ? "" : " (soon)"}</button>`).join("");
}
$("versions").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-version]");
  if (!b || b.disabled) return;
  state.version = b.dataset.version;
  store.set("office-rag-version", state.version);
  renderVersions();
});
function renderExplain() {
  const el = $("explain");
  el.hidden = state.mode !== "dev";
  if (el.hidden) return;
  const model = INFO?.llm || "Gemini Flash";
  el.innerHTML = `<strong>How this works.</strong> This is RAG (retrieval-augmented generation) over the full
    transcripts: your question is matched against the show's transcripts, both by meaning and by exact words, and
    the best-matching scenes are handed to
    <strong>${esc(model)}</strong> with the question. It's a small, fast model that knows a fair amount about the show,
    but less than larger models, so comparing the answers shows what the transcripts add. Each question gets three
    answers: both sources, transcripts only, and memory only.${adminKey ? "" : " Retrieval settings are locked (defaults used)."}`;
}

/* ---------- examples ---------- */
for (const ex of EXAMPLES) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "chip-btn"; b.textContent = ex;
  b.onclick = () => { $("q").value = ex; $("ask").requestSubmit(); };
  $("examples").append(b);
}

/* ---------- quote of the minute (326 offline quotes, MIT, office-quotes-cli; avatars from the-office-api) ---------- */
let QUOTES = [], AVATARS = {}, currentQuote = null, quoteTimer = null;
const recent = [];
function pickQuote() {
  if (!QUOTES.length) return null;
  let q;
  for (let tries = 0; tries < 20; tries++) {
    q = QUOTES[Math.floor(Math.random() * QUOTES.length)];
    if (!recent.includes(q)) break;
  }
  recent.push(q); if (recent.length > 30) recent.shift();
  return q;
}
function quoteHTML() {
  const q = currentQuote;
  if (!q) return "";
  const initials = q.character.split(" ").map((w) => w[0]).join("").slice(0, 2);
  const face = AVATARS[q.character]
    ? `<img class="avatar" src="${esc(AVATARS[q.character])}" alt="${esc(q.character)}">`
    : `<span class="avatar" aria-hidden="true">${esc(initials)}</span>`;
  return `<figure class="quote" id="quote">${face}<div><blockquote>“${esc(q.content)}”</blockquote>
    <figcaption>${esc(q.character)}</figcaption></div></figure>`;
}
function showNextQuote() {
  currentQuote = pickQuote();
  const el = $("quote");
  if (el) el.outerHTML = quoteHTML();
}
// every 30 s: the longest quote (45 words) reads in about 16 s
function startQuoteTimer() { stopQuoteTimer(); quoteTimer = setInterval(showNextQuote, 30000); }
function stopQuoteTimer() { clearInterval(quoteTimer); quoteTimer = null; }
document.addEventListener("visibilitychange", () => (document.hidden ? stopQuoteTimer() : startQuoteTimer()));
Promise.all([fetch("/static/quotes/quotes.json").then((r) => r.json()), fetch("/static/quotes/avatars.json").then((r) => r.json())])
  .then(([quotes, avatars]) => {
    QUOTES = quotes.filter((q) => q.content.length <= 220);
    AVATARS = avatars;
    currentQuote = pickQuote();
    const slot = $("quote-slot"); if (slot) slot.outerHTML = quoteHTML();
    startQuoteTimer();
  })
  .catch(() => {});      // no quotes: the page works without them

/* ---------- empty / loading ---------- */
function renderEmpty() {
  $("result").innerHTML = `<div class="sheet empty"><h2>Ask Dunder Mifflin's archive anything.</h2>
    <p>Every answer comes from the episode transcripts, with chips that jump to the exact scene.</p>
    ${quoteHTML() || '<span id="quote-slot"></span>'}</div>`;
  $("sources-wrap").innerHTML = "";
}
let loadingTimer = null;
function renderLoading() {
  $("sources-wrap").innerHTML = "";
  $("result").innerHTML = `<div class="sheet loading" aria-busy="true">
    <div class="status" id="loading-status">${LOADING_LINES[0]}</div>
    <div class="line" style="width:92%"></div><div class="line" style="width:78%"></div><div class="line" style="width:85%"></div>
    <div class="line" style="width:40%"></div>${quoteHTML()}</div>`;
  let i = 0;
  loadingTimer = setInterval(() => {
    i = (i + 1) % LOADING_LINES.length;
    const el = $("loading-status"); if (el) el.textContent = LOADING_LINES[i];
  }, 1800);
}

/* ---------- ask ---------- */
$("ask").addEventListener("submit", async (e) => {
  e.preventDefault();
  const question = $("q").value.trim();
  if (!question) return;
  $("go").disabled = true;
  renderLoading();
  try {
    const res = await fetch("/api/ask", {
      method: "POST", headers: { "Content-Type": "application/json", ...adminHeaders() },
      body: JSON.stringify({ question, k: +$("k").value, expand: +$("expand").value, mode: state.mode,
                             systems: state.mode === "dev" ? (state.systems.length ? state.systems : ["rag", "llm"]) : ["hybrid"],   // user mode: v3 LLM + RAG only
                             ...(state.mode === "dev" && state.version ? { version: state.version } : {}) }),
    });
    if (res.status === 401) { location.reload(); return; }       // the site password cookie expired: the login page comes back
    if (res.status === 429) throw new Error((await res.json()).detail);
    if (!res.ok) throw new Error(`The server answered ${res.status}. ${await res.text()}`);
    state.data = await res.json();
    state.order = Math.random() < 0.5 ? ["rag", "llm"] : ["llm", "rag"];
    state.feedback = { satisfied: null, preferred: null };
    state.status = { satisfied: "", preferred: "" };
    state.showSources = false;
    state.sentScenes = sentSet(state.data.retrieval.passages, state.data.retrieval.plan);
    hist.started = false;             // the history now has a newer question
    state.compare = null;
    render();
    loadCompare(question);
  } catch (err) {
    $("result").innerHTML = `<div class="sheet error"><i class="ph ph-warning-circle"></i> Something went wrong. ${esc(err.message)}</div>`;
  } finally {
    clearInterval(loadingTimer);
    $("go").disabled = false;
  }
});

/* ---------- answer text ---------- */
function formatAnswer(text, ctx = MAIN) {
  const blocks = []; let list = null;
  const flush = () => { if (list) { blocks.push(`<ul>${list.map((l) => `<li>${cites(l, ctx)}</li>`).join("")}</ul>`); list = null; } };
  for (const raw of String(text || "").split("\n")) {
    const line = raw.trim();
    if (/^([-*•]|\d+\.)\s+/.test(line)) { (list ||= []).push(line.replace(/^([-*•]|\d+\.)\s+/, "")); continue; }
    flush();
    if (line) blocks.push(`<p>${cites(line, ctx)}</p>`);
  }
  flush();
  return blocks.join("");
}
function cites(text, ctx) {
  return esc(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/\[S(\d+)E(\d+) ((?:sc\.\d+(?:,\s*)?)+)\]/g, (_, s, e, scenes) =>
      [...scenes.matchAll(/\d+/g)].map(([sc]) => sceneChip(s, e, sc, ctx)).join(""))
    .replace(/\[memory\]/g, `<span class="cite memory" title="From the model's own memory, not the transcripts">memory</span>`);
}
function sceneChip(s, e, sc, ctx = MAIN) {
  const key = `${s}-${e}-${sc}`, sent = ctx.sent.has(key);
  return `<a class="cite${sent ? "" : " missing"}" href="#" data-target="scene-${ctx.prefix}-${key}" data-ctx="${ctx.prefix}"
            title="${sent ? "Show this scene" : "This scene was not among the sources sent to the model"}">S${s}E${e} sc ${sc}</a>`;
}

/* ---------- render: ask view ---------- */
function render() {
  if (state.mode === "user") renderUser(); else renderDev();
  renderCompare();
  renderSources();
}

/* ---------- dev mode: compare stored answers to the same question (memory, v1, v2, ...); pick any three ---------- */
const MAX_PICKS = 3;
async function loadCompare(question) {
  try {
    const res = await fetch(`/api/compare?question=${encodeURIComponent(question)}`);
    if (!res.ok) return;
    const { answers } = await res.json();
    if (state.data?.question !== question) return;            // a newer question was asked meanwhile
    const keys = answers.map((a) => a.key), current = state.data.retrieval.version;
    const preferred = ["llm", "v1:rag", `${current}:rag`, `${current}:hybrid`, "v1:hybrid"];
    const picked = [...new Set(preferred.filter((k) => keys.includes(k)).concat(keys))].slice(0, MAX_PICKS);
    state.compare = { answers, picked };
    renderCompare();
  } catch {}
}
function renderCompare() {
  const c = state.compare, el = $("compare");
  // only worth showing in dev mode, when there is something beyond the run just shown
  if (state.mode !== "dev" || !c || !c.answers.some((a) => a.run_id !== state.data.run_id)) { el.innerHTML = ""; return; }
  const picks = c.answers.map((a) => `<button type="button" class="pill" data-cmp="${a.key}"
      aria-pressed="${c.picked.includes(a.key)}">${esc(a.label)}</button>`).join("");
  const cards = c.picked.map((k) => c.answers.find((a) => a.key === k)).filter(Boolean).map((a) => {
    const ctx = a.run_id === state.data.run_id ? MAIN : { prefix: `cmp${a.run_id}`, sent: new Set(a.sent_scenes) };
    const when = new Date(a.asked_at).toLocaleDateString(undefined, { day: "numeric", month: "short" });
    const from = a.run_id === state.data.run_id ? "this run" : `run ${a.run_id}, ${a.source}, ${when}`;
    return renderCard(a.system, a.answer, ctx, `<div class="meta"><span>${esc(from)}</span></div>`, a.label);
  }).join("");
  el.innerHTML = `<section class="sheet compare">
    <h2>Compare stored answers</h2>
    <div class="sub-line">Every answer this exact question has received, latest of each kind. Pick up to ${MAX_PICKS}.</div>
    <div class="picks" role="group" aria-label="Answers to compare">${picks}</div>
    <div class="cards">${cards}</div>
  </section>`;
}
$("compare").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-cmp]");
  if (!b || !state.compare) return;
  const k = b.dataset.cmp, picked = state.compare.picked;
  if (picked.includes(k)) state.compare.picked = picked.filter((x) => x !== k);
  else state.compare.picked = [...picked, k].slice(-MAX_PICKS);     // a 4th pick drops the oldest
  renderCompare();
});

function feedbackStatus(kind) {
  const s = state.status[kind];
  if (!s) return "";
  return s === "saved" ? `<span class="saved"><i class="ph ph-check"></i> Saved</span>`
                       : `<span class="saved fail">Couldn't save. Try again.</span>`;
}

function renderUser() {
  const d = state.data, a = d.answers.hybrid;
  const today = new Date().toLocaleDateString(undefined, { day: "numeric", month: "long", year: "numeric" });
  const body = a?.error ? `<p class="no">The model couldn't answer this time. ${esc(a.error)}</p>`
                        : formatAnswer(a?.data?.answer ?? a?.raw);
  const canVote = d.run_id != null && !a?.error;
  const yes = state.feedback.satisfied === true, no = state.feedback.satisfied === false;
  $("result").innerHTML = `<article class="sheet memo">
    <div class="memo-head">
      <b>TO</b><span>You</span>
      <b>FROM</b><span>The Office transcripts, 9 seasons</span>
      <b>DATE</b><span>${esc(today)}</span>
      <b>RE</b><span class="re">${esc(d.question)}</span>
    </div>
    <div class="answer">${body}</div>
    <div class="row-actions">
      ${canVote ? `<span class="label">Satisfactory?</span>
        <button class="pill" data-fb="satisfied" data-val="true" aria-pressed="${yes}"><i class="ph ph-thumbs-up"></i> Yes</button>
        <button class="pill" data-fb="satisfied" data-val="false" aria-pressed="${no}"><i class="ph ph-thumbs-down"></i> No</button>
        ${feedbackStatus("satisfied")}` : ""}
      <button class="pill ghost push" id="toggle-sources" aria-expanded="${state.showSources}">
        <i class="ph ph-files"></i> ${state.showSources ? "Hide sources" : "Show sources"}</button>
    </div>
  </article>`;
}

$("info-btn").addEventListener("click", () => $("info").showModal());

function renderDev() {
  const got = state.data.answers, order = [...state.order.filter((s) => got[s]), ...(got.hybrid ? ["hybrid"] : [])];
  $("result").innerHTML = `<div class="cards">${order.map((sys) => renderCard(sys, got[sys], MAIN, voteHTML(sys))).join("")}</div>`;
}
function voteHTML(system) {
  if (system === "hybrid" || !(state.data.answers.rag && state.data.answers.llm) || state.data.run_id == null) return "";
  const voted = state.feedback.preferred === system;
  return `<div class="vote">
      <button class="pill" data-fb="preference" data-val="${system}" aria-pressed="${voted}">
        <i class="ph ${voted ? "ph-check-circle" : "ph-star"}"></i> This one is better</button>
      ${voted ? feedbackStatus("preferred") : ""}</div>`;
}

function renderCard(system, res, ctx, footer = "", title = null) {
  const s = SYSTEMS[system];
  if (!res) return "";
  if (res.error) return `<article class="sheet card"><div class="card-head"><h3>${s.title}</h3></div>
    <p class="no">The model couldn't answer. ${esc(res.error)}</p>${footer}</article>`;
  const d = res.data || {}, llm = res.llm || {}, u = llm.usage || {};
  let badge = "";
  if ("answerable" in d) badge = d.answerable ? `<span class="badge good">answerable</span>` : `<span class="badge bad">not in sources</span>`;
  if ("knows_answer" in d) badge = d.knows_answer ? `<span class="badge warn">claims to know</span>` : `<span class="badge bad">doesn't know</span>`;
  if ("memory_claims" in d) badge = d.memory_claims.length ? `<span class="badge warn">${d.memory_claims.length} from memory</span>`
                                                           : `<span class="badge good">transcripts only</span>`;
  const bad = new Set((res.check?.bad_evidence || []).map((b) => `${b.season}-${b.episode}-${b.scene}|${b.quote}`));
  const evidence = (d.evidence || []).map((ev) => {
    const ok = !bad.has(`${ev.season}-${ev.episode}-${ev.scene}|${ev.quote}`);
    return `<li><i class="ph ${ok ? "ph-check-circle ok" : "ph-x-circle no"}" title="${ok ? "Quote found in the sources" : "Quote or scene not found in the sources"}"></i>
            <span>${sceneChip(ev.season, ev.episode, ev.scene, ctx)} ${esc(ev.quote)}</span></li>`;
  }).join("");
  const section = (title, items, icon, cls) => items?.length
    ? `<details class="sub" open><summary>${title} (${items.length})</summary><ul class="list">${items.map((i) =>
        `<li><i class="ph ${icon} ${cls}"></i><span>${esc(i)}</span></li>`).join("")}</ul></details>` : "";
  const check = res.check ? `<span>quotes verified ${res.check.evidence - res.check.bad_evidence.length} of ${res.check.evidence}</span>` : "";
  const retries = llm.attempts > 1 ? `<span>${llm.attempts} attempts, server busy</span>` : "";
  return `<article class="sheet card">
    <div class="card-head"><h3>${esc(title || s.title)}</h3>${badge}</div>
    <div class="desc">${s.desc}</div>
    <div class="answer">${formatAnswer(d.answer ?? res.raw, ctx)}</div>
    ${evidence ? `<details class="sub" open><summary>Evidence (${d.evidence.length})</summary><ul class="list">${evidence}</ul></details>` : ""}
    ${section("From memory", d.memory_claims, "ph-brain", "mem")}
    ${section("Conflicts with the transcripts", d.conflicts, "ph-warning", "no")}
    ${section("Unsure about", d.uncertain, "ph-question", "muted")}
    <div class="meta"><span>${esc(llm.model_version)}</span><span>${((llm.latency_ms || 0) / 1000).toFixed(1)} s</span>
      <span>${u.input ?? "?"} in / ${u.output ?? "?"} out / ${u.thinking ?? "?"} thinking</span>${check}${retries}${
      res.reused_from_run ? `<span>reused from run ${res.reused_from_run}, no new call</span>` : ""}</div>
    ${footer}
  </article>`;
}

/* v3: the scenes the graph rows point at, shown like passages so a citation chip can jump to them; scenes already
   shown as passages are skipped (their ids exist) */
function graphScenesHTML(plan, passages, ctx) {
  const have = sentSet(passages), scenes = new Map();
  for (const l of graphLines(plan)) {
    const key = `${l.season}-${l.episode}-${l.scene}`;
    if (have.has(key)) continue;
    if (!scenes.has(key)) scenes.set(key, { l, lines: [] });
    scenes.get(key).lines.push(l);
  }
  if (!scenes.size) return "";
  const body = [...scenes.entries()].sort(([, a], [, b]) => a.l.season - b.l.season || a.l.episode - b.l.episode || a.l.scene - b.l.scene)
    .map(([key, { l, lines }]) => `<div class="scene" id="scene-${ctx.prefix}-${key}"><div class="scene-no">S${l.season}E${l.episode} SCENE ${l.scene}</div>${
      lines.map((x) => `<div class="line"><span class="who">${esc(x.speaker)}</span><span>${esc(x.text).replace(/\[([^\]]*)\]/g, `<span class="dir">($1)</span>`)}</span></div>`).join("")}</div>`).join("");
  return `<details class="passage"><summary>Lines from the graph<small>${scenes.size} more scene${scenes.size === 1 ? "" : "s"}</small></summary>
    <div class="chunk">${body}</div></details>`;
}
function passagesHTML(passages, ctx, devLabels, openFirst) {
  return passages.map((p, i) => `
    <details class="passage" ${openFirst && i === 0 ? "open" : ""}>
      <summary>S${p.season}E${p.episode} ${esc(p.title)}<small>scenes ${p.scene_start}-${p.scene_end}</small></summary>
      ${p.chunks.map((c) => renderChunk(p, c, ctx, devLabels)).join("")}
    </details>`).join("");
}
function renderSources() {
  const show = state.mode === "dev" || state.showSources;
  if (!show) { $("sources-wrap").innerHTML = ""; return; }
  const r = state.data.retrieval, t = r.timings_ms, dev = state.mode === "dev";
  const hybrid = ["hybrid", "enhanced", "graph"].includes(r.method), dash = (v) => (v == null ? "–" : v);
  const hits = dev ? `<details class="sub"><summary>Search hits (top ${r.k} ${hybrid
      ? "by vector + keyword search, merged by rank" : "by cosine distance"}${
      r.hits.some((h) => h.scores?.sql || h.scores?.graph) ? ", plus scenes found by SQL or the graph" : ""})</summary>
    <div class="table-wrap"><table><thead><tr><th>#</th>${hybrid
      ? "<th>Vector rank</th><th>Keyword rank</th><th>Fused score</th>" : "<th>Distance</th>"}<th>Episode</th><th>Scenes</th></tr></thead><tbody>${
    r.hits.map((h) => `<tr><td>${h.rank}</td>${!hybrid ? `<td>${h.distance.toFixed(3)}</td>`
      : h.scores.sql || h.scores.graph ? `<td colspan="3">found by ${h.scores.sql ? "SQL" : "the graph"}</td>`
      : `<td>${dash(h.scores.vector_rank)}</td><td>${dash(h.scores.bm25_rank)}</td><td>${h.scores.rrf.toFixed(4)}</td>`}
      <td>S${h.season}E${h.episode} ${esc(h.title)}</td><td>${h.scene_start}-${h.scene_end}</td></tr>`).join("")}</tbody></table></div></details>` : "";
  const found = { vector: "meaning only", hybrid: "meaning + exact words",
                  enhanced: "question rewritten, meaning + exact words, SQL",
                  graph: "question rewritten, meaning + exact words, SQL and graph" }[r.method] || r.method;
  $("sources-wrap").innerHTML = `<section class="sheet sources">
    <h2>Sources</h2>
    <div class="sub-line">${r.passages.length} passages sent to the model. ${dev && r.version
      ? `Found with ${esc(r.version)} (${found}). ` : ""}Retrieval took ${t.total} ms.</div>
    ${dev ? planHTML(r.plan) : ""}${hits}${passagesHTML(r.passages, MAIN, dev, true)}${graphScenesHTML(r.plan, r.passages, MAIN)}
  </section>`;
}

/* dev mode, v2: what the enhancer made of the question, and what its SQL returned */
function planHTML(plan) {
  if (!plan) return "";
  const res = plan.sql_result;
  const rows = !res ? "" : res.error
    ? `<p class="sub-line">The query failed${res.retried ? " (after one fix)" : ""}: ${esc(res.error)}</p>`
    : `<div class="table-wrap"><table><thead><tr>${res.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${
        res.rows.map((row) => `<tr>${row.map((v) => `<td>${esc(String(v ?? ""))}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
       <p class="sub-line">${res.rows.length} rows${res.truncated ? " (cut at 50: more exist)" : ""}${res.retried ? ", after one fix" : ""}, ${res.ms} ms.</p>`;
  return `<details class="sub"><summary>Search preparation (${plan.enhancer.latency_ms} ms)</summary>
    <p class="sub-line">Searched for: <strong>${esc(plan.search_text || "the question as asked")}</strong></p>
    ${plan.sql ? `<pre class="sql">${esc(plan.sql)}</pre>${plan.assumptions ? `<p class="sub-line">${esc(plan.assumptions)}</p>` : ""}${rows}`
               : `<p class="sub-line">No SQL for this question.</p>`}
    ${"graph_sql" in plan ? graphHTML(plan) : ""}
  </details>`;
}

/* dev mode, v3: the enhancer's graph query and the rows it returned, each with the transcript lines shown to the model */
function graphHTML(plan) {
  const g = plan.graph_result;
  if (!plan.graph_sql || !g) return `<p class="sub-line">No graph query for this question.</p>`;
  if (g.error) return `<pre class="sql">${esc(plan.graph_sql)}</pre><p class="sub-line">The graph query failed${g.retried ? " (after one fix)" : ""}: ${esc(g.error)}</p>`;
  const cols = g.columns.map((c, i) => [c, i]).filter(([c]) => c !== "line_ids");
  const body = g.rows.map((row, n) => `<tr>${cols.map(([, i]) => `<td>${esc(String(row[i] ?? ""))}</td>`).join("")}</tr>${
    (g.lines?.[n] || []).map((l) => `<tr><td colspan="${cols.length}" class="sub-line">S${l.season}E${l.episode} sc.${l.scene} · ${esc(l.speaker)}: ${esc(l.text.slice(0, 200))}</td></tr>`).join("")}`).join("");
  return `<p class="sub-line"><strong>Graph query</strong></p><pre class="sql">${esc(plan.graph_sql)}</pre>
    <div class="table-wrap"><table><thead><tr>${cols.map(([c]) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>
    <p class="sub-line">${g.rows.length} graph rows${g.truncated ? " (cut at 50: more exist)" : ""}${g.retried ? ", after one fix" : ""}, ${g.ms} ms.</p>`;
}
function renderChunk(p, c, ctx, devLabels) {
  const scenes = c.content.split("\n\n").slice(1).map((block) => {   // drop the chunk header; the rest are scene blocks
    const [first, ...lines] = block.split("\n");
    const n = (first.match(/^Scene (\d+)/) || [])[1];
    return `<div class="scene" id="scene-${ctx.prefix}-${p.season}-${p.episode}-${n}"><div class="scene-no">SCENE ${n}</div>${
      lines.map((l) => {
        const i = l.indexOf(": ");
        const who = i > 0 ? esc(l.slice(0, i)) : "";
        const text = esc(i > 0 ? l.slice(i + 2) : l).replace(/\[([^\]]*)\]/g, `<span class="dir">($1)</span>`);
        return `<div class="line"><span class="who">${who}</span><span>${text}</span></div>`;
      }).join("")}</div>`;
  }).join("");
  const label = devLabels ? `<div class="chunk-label">${c.is_hit ? "matched" : "neighbour"}</div>` : "";
  return `<div class="chunk${c.is_hit && devLabels ? " hit" : ""}">${label}${scenes}</div>`;
}

/* ---------- history: one question at a time, loaded as you scroll ---------- */
const hist = { started: false, next: null, hasMore: true, loading: false, failed: false, items: {} };
let histObserver = null;

function resetHistory() {
  hist.started = true;
  hist.next = null; hist.hasMore = true; hist.failed = false; hist.items = {};
  $("history-list").innerHTML = "";
  $("history-sentinel").textContent = "Loading…";
  if (!histObserver) {
    histObserver = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) loadNextHistory();
    }, { rootMargin: "600px 0px" });
    histObserver.observe($("history-sentinel"));
  }
  loadNextHistory();
}

async function loadNextHistory() {
  if (hist.loading || hist.failed || !hist.hasMore || state.view !== "history") return;
  hist.loading = true;
  try {
    const url = "/api/history" + (hist.next != null ? `?before=${hist.next}` : "");
    const res = await fetch(url, { headers: adminHeaders() });
    if (res.status === 401) { location.reload(); return; }      // the site password cookie expired
    if (res.status === 403) throw new Error("History is for the admin: open Admin, enter the admin password (not the site password), then try again.");
    if (!res.ok) throw new Error(`The server answered ${res.status}.`);
    const data = await res.json();
    if (data.run) {
      hist.items[data.run.run_id] = data.run;
      $("history-list").insertAdjacentHTML("beforeend", historyItemHTML(data.run));
      hist.next = data.run.run_id;
    }
    hist.hasMore = data.has_more;
    $("history-sentinel").textContent = hist.hasMore ? "Loading…"
      : Object.keys(hist.items).length ? "That's every question so far." : "No questions yet. Ask one!";
  } catch (err) {
    hist.failed = true;                          // stop here: retrying on its own would hammer the server
    $("history-sentinel").innerHTML = `Couldn't load more. ${esc(err.message)} <button type="button" class="pill" id="history-retry">Try again</button>`;
  } finally {
    hist.loading = false;
  }
  if (hist.failed) return;
  // keep filling while the sentinel is still on screen (tall screens, short items)
  const r = $("history-sentinel").getBoundingClientRect();
  if (hist.hasMore && r.top < innerHeight + 600) loadNextHistory();
}

function historyItemHTML(run) {
  const ctx = { prefix: `h${run.run_id}`, sent: sentSet(run.passages, run.plan) };
  const when = new Date(run.asked_at).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  const reviews = run.reviews || [];
  const cards = ["hybrid", "rag", "llm"].map((sys) =>
    renderCard(sys, run.answers[sys], ctx, adminKey ? reviewHTML(run.run_id, sys, reviews.find((r) => r.reviewer === "me" && r.system === sys)) : "")).join("");
  const fb = adminKey && run.feedback ? `<div class="fb-line"><i class="ph ph-chat-circle-text"></i>${
    run.feedback.length ? run.feedback.map((f) => f.kind === "satisfied" ? `Satisfactory: ${f.satisfied ? "yes" : "no"}`
                                                                        : `Preferred: ${f.preferred.toUpperCase()}`).join("<span>/</span>")
                        : "No feedback on this question."}</div>` : "";
  return `<article class="sheet hist-item" id="run-${run.run_id}">
    <h3 class="hist-q">${esc(run.question)}</h3>
    <div class="hist-meta"><span>${esc(when)}</span><span>asked in ${esc(run.mode)} mode</span><span>via ${esc(run.source)}</span>
      <span>${esc(run.version)}, ${run.k} chunks, neighbours ${run.expand}</span><span>run ${run.run_id}</span></div>
    ${fb}
    <div class="cards">${cards}</div>
    <details class="sub"><summary>Sources (${run.passages.length} passages)</summary>${passagesHTML(run.passages, ctx, true, false)}${graphScenesHTML(run.plan, run.passages, ctx)}</details>
  </article>`;
}

function reviewHTML(runId, system, mine) {
  const id = `${runId}-${system}`;
  return `<div class="review" data-run="${runId}" data-system="${system}">
    <div class="verdicts">${VERDICTS.map((v) => `<button type="button" class="pill" data-verdict="${v}"
      aria-pressed="${mine?.verdict === v}">${v[0].toUpperCase() + v.slice(1)}</button>`).join("")}</div>
    <textarea id="notes-${id}" aria-label="Review notes" placeholder="Notes (optional)">${esc(mine?.notes || "")}</textarea>
    <div class="row"><button type="button" class="pill" data-save-review>Save review</button><span class="saved" id="rv-status-${id}"></span></div>
  </div>`;
}

async function saveReview(box) {
  const runId = +box.dataset.run, system = box.dataset.system, id = `${runId}-${system}`;
  const verdict = box.querySelector('[data-verdict][aria-pressed="true"]')?.dataset.verdict;
  const status = $(`rv-status-${id}`);
  if (!verdict) { status.className = "saved fail"; status.textContent = "Pick a verdict first."; return; }
  try {
    const res = await fetch("/api/review", { method: "POST", headers: { "Content-Type": "application/json", ...adminHeaders() },
      body: JSON.stringify({ run_id: runId, system, verdict, notes: $(`notes-${id}`).value || null }) });
    status.className = res.ok ? "saved" : "saved fail";
    status.innerHTML = res.ok ? `<i class="ph ph-check"></i> Saved` : "Couldn't save. Is admin mode still on?";
  } catch { status.className = "saved fail"; status.textContent = "Couldn't reach the server."; }
}

/* ---------- clicks: citations, sources toggle, feedback, reviews ---------- */
document.addEventListener("click", async (e) => {
  const chip = e.target.closest("a.cite[data-target]");
  if (chip) {
    e.preventDefault();
    if (chip.dataset.ctx === MAIN.prefix && state.mode === "user" && !state.showSources) { state.showSources = true; render(); }
    const el = document.getElementById(chip.dataset.target);
    if (!el) return;
    for (let d = el.closest("details"); d; d = d.parentElement?.closest("details")) d.open = true;
    el.scrollIntoView({ behavior: reduceMotion() ? "auto" : "smooth", block: "center" });
    el.classList.remove("flash"); void el.offsetWidth; el.classList.add("flash");
    return;
  }
  if (e.target.closest("#history-retry")) { hist.failed = false; $("history-sentinel").textContent = "Loading…"; loadNextHistory(); return; }
  if (e.target.closest("#toggle-sources")) { state.showSources = !state.showSources; render(); return; }

  const verdictBtn = e.target.closest(".review [data-verdict]");
  if (verdictBtn) {
    for (const b of verdictBtn.parentElement.querySelectorAll("[data-verdict]")) b.setAttribute("aria-pressed", String(b === verdictBtn));
    return;
  }
  const saveBtn = e.target.closest("[data-save-review]");
  if (saveBtn) { saveReview(saveBtn.closest(".review")); return; }

  const fb = e.target.closest("button[data-fb]");
  if (!fb || state.data?.run_id == null) return;
  const kind = fb.dataset.fb;
  const body = { run_id: state.data.run_id, kind };
  if (kind === "satisfied") { body.satisfied = fb.dataset.val === "true"; state.feedback.satisfied = body.satisfied; }
  else { body.preferred = fb.dataset.val; state.feedback.preferred = body.preferred; }
  const key = kind === "satisfied" ? "satisfied" : "preferred";
  try {
    const res = await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    state.status[key] = res.ok ? "saved" : "fail";
  } catch { state.status[key] = "fail"; }
  render();
});

/* ---------- theme music: once per page open; browsers allow sound only after an interaction ---------- */
(() => {
  const audio = $("theme"), button = $("sound");
  let muted = store.get("office-rag-muted") === "1";
  audio.volume = 0.5;
  const show = () => {
    button.innerHTML = `<i class="ph ${muted ? "ph-speaker-slash" : "ph-speaker-high"}"></i>`;
    button.title = button.ariaLabel = muted ? "Unmute music" : "Mute music";
  };
  const play = () => (muted ? Promise.resolve() : audio.play());
  const playOnFirstInteraction = () => {
    const start = (e) => {
      if (button.contains(e.target)) return;           // clicking mute first shouldn't start the music
      ["pointerdown", "keydown"].forEach((t) => removeEventListener(t, start));
      play().catch(() => {});
    };
    ["pointerdown", "keydown"].forEach((t) => addEventListener(t, start));
  };
  audio.addEventListener("canplay", () => { button.hidden = false; show(); }, { once: true });
  audio.addEventListener("error", () => { button.hidden = true; });
  button.addEventListener("click", (e) => {
    e.stopPropagation();
    muted = !muted;
    store.set("office-rag-muted", muted ? "1" : "0");
    if (muted) audio.pause(); else audio.play().catch(() => {});
    show();
  });
  play().catch(() => playOnFirstInteraction());
})();

/* ---------- start ---------- */
renderAdmin();
renderLock();
renderSystems();
setMode(state.mode);
renderEmpty();
setView(state.view);
