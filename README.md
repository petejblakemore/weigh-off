# The Weigh Off

A friendly, self-hosted weight/BMI/waist tracker for a small group. Runs on your
own Debian box with **zero third-party services** and **no pip dependencies** —
just Python 3's standard library and a SQLite file.

- Shared board: everyone with the passphrase sees and updates the same data.
- Scoring: combined 50/50 weight + waist % lost each quarter, with graceful
  weight-only fallback. Gold stars reward *steady* fortnightly loss (not crash diets).
- Hall of Fame: each 90-day quarter is banked automatically with winner + who cooks.

---

## 1. Push to a new private GitHub repo

From this project folder on your machine:

```bash
git init
git add .
git commit -m "The Weigh Off: self-hosted tracker"
git branch -M main
```

Create an **empty private repo** on GitHub called `weigh-off` (no README/gitignore —
this project already has them), then:

```bash
git remote add origin git@github.com:YOUR_USERNAME/weigh-off.git
git push -u origin main
```

> The `.gitignore` already keeps `weighoff.db` (your friends' data) and any real
> passphrase out of the repo. Verify with `git status` before your first commit —
> you should NOT see `weighoff.db` listed.

---

## 2. Get it onto the Debian box

On **blackbox**:

```bash
sudo mkdir -p /opt/weigh-off-server
sudo chown $USER /opt/weigh-off-server
git clone git@github.com:YOUR_USERNAME/weigh-off.git /opt/weigh-off-server
cd /opt/weigh-off-server
```

Nothing to install — Python 3.13 on the box already has `sqlite3` and the HTTP
server built in.

### Quick test (foreground)

```bash
WEIGHOFF_PASSPHRASE="pick-a-good-one" python3 server.py
```

Visit `http://127.0.0.1:8770` on the box (or via an SSH tunnel). You should get the
passphrase screen. Ctrl-C to stop, then set it up as a service below.

---

## 3. Run it as a systemd service (starts on boot, restarts on crash)

```bash
# Create the service account the unit expects
sudo useradd --system --home /opt/weigh-off-server weighoff || true
sudo chown -R weighoff /opt/weigh-off-server

# Install the unit, then EDIT it to set your real passphrase
sudo cp deploy/weigh-off.service /etc/systemd/system/weigh-off.service
sudo nano /etc/systemd/system/weigh-off.service   # set WEIGHOFF_PASSPHRASE=...

sudo systemctl daemon-reload
sudo systemctl enable --now weigh-off
sudo systemctl status weigh-off        # should say active (running)
journalctl -u weigh-off -f             # live logs
```

The server binds to `127.0.0.1:8770` — it is **not** exposed to the internet directly.
Caddy (next step) is what faces the outside world.

---

## 4. HTTPS with Caddy (recommended)

The box has no web server yet, so install Caddy (official Debian package):

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Then point Caddy at your No-IP hostname:

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile      # replace yourname.ddns.net with your real host
sudo systemctl restart caddy
```

**Firewall / router:** forward ports **80 and 443** through your firewall hole to this
box. Caddy needs 80 to obtain the Let's Encrypt certificate and 443 to serve HTTPS.
Once done, your friends visit `https://yourname.ddns.net` and get a padlock.

> Prefer plain HTTP for now? Skip Caddy and forward your chosen port straight to
> 8770 instead — but weigh-ins will travel unencrypted. Adding Caddy later is easy.

---

## 5. Day-to-day

- **Add friends:** each person opens the URL, enters the passphrase once, and adds
  themselves as a contender (name, sex, height). Then they log weigh-ins.
- **Update the app:** `git pull` on the box, then `sudo systemctl restart weigh-off`.
- **Back up the data:** copy `weighoff.db` somewhere safe periodically, or use the
  in-app **Export** button. To restore, use **Import**.

## Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `WEIGHOFF_PASSPHRASE` | *(empty = open!)* | Shared passphrase to use the app |
| `WEIGHOFF_HOST` | `127.0.0.1` | Bind address (leave as-is behind Caddy) |
| `WEIGHOFF_PORT` | `8770` | Bind port |
| `WEIGHOFF_DB` | `./weighoff.db` | SQLite file location |

## How it fits together

```
Browser  ──HTTPS──►  Caddy (:443)  ──proxy──►  server.py (127.0.0.1:8770)  ──►  weighoff.db
                     Let's Encrypt              Python stdlib, SQLite
```

## A note on the security model

One shared passphrase gates the whole app; there are no per-person accounts, so
anyone with the passphrase can edit anyone's weigh-ins. That's a deliberate,
friend-sized trade-off. If it ever needs tightening, the natural next step is
per-person accounts — ask and it can be added.
