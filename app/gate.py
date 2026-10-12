"""Optional site password (SITE_PASSWORD). Off when the variable is unset, so the local app is unchanged.

One shared password for everyone you give it to. A correct password sets a signed cookie "<expiry>.<signature>" that lasts
SITE_SESSION_DAYS (default 7). Nothing is stored on the server: it only checks the signature. The signing key is derived
from the password, so changing SITE_PASSWORD signs everybody out. The admin password (History, retrieval settings) is separate.
"""
import hashlib
import hmac
import os
import time

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from app.public import _Windows, client_ip

COOKIE = "keleven_session"
OPEN_PATHS = {"/healthz", "/api/login", "/static/image/ryan.png"}     # the login page background; everything else needs the cookie
_attempts = _Windows()


def password():
    return os.environ.get("SITE_PASSWORD") or ""


def enabled():
    return bool(password())


def _days():
    return int(os.environ.get("SITE_SESSION_DAYS", "7"))


def _sign(expiry: int) -> str:
    key = ("keleven-session:" + password()).encode()
    return hmac.new(key, str(expiry).encode(), hashlib.sha256).hexdigest()


def make_cookie() -> tuple[str, int]:
    expiry = int(time.time()) + _days() * 86400
    return f"{expiry}.{_sign(expiry)}", _days() * 86400


def valid(cookie: str | None) -> bool:
    try:
        expiry, sig = (cookie or "").split(".", 1)
        return int(expiry) > time.time() and hmac.compare_digest(sig, _sign(int(expiry)))
    except ValueError:
        return False


def check_password(given: str) -> bool:
    return hmac.compare_digest((given or "").encode(), password().encode())


def throttle(request: Request):
    """At most 10 wrong or right tries per IP per 10 minutes, so the password can't be guessed by brute force."""
    ok, wait = _attempts.hit(client_ip(request), per_minute=10, per_day=200)
    if not ok:
        raise HTTPException(429, f"Too many attempts. Try again in {wait} seconds.")


async def middleware(request: Request, call_next):
    if not enabled() or request.url.path in OPEN_PATHS or valid(request.cookies.get(COOKIE)):
        return await call_next(request)
    if request.url.path.startswith("/api/"):
        return JSONResponse({"detail": "Sign in first."}, status_code=401)
    return HTMLResponse(LOGIN_PAGE, status_code=401)


LOGIN_PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Keleven</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 viewBox=%270 0 64 64%27%3E%3Crect width=%2764%27 height=%2764%27 rx=%2714%27 fill=%27%238aa5ff%27/%3E%3Cpath d=%27M20 14v36M20 33l22-19M26 31l18 19%27 fill=%27none%27 stroke=%27%230f1630%27 stroke-width=%277%27 stroke-linecap=%27round%27 stroke-linejoin=%27round%27/%3E%3C/svg%3E">
<style>
  :root { --paper:#101216; --sheet:#181b20; --ink:#e7e9ee; --ink-2:#b2b8c3; --rule:#2a2f37; --accent:#8aa5ff; --on:#0f1630; }
  @media (prefers-color-scheme: light) { :root { --paper:#f2f4f7; --sheet:#fcfcfd; --ink:#15181d; --ink-2:#485060; --rule:#dde2e9; --on:#fff; } }
  body { margin:0; min-height:100dvh; isolation:isolate; display:grid; place-items:center; background:var(--paper); color:var(--ink);
         font:15px/1.5 system-ui, sans-serif; padding:16px; box-sizing:border-box; }
  body::before { content:""; position:fixed; inset:-8px; z-index:-1; background:url(/static/image/ryan.png) center / cover no-repeat;
                 opacity:.65; filter:blur(1px) saturate(1.1); }
  @media (prefers-color-scheme: light) { body::before { opacity:.5; } }
  form { box-shadow:0 10px 40px rgba(0,0,0,.35); width:100%; max-width:360px; background:var(--sheet); border:1px solid var(--rule); border-radius:10px; padding:24px; position:relative; }
  h1 { font-size:20px; margin:0 0 4px; } p { color:var(--ink-2); margin:0 0 16px; }
  input { width:100%; box-sizing:border-box; padding:11px 12px; font:inherit; color:inherit; background:var(--paper);
          border:1px solid var(--rule); border-radius:8px; }
  button { margin-top:12px; width:100%; padding:11px; font:inherit; font-weight:600; border:0; border-radius:8px;
           background:var(--accent); color:var(--on); cursor:pointer; }
  #msg { min-height:20px; margin:10px 0 0; color:#e5736b; font-size:14px; }
</style></head><body>
<form id="f"><h1>Keleven</h1><p>Enter the password you were given.</p>
  <input id="p" type="password" autocomplete="current-password" aria-label="Password" autofocus required>
  <button type="submit">Enter</button><div id="msg" role="alert"></div></form>
<script>
document.getElementById("f").addEventListener("submit", async (e) => {
  e.preventDefault();
  const msg = document.getElementById("msg"); msg.textContent = "";
  try {
    const res = await fetch("/api/login", { method: "POST", headers: { "Content-Type": "application/json" },
                                            body: JSON.stringify({ password: document.getElementById("p").value }) });
    if (res.ok) { location.reload(); return; }
    msg.textContent = res.status === 429 ? (await res.json()).detail : "That password is not right.";
  } catch { msg.textContent = "Couldn't reach the server."; }
});
</script></body></html>"""
