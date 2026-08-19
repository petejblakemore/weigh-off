# blackbox — server inventory

> The single source of truth for what runs on this machine, where it lives, and how
> to look after it. Update this whenever you add, move, or remove anything.
> Convention: **always-on services live in `/opt`; things I develop and run as myself
> live in `~/Projects`.**

_Last updated: 2026-08-19_

---

## The rule (so nothing scatters)

| If it is... | It lives in... | Runs as... |
|---|---|---|
| An always-on service (has a systemd unit) | `/opt/<name>` | its own system user |
| A project I actively develop / run by hand | `~/Projects/<name>` | me (pete) |

When in doubt: *"Is it a running service, or a thing I hack on?"* — that answers where it goes.

---

## Services (always-on, under /opt)

### The Weigh Off — weight/BMI/waist tracker for friends
- **Path:** `/opt/weigh-off-server`
- **Runs as:** `weighoff` (system user, no login)
- **systemd unit:** `weigh-off.service` → `/etc/systemd/system/weigh-off.service`
- **Listens on:** `127.0.0.1:8770` (not exposed directly)
- **Public URL:** **`https://weigh-off.uk`** — reached via **Cloudflare Tunnel** (see below), NOT port forwarding
- **Data file:** `/opt/weigh-off-server/weighoff.db` (SQLite) — **gitignored**; friends' real data
- **Secret:** `WEIGHOFF_PASSPHRASE` set in the systemd unit (NOT in git) — this is the only front door to a public app
- **Git repo:** `https://github.com/petejblakemore/weigh-off` — **PUBLIC** (no secrets in code; passphrase is in the unit, DB is gitignored)
- **Runtime:** Python 3 standard library only — no dependencies to install
- **All files owned by `weighoff:weighoff`** — deploy AS that user (see below), never as `pete`

**Deploy (ALWAYS run as the weighoff user, over HTTPS):**
```bash
sudo -u weighoff git -C /opt/weigh-off-server pull && sudo systemctl restart weigh-off
```

**Other common commands**
```bash
# status / logs
sudo systemctl status weigh-off
journalctl -u weigh-off -f
# back up the data
cp /opt/weigh-off-server/weighoff.db ~/backups/weighoff-$(date +%F).db
```

---

## How the internet reaches this box (Cloudflare Tunnel)

**Everything public goes through a Cloudflare Tunnel — there is NO port forwarding.**
The EE Smart Hub (SH31B) blocks all inbound connections and can't be configured to
stop (TR-069 remote management holds the ports), so inbound hosting is impossible on
this line. Instead, `cloudflared` on the box makes an *outbound* connection to
Cloudflare, and Cloudflare routes public traffic back down it.

- **Connector:** `cloudflared` running as a systemd service (installed via dashboard token)
- **Tunnel name:** `blackbox` (Cloudflare dashboard → Zero Trust → Networks → Tunnels)
- **Domain:** `weigh-off.uk` — registered at **Cloudflare Registrar**, so DNS is auto-managed
  (this is a SEPARATE domain from `blakemore.me.uk`, which was deliberately left untouched)
- **Route:** Published application route → `weigh-off.uk` → `HTTP` → `localhost:8770`
- **HTTPS:** terminated by Cloudflare automatically (no cert to manage on the box)

**To publish another app later** (e.g. CMMS), don't touch the router — just add another
published application route in the same tunnel, e.g. `cmms.weigh-off.uk` → `localhost:8000`.

```bash
# tunnel connector status / logs
sudo systemctl status cloudflared
journalctl -u cloudflared -f
```

> **Retired:** Caddy and port forwarding were the original plan (Caddy + Let's Encrypt,
> ports 80/443 forwarded). Both were abandoned once the EE hub proved it blocks all
> inbound. Caddy is stopped and disabled (`sudo systemctl disable --now caddy`); the
> router port-forward rules are irrelevant and can be removed.

---

## Projects (development, under ~/Projects)

### CMMS — Home CMMS for the Plas Gwernoer estate
Self-hosted maintenance management: assets, work orders, parts, vendors, planned
maintenance, projects, multi-user login. FastAPI + uvicorn + SQLite + Jinja2.

- **Dev path (Mac Mini):** `/Users/pete/Projects/CMMS`
- **Production path (blackbox):** `/home/pete/CMMS`  ← note: home dir, not /opt (see rule below)
- **Runs as:** me (pete)
- **How to run:** `uvicorn cmms_ui:app --host 0.0.0.0 --port 8000` (from a `.venv`; see `startup.sh`)
- **Listens on:** `0.0.0.0:8000`
- **HTTPS:** uvicorn with mkcert certs — `data/192.168.1.224+3.pem` / `-key.pem`
- **Data:** `/home/pete/CMMS/data/cmms.db` (SQLite)
- **Backups:** `backup.sh` → `~/CMMS/backups` (keeps 14) + NAS `/mnt/puffin-cmms-backups` (keeps 90 days)
- **Secret:** `CMMS_SECRET_KEY` env var (session signing)
- **Git repo:** `https://github.com/petejblakemore/CMMS.git`
- **Poller:** `poller.py` pings network assets every 5 min (cron or systemd timer)
- **Deps:** `pip install -r requirements.txt` inside `.venv`
- **Deploy flow:** edit/test on Mac Mini → commit/push → pull on server → apply new `migrations/` in order
- **Docs:** `documents/` — SETUP, PRODUCTION_SETUP, GIT_WORKFLOW, SSL_SETUP, RUNBOOK, etc.

**Common commands**
```bash
# run (dev or prod)
cd ~/CMMS && source .venv/bin/activate && ./startup.sh
# back up the database
cd ~/CMMS && ./backup.sh
# apply a migration (back up first!)
cp data/cmms.db data/cmms.db.bak && sqlite3 data/cmms.db < migrations/0NN_name.sql
```

> ⚠️ **Security tidy-up:**
> 1. ~~`startup.sh` had a hard-coded `CMMS_SECRET_KEY`~~ — **rotated in production (2026-08-14).**
>    Still worth removing the literal from `startup.sh` in git so it's not in history going forward.
> 2. The `.pem` cert + **private key** files live in the project folder. Confirm
>    they're gitignored — a committed private key is worth rotating.

<!-- Copy a project block for each additional project. -->

---

## Why the two apps live in different places (deliberate)

- **The Weigh Off → `/opt`** because it's an always-on systemd **service** running as its
  own locked-down `weighoff` user. Service files don't belong in a personal home dir.
- **CMMS → `~/CMMS`** because you run it as **yourself** (uvicorn from your `.venv`,
  started by hand / `startup.sh`), and it's under active development.

Both are correct for what they are. The split is intentional, not scatter — this file
is the record that makes it so.

---

## Shared infrastructure

| Thing | Location | Notes |
|---|---|---|
| Cloudflare Tunnel | dashboard → Zero Trust → Networks → Tunnels (`blackbox`) | how the internet reaches this box; `cloudflared` service |
| Domain | `weigh-off.uk` @ Cloudflare Registrar | DNS auto-managed; separate from blakemore.me.uk |
| systemd units | `/etc/systemd/system/*.service` | `weigh-off.service`, `cloudflared` |
| Backups (Weigh Off) | `~/backups/` | SQLite copies |
| Backups (CMMS) | `~/CMMS/backups/` + NAS `/mnt/puffin-cmms-backups` | via `backup.sh` |
| CMMS TLS certs | `~/CMMS/data/*.pem` | mkcert (192.168.1.224+3); keep the key out of git |
| ~~Caddy~~ | `/etc/caddy/Caddyfile` | **retired** — stopped & disabled; tunnel replaced it |
| ~~No-IP / port-forwards~~ | router | **abandoned** — EE hub blocks inbound; tunnel used instead |

---

## Ports in use

| Port | Used by | Exposed? |
|---|---|---|
| 8770 | The Weigh Off | no — localhost only; public via Cloudflare Tunnel |
| 8000 | CMMS (uvicorn) | LAN only — `0.0.0.0`, HTTPS via mkcert certs |

---

## Maintenance checklist

- [ ] Monthly: back up `weighoff.db`; confirm CMMS `backup.sh` is running (cron/timer) and the NAS is mounted
- [ ] After any deploy: confirm `systemctl status` is `active (running)` (weigh-off, cloudflared) / uvicorn is up (CMMS)
- [x] Deploy Weigh Off v1 batch (units fix, plausibility guard, longer messages, 5s fireworks, mobile layout, demo-button removed) — **live 2026-08-19**
- [ ] Run `sudo systemctl disable --now caddy` to formally retire Caddy on the box
- [ ] Tidy stray `/opt/weigh-off-server/.ssh/` (leftover known_hosts from the SSH attempt; untracked, harmless)
- [ ] When adding anything new: add it to this file **before** you forget the details
- [ ] Keep secrets (passphrases, keys, `CMMS_SECRET_KEY`) in systemd units or `.env` files, never in git
- [ ] Tidy the remaining CMMS security items above (strip the old key literal from `startup.sh` in git; confirm `.pem` files are gitignored)

---

## Gotchas & lessons learned (read before touching hosting again)

**These cost real time to work out. Don't rediscover them.**

1. **This line CANNOT do inbound port forwarding.** The EE Smart Hub 2 (SH31B) reserves
   ports 80/443 for its own management and offers no way to disable remote access
   (TR-069 keeps it on). Every inbound approach — Caddy + Let's Encrypt HTTP-01/TLS-ALPN,
   direct port forwards — fails with "Timeout during connect." The public IP is real
   (`curl -4 ifconfig.me` matched, no CGNAT), but the hub swallows inbound regardless.
   **Answer: Cloudflare Tunnel (outbound-only). Never fight the router again.**

2. **Deploy as `weighoff`, not `pete`.** The repo and files are owned by `weighoff`
   (the service user). Running `git pull` as `pete` causes:
   - `fatal: detected dubious ownership` (fixed once via `git config --global --add safe.directory`)
   - `error: unable to create file … Permission denied` (pete can't write weighoff-owned files)
   - stray `pete`-owned files (e.g. `.git/FETCH_HEAD`) that then block the *next* pull
   **Fix that was applied:** `sudo chown -R weighoff:weighoff /opt/weigh-off-server`, and
   from now on deploy only via `sudo -u weighoff git -C … pull`.

3. **The repo remote must be HTTPS, not SSH.** The `weighoff` user has no SSH key, so
   `git@github.com:…` gives "Permission denied (publickey)". The remote is set to
   `https://github.com/petejblakemore/weigh-off.git`, and the repo is **public**, so
   HTTPS pulls need no auth. (If it were private, HTTPS as a login-less user needs a
   token baked into the URL — avoided by keeping it public.)

4. **"Local changes would be overwritten by merge" on the box** usually means a change
   was made directly on the box that also exists in the incoming commit. Check with
   `git diff`; if it's a duplicate/junk, `git checkout -- <file>` then pull. The Mac +
   GitHub is the source of truth — the box is only a deployment target, so discarding
   the box's local edits is safe.

5. **Let's Encrypt rate-limits failed attempts** (5 failures/hour/identifier). While
   debugging, don't keep restarting Caddy against a broken setup — it burns attempts and
   locks you out for an hour. (Moot now Caddy's retired, but the principle holds for any
   ACME retries.) Use `python3 -m http.server 80` + a phone on mobile data to test the
   path for free, without touching Let's Encrypt.

6. **`blakemore.me.uk` was deliberately NOT used** (it's live email + blog; moving its
   nameservers risked breaking mail). A separate domain, `weigh-off.uk`, was registered
   at Cloudflare Registrar specifically so DNS is auto-managed with zero nameserver changes.

7. **In the tunnel route, service type is HTTP not HTTPS** → `localhost:8770`. The box
   speaks plain HTTP internally; Cloudflare adds the public HTTPS. Selecting HTTPS there
   causes a 502.
