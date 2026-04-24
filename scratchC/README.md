# Nielit Community

A private social feed for the NIELIT community — Flask + PostgreSQL, packaged as a self-contained Docker stack with auto-HTTPS via Caddy and Let's Encrypt.

Features: posts (text, photos, albums, videos, short-form, polls, links, shares), reactions (6 types), threaded comments, saved posts, friends, notifications, pages, groups, admin moderation, sponsored posts, personalised ranked feed with dwell-time signals, search, insights.

---

## TL;DR — the whole point

You want to **run apps on your VM without reinstalling anything**. This repo is structured so that:

- The code lives in **Git**. You push changes from your laptop, pull them on the VM.
- The app runs entirely in **Docker containers**. Start it with `docker compose up -d`, stop it with `docker compose down`. No apt packages, no system services, no systemd units to clean up.
- **Don't like it?** `docker compose down -v` wipes it completely (containers + volumes + database). `git clone` a different repo and `docker compose up -d` — you're running a different app in under a minute.

---

## 1. First-time VM setup (do this once)

SSH into your Azure VM and run:

```bash
git clone <your-repo-url> nielit-community
cd nielit-community
sudo bash scripts/bootstrap-docker.sh
```

This installs Docker + Compose plugin and opens firewall ports 22, 80, 443. After it finishes, log out and back in so your user picks up the `docker` group.

Also verify:

- DNS for `edtech05.centralindia.cloudapp.azure.com` points at your VM's public IP  (`dig +short <domain>`)
- Azure NSG allows inbound TCP on 80 and 443

---

## 2. Configure and launch

```bash
cp .env.example .env

# Generate two strong random strings
echo "SECRET_KEY=$(openssl rand -base64 48 | tr -d '=+/' | cut -c1-48)"
echo "DB_PASSWORD=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)"

# Paste those into .env and set APP_DOMAIN + ADMIN_EMAIL
nano .env

# Launch
docker compose up -d
```

First run takes a couple of minutes: Docker pulls `postgres:16-alpine` and `caddy:2-alpine`, builds the web image, waits for Postgres, creates the schema, then Caddy requests an SSL certificate from Let's Encrypt.

Watch progress with `docker compose logs -f`.

When Caddy prints something like `certificate obtained successfully` you're live at **https://edtech05.centralindia.cloudapp.azure.com**.

**Sign up — the first registered user becomes admin.**

---

## 3. Day-to-day commands

All commands are run from inside the repo directory.

| Task | Command |
|------|---------|
| Start stack (background) | `docker compose up -d` |
| Stop stack (keep data) | `docker compose stop` |
| Resume stopped stack | `docker compose start` |
| Stop and remove containers (keep data in volumes) | `docker compose down` |
| **Remove everything including database and uploads** | `docker compose down -v` |
| Tail logs | `docker compose logs -f` |
| Tail only app | `docker compose logs -f web` |
| Check status | `docker compose ps` |
| Shell inside web container | `docker compose exec web bash` |
| Open psql on the database | `docker compose exec db psql -U nielit nielit_community` |
| Promote a user to admin | `docker compose exec web flask promote-admin` |
| Rebuild web image after code changes | `docker compose build web && docker compose up -d` |
| Backup database | `bash scripts/backup-db.sh` |

There's also a `Makefile` with shorter aliases — run `make help` to see all targets.

---

## 4. Pushing code changes

Typical workflow from your laptop:

```bash
# Edit code locally
git add .
git commit -m "Fix: reaction button bug"
git push

# On the VM
ssh azureuser@20.244.42.214
cd nielit-community
git pull
docker compose build web
docker compose up -d
```

The whole cycle takes about 30 seconds on the VM. The `db` and `caddy` containers aren't rebuilt, so their state (users, posts, SSL certs) survives.

---

## 5. Running a different app instead

The whole point of the Docker setup — **disposability**. To swap this app for something else:

```bash
# In the nielit-community directory:
docker compose down -v         # removes containers AND data volumes
cd ..

# Clone and start a different app
git clone <other-repo-url> other-app
cd other-app
cp .env.example .env && nano .env
docker compose up -d
```

The new app can reuse ports 80/443 because the old stack is completely torn down. Caddy in the new stack will issue its own certificates.

> **Multiple apps at once?** You'd need each app to use a different internal port and a shared edge proxy (Traefik or a top-level Caddy). Out of scope here — but once you have that edge proxy running once, every future app just registers with it via labels. Ask if you want me to set that up.

---

## 6. Configuration reference

All settings live in `.env`. Restart the stack after changing them (`docker compose up -d` picks up new env vars).

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `APP_DOMAIN` | yes | — | The domain Caddy serves (and gets a cert for). Must resolve to this VM. |
| `ADMIN_EMAIL` | yes | — | Let's Encrypt sends renewal notices here. |
| `APP_NAME` | no | `Nielit Community` | Shown in the UI (`<title>`, header). |
| `SECRET_KEY` | yes | — | Flask session / CSRF signing key. Rotating it logs everyone out. |
| `DB_NAME` | no | `nielit_community` | |
| `DB_USER` | no | `nielit` | |
| `DB_PASSWORD` | yes | — | Used internally; still make it strong. |
| `MAX_CONTENT_LENGTH_MB` | no | `55` | Per-upload cap. Must match `request_body max_size` in `Caddyfile` if you raise it. |

---

## 7. Admin UI

Once logged in as admin, click the ⚙️ in the top bar:

- **Users** — enable/disable accounts, promote/demote admins
- **Posts** — soft-delete posts, restore deletions, view metrics per post
- **Reports** — review and resolve user reports
- **New sponsored post** — creates a post with a ranking boost and a "Sponsored" badge

---

## 8. Feed ranking

Each post is scored per-user:

```
score = w_aff × affinity                 # your interest in author/page/group
      + w_eng × engagement_velocity      # how fast reactions/comments are piling up
      + w_rec × recency_decay            # exponential half-life (24h)
      + 0.4  × post_type_preference      # your learned taste (video/photo/poll/link/text)
      + boosts                           # sponsored +1.0, own post −0.4, already-seen −0.8
      + noise                            # small exploration term
```

Weights and affinities are stored in `user_feed_weights` and `user_affinity`, and updated by `record_interaction()` on every reaction, comment, share, save, long dwell (>3 s), and long watch (>15 s). Visibility (`public`, `friends`, `friends_of_friends`, `only_me`) is enforced at candidate-fetch time. See `app/feed/ranking.py`.

---

## 9. Troubleshooting

### Caddy can't get a certificate

```bash
docker compose logs caddy
```

Most common causes:

1. **DNS not pointing at the VM yet.** Verify: `dig +short edtech05.centralindia.cloudapp.azure.com`
2. **Port 80 blocked.** Let's Encrypt needs to reach port 80 from the outside. Check Azure NSG and `sudo ufw status`.
3. **Rate limited.** If you restarted a lot while debugging, you may have hit LE's 5-per-week rate limit for the same domain. Wait an hour and try staging: edit `Caddyfile` to add `acme_ca https://acme-staging-v02.api.letsencrypt.org/directory` inside the site block.

### 502 Bad Gateway

The `web` container is failing. Check:

```bash
docker compose logs web
```

Usually a bad env var or a DB connection issue. The entrypoint waits up to 60s for the DB; if Postgres itself is broken (corrupt volume), logs will show it.

### "Database is starting up"

Normal on first boot — the entrypoint in the web container keeps retrying. Give it ~20 seconds.

### I forgot my admin password

```bash
docker compose exec web python -c "
from app import create_app
from app.extensions import db
from app.models import User
app = create_app()
with app.app_context():
    u = db.session.query(User).filter_by(username='YOUR_USERNAME').first()
    u.set_password('new-strong-password')
    db.session.commit()
    print('updated')
"
```

### Reset everything

```bash
docker compose down -v        # wipe containers AND volumes
docker compose up -d          # rebuild from scratch
```

Next user to sign up becomes the new admin.

---

## 10. Project layout

```
nielit-community/
├── app/                        # Flask package (models, routes, templates, static)
├── scripts/
│   ├── bootstrap-docker.sh     # One-time VM setup (installs Docker, opens firewall)
│   ├── backup-db.sh            # Dump postgres to ./backups/
│   └── smoketest.py            # Run all 41 routes against SQLite (CI-style check)
├── Caddyfile                   # Caddy config — auto-HTTPS, reverse proxy
├── docker-compose.yml          # db + web + caddy
├── docker-entrypoint.sh        # Waits for DB, runs init-db, then gunicorn
├── Dockerfile                  # Python 3.12-slim runtime image
├── Makefile                    # Convenience commands (make up/down/logs/shell)
├── requirements.txt
├── wsgi.py                     # Gunicorn entry point
├── .env.example                # Copy to .env and fill in
├── .dockerignore
└── .gitignore
```

---

## 11. Local development (without Docker)

If you want to hack on the code without spinning up containers:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export FLASK_APP=wsgi.py
export DATABASE_URL=sqlite:////tmp/nielit-dev.db
export SECRET_KEY=dev

flask init-db
python wsgi.py
# → http://localhost:5000
```

Run the smoke test (exercises every route against SQLite):

```bash
PYTHONPATH=. python scripts/smoketest.py
```

---

## 12. Git workflow

```bash
# One-time: initialize and push
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin git@github.com:<you>/nielit-community.git
git push -u origin main
```

From then on: edit → `commit` → `push` on your laptop; `pull` + `docker compose build web && docker compose up -d` on the VM.
