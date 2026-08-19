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
- **Data file:** `/opt/weigh-off-server/weighoff.db` (SQLite)
- **Secret:** `WEIGHOFF_PASSPHRASE` set in the systemd unit (NOT in git) — this is the only front door to a public app
- **Git repo:** `https://github.com/petejblakemore/weigh-off` (private)
- **Runtime:** Python 3 standard library only — no dependencies to install

**Common commands**
```bash
# deploy an update
cd /opt/weigh-off-server && git pull && sudo systemctl restart weigh-off
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
- [ ] Deploy pending Weigh Off changes (units fix, longer messages, longer fireworks, mobile pass): `git pull` + `sudo systemctl restart weigh-off`
- [ ] When adding anything new: add it to this file **before** you forget the details
- [ ] Keep secrets (passphrases, keys, `CMMS_SECRET_KEY`) in systemd units or `.env` files, never in git
- [ ] Tidy the remaining CMMS security items above (strip the old key literal from `startup.sh` in git; confirm `.pem` files are gitignored)
