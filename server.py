#!/usr/bin/env python3
"""
The Weigh Off — self-contained server.

Standard library only (Python 3.11+). No pip install required.
Serves the front-end (static/index.html) and a small JSON API backed by SQLite.
Access is gated by a single shared passphrase (see WEIGHOFF_PASSPHRASE below).

Data model mirrors the front-end:
  people(id, name, cm, sex, color)
  entries(id, person_id, date, kg, waist)
  history(key, end_iso, winner, cook, standings_json)

Run:
  WEIGHOFF_PASSPHRASE="something-secret" python3 server.py
Environment variables (all optional except the passphrase in production):
  WEIGHOFF_PASSPHRASE  shared passphrase required to use the app
  WEIGHOFF_HOST        bind address (default 127.0.0.1 — Caddy proxies to it)
  WEIGHOFF_PORT        bind port    (default 8770)
  WEIGHOFF_DB          path to the SQLite file (default weighoff.db next to this file)
"""

import json
import os
import sqlite3
import secrets
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
DB_PATH = Path(os.environ.get("WEIGHOFF_DB", BASE / "weighoff.db"))
HOST = os.environ.get("WEIGHOFF_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEIGHOFF_PORT", "8770"))
PASSPHRASE = os.environ.get("WEIGHOFF_PASSPHRASE", "")

# In-memory set of valid session tokens. Cleared on restart (friends just log in again).
SESSIONS = set()


# ---------------- database ----------------
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS people (
                id    TEXT PRIMARY KEY,
                name  TEXT NOT NULL,
                cm    REAL NOT NULL,
                sex   TEXT NOT NULL DEFAULT 'm',
                color TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entries (
                id        TEXT PRIMARY KEY,
                person_id TEXT NOT NULL REFERENCES people(id) ON DELETE CASCADE,
                date      TEXT NOT NULL,
                kg        REAL NOT NULL,
                waist     REAL
            );
            CREATE TABLE IF NOT EXISTS history (
                key            TEXT PRIMARY KEY,
                end_iso        TEXT,
                winner         TEXT,
                cook           TEXT,
                standings_json TEXT
            );
            """
        )


def load_state():
    with db() as conn:
        people = [dict(r) for r in conn.execute("SELECT * FROM people")]
        entries = [dict(r) for r in conn.execute("SELECT * FROM entries")]
        history = [dict(r) for r in conn.execute("SELECT * FROM history")]
    by_id = {}
    for p in people:
        p["entries"] = []
        by_id[p["id"]] = p
    for e in entries:
        row = by_id.get(e["person_id"])
        if row is not None:
            item = {"id": e["id"], "date": e["date"], "kg": e["kg"]}
            if e["waist"] is not None:
                item["waist"] = e["waist"]
            row["entries"].append(item)
    return {
        "people": [
            {k: p[k] for k in ("id", "name", "cm", "sex", "color", "entries")}
            for p in people
        ],
        "history": [
            {
                "key": h["key"],
                "endISO": h["end_iso"],
                "winner": h["winner"],
                "cook": h["cook"],
                "standings": json.loads(h["standings_json"] or "[]"),
            }
            for h in history
        ],
    }


def save_state(state):
    """Full replace: the front-end always sends the whole picture."""
    people = state.get("people", [])
    history = state.get("history", [])
    with db() as conn:
        conn.execute("DELETE FROM entries")
        conn.execute("DELETE FROM people")
        conn.execute("DELETE FROM history")
        for p in people:
            conn.execute(
                "INSERT INTO people(id,name,cm,sex,color) VALUES(?,?,?,?,?)",
                (p["id"], p["name"], p["cm"], p.get("sex", "m"), p["color"]),
            )
            for e in p.get("entries", []):
                conn.execute(
                    "INSERT INTO entries(id,person_id,date,kg,waist) VALUES(?,?,?,?,?)",
                    (e["id"], p["id"], e["date"], e["kg"], e.get("waist")),
                )
        for h in history:
            conn.execute(
                "INSERT INTO history(key,end_iso,winner,cook,standings_json) VALUES(?,?,?,?,?)",
                (
                    h["key"],
                    h.get("endISO"),
                    h.get("winner"),
                    h.get("cook"),
                    json.dumps(h.get("standings", [])),
                ),
            )


# ---------------- http handler ----------------
class Handler(BaseHTTPRequestHandler):
    server_version = "WeighOff/1.0"

    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _token(self):
        # Expect "Authorization: Bearer <token>"
        h = self.headers.get("Authorization", "")
        return h[7:] if h.startswith("Bearer ") else ""

    def _authed(self):
        if not PASSPHRASE:  # no passphrase set = open (dev only)
            return True
        tok = self._token()
        return any(hmac.compare_digest(tok, s) for s in SESSIONS)

    # ---- static files ----
    def _serve_static(self, rel):
        # Only ever serve from the static/ directory.
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC.resolve())) or not target.is_file():
            self.send_error(404)
            return
        ctype = {
            ".html": "text/html; charset=utf-8",
            ".js": "text/javascript",
            ".css": "text/css",
            ".svg": "image/svg+xml",
        }.get(target.suffix, "application/octet-stream")
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._serve_static("index.html")
        if self.path == "/api/state":
            if not self._authed():
                return self._json(401, {"error": "unauthorized"})
            return self._json(200, load_state())
        if self.path.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        # any other path -> static asset
        return self._serve_static(self.path.lstrip("/"))

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._json(400, {"error": "bad json"})

        if self.path == "/api/login":
            if not PASSPHRASE:
                return self._json(200, {"token": "open"})
            given = str(payload.get("passphrase", ""))
            if hmac.compare_digest(given, PASSPHRASE):
                token = secrets.token_urlsafe(24)
                SESSIONS.add(token)
                return self._json(200, {"token": token})
            return self._json(401, {"error": "wrong passphrase"})

        if self.path == "/api/state":
            if not self._authed():
                return self._json(401, {"error": "unauthorized"})
            try:
                save_state(payload)
            except Exception as exc:  # keep the server alive on bad input
                return self._json(400, {"error": str(exc)})
            return self._json(200, {"ok": True})

        return self._json(404, {"error": "not found"})

    def log_message(self, fmt, *args):  # quieter logs
        pass


def main():
    if not STATIC.exists():
        raise SystemExit(f"Missing static/ directory at {STATIC}")
    init_db()
    if not PASSPHRASE:
        print("WARNING: WEIGHOFF_PASSPHRASE is not set — the app is OPEN to anyone.")
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"The Weigh Off running on http://{HOST}:{PORT}  (db: {DB_PATH})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()
