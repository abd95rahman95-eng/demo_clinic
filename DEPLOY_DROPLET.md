# DigitalOcean Droplet Deployment — HTTP-only first stage

This guide walks you from a fresh Ubuntu droplet to your Django site
serving on plain HTTP on port 80. It assumes:

- You've created an Ubuntu 22.04 or 24.04 LTS droplet on DigitalOcean.
- You can SSH in as `root` with your SSH key.
- Your code is on GitHub at the repo URL you'll paste below.
- TLS comes **later** (next stage with certbot — kept separate so you can
  test and iterate without fighting cert errors).

Replace the placeholders inline as you go:

| Placeholder              | Example                                |
|--------------------------|----------------------------------------|
| `<droplet-ip>`           | `134.122.45.67`                        |
| `<your-repo-url>`        | `https://github.com/abd95/demo_clinic.git` |
| `<your-domain>`          | `eyadatak.com` (skip if you don't have a domain yet) |

---

## 1. SSH in as root

From your Windows machine:

```cmd
ssh root@<droplet-ip>
```

If this is your first time, accept the host key fingerprint.

## 2. System updates + base packages

```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip python3-dev \
               build-essential libpq-dev nginx git ufw curl \
               libjpeg-dev zlib1g-dev
```

`libjpeg-dev` and `zlib1g-dev` are needed for Pillow (the image-compression
dependency from your `VisitAttachment` model).

## 3. Configure the firewall

DigitalOcean droplets ship with no firewall by default — but the OS-level
UFW lets you whitelist what's exposed:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 'Nginx HTTP'        # opens port 80
ufw --force enable
ufw status
```

Don't open port 8000 to the world — gunicorn only needs to bind to
`127.0.0.1:8000` and nginx will proxy to it.

## 4. Create a non-root user for the app

Running web apps as `root` is a security footgun. Create a user named
`eyadatak`:

```bash
adduser --disabled-password --gecos "" eyadatak
usermod -aG sudo eyadatak

# Copy your SSH key so you can log in directly as that user
mkdir -p /home/eyadatak/.ssh
cp /root/.ssh/authorized_keys /home/eyadatak/.ssh/
chown -R eyadatak:eyadatak /home/eyadatak/.ssh
chmod 700 /home/eyadatak/.ssh
chmod 600 /home/eyadatak/.ssh/authorized_keys
```

Open a **second** SSH session as the new user (keep the root session open
in case anything breaks):

```cmd
ssh eyadatak@<droplet-ip>
```

From now on, all the commands below run as `eyadatak`.

## 5. Clone your repo

```bash
cd ~
git clone <your-repo-url> demo_clinic
cd demo_clinic
```

If the repo is private, set up a deploy key first or use a personal access
token in the URL.

## 6. Python venv + dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn
```

`gunicorn` isn't in `requirements.txt` because it's a deployment-only
dependency — feel free to add it there if you prefer one source of truth.

## 7. Create the `.env` file

This is the **HTTP-only** stage — TLS settings stay off until you've got
nginx serving the site. Generate a fresh `SECRET_KEY` first:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Then create `.env` next to `manage.py`:

```bash
nano .env
```

Paste:

```
DEBUG=False
SECRET_KEY=<paste-the-50-char-key-from-above>
ALLOWED_HOSTS=<droplet-ip>,<your-domain>,www.<your-domain>,localhost,127.0.0.1
CSRF_TRUSTED_ORIGINS=http://<droplet-ip>,http://<your-domain>,http://www.<your-domain>
FORCE_SSL=False
USE_PROXY_SSL_HEADER=False

# Optional features — leave blank if you're not using them yet.
ANTHROPIC_API_KEY=
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
SIGNUP_NOTIFY_EMAILS=
```

Save: **Ctrl+O**, **Enter**, **Ctrl+X**.

## 8. Initialize the database + static files + admin user

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

`collectstatic` gathers all static assets (FA-not-applicable, your CSS/JS,
admin styles) into `staticfiles/`, where whitenoise will serve them.

> **About SQLite vs Postgres.** Your current `dj_database_url.config(default='sqlite:///db.sqlite3')`
> means SQLite "just works" out of the box. That's fine for the first
> dozens of clinics. When you outgrow it, install Postgres locally on the
> droplet (`apt install postgresql`), set `DATABASE_URL=postgres://...` in
> `.env`, and re-run `migrate` — Django + dj-database-url handles the rest.

## 9. Smoke-test gunicorn manually

Before wiring it up to systemd, confirm gunicorn can start:

```bash
gunicorn clinic_system.wsgi --bind 127.0.0.1:8000
```

In another SSH session (still on the droplet):

```bash
curl http://127.0.0.1:8000/healthz
```

Expected: `{"ok": true, "service": "eyadatak"}`. Hit **Ctrl+C** in the
first session to stop it.

If you get an error like `ModuleNotFoundError`, you forgot to activate the
venv (`source .venv/bin/activate`).

## 10. Run gunicorn as a systemd service

This makes gunicorn auto-start on boot and restart if it crashes.

```bash
sudo nano /etc/systemd/system/eyadatak.service
```

Paste (adjust paths if your username/repo names differ):

```ini
[Unit]
Description=Eyadatak Django app (gunicorn)
After=network.target

[Service]
User=eyadatak
Group=www-data
WorkingDirectory=/home/eyadatak/demo_clinic
EnvironmentFile=/home/eyadatak/demo_clinic/.env
ExecStart=/home/eyadatak/demo_clinic/.venv/bin/gunicorn \
    --workers 3 \
    --bind 127.0.0.1:8000 \
    --access-logfile - \
    --error-logfile - \
    clinic_system.wsgi:application

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable + start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable eyadatak
sudo systemctl start eyadatak
sudo systemctl status eyadatak       # should show: active (running)
```

If the status shows `failed`, see the last 50 lines of logs:

```bash
sudo journalctl -u eyadatak -n 50 --no-pager
```

## 11. Configure nginx as a reverse proxy

```bash
sudo nano /etc/nginx/sites-available/eyadatak
```

Paste:

```nginx
server {
    listen 80;
    server_name <droplet-ip> <your-domain> www.<your-domain>;

    # Allow large attachment uploads (10 MB ceiling — the visit-attachment
    # form caps at 2 images per visit, but Pillow + raw phone shots can
    # exceed Django's default).
    client_max_body_size 10M;

    # Static files served directly by nginx (faster than Django/whitenoise).
    location /static/ {
        alias /home/eyadatak/demo_clinic/staticfiles/;
        expires 30d;
        access_log off;
    }

    # Uploaded attachments.
    location /media/ {
        alias /home/eyadatak/demo_clinic/media/;
        expires 30d;
        access_log off;
    }

    # Everything else → gunicorn.
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_read_timeout 60s;
    }
}
```

Enable the site, disable the default, and reload:

```bash
sudo ln -s /etc/nginx/sites-available/eyadatak /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t                  # syntax check, must say "test is successful"
sudo systemctl reload nginx
```

## 12. First test from your laptop

Visit `http://<droplet-ip>/patients/login/` in your browser. The login page
should load, fully styled.

Smoke-test the new endpoints:

- `http://<droplet-ip>/healthz` → JSON
- `http://<droplet-ip>/manifest.webmanifest` → JSON manifest
- `http://<droplet-ip>/service-worker.js` → JavaScript
- `http://<droplet-ip>/admin/` → login form

Log in as the superuser you created in step 8.

## 13. Point your domain at the droplet (optional but recommended)

At your registrar (Namecheap / Cloudflare / etc.), set DNS records:

| Type | Host | Value             | TTL  |
|------|------|-------------------|------|
| A    | @    | `<droplet-ip>`    | 600  |
| A    | www  | `<droplet-ip>`    | 600  |

Wait 5–30 minutes for propagation. Then `http://<your-domain>/` should
load identically to `http://<droplet-ip>/`.

## 14. (Next stage) Add HTTPS with Let's Encrypt

Once you have DNS pointing at the droplet **and** the HTTP version working
end-to-end, certbot is one command:

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <your-domain> -d www.<your-domain>
```

Certbot edits the nginx config in place to add the HTTPS server block,
sets up auto-renewal via systemd, and offers to redirect HTTP → HTTPS.

After it finishes, **switch the `.env` to TLS-aware mode**:

```
ALLOWED_HOSTS=<your-domain>,www.<your-domain>
CSRF_TRUSTED_ORIGINS=https://<your-domain>,https://www.<your-domain>
FORCE_SSL=True
USE_PROXY_SSL_HEADER=True
```

Restart Django:

```bash
sudo systemctl restart eyadatak
```

Visit `https://<your-domain>/` — should load with a green lock.

---

## Common errors & fixes

### `502 Bad Gateway` from nginx

Gunicorn isn't running, or it's not listening on `127.0.0.1:8000`.

```bash
sudo systemctl status eyadatak
sudo journalctl -u eyadatak -n 50 --no-pager
```

### `400 Bad Request` from Django

Your `ALLOWED_HOSTS` doesn't include the domain you're hitting. Open
`.env`, add it, restart:

```bash
sudo systemctl restart eyadatak
```

### Static files (CSS/icons) missing

Either you forgot `python manage.py collectstatic --noinput`, or the
nginx `alias` path is wrong. Verify:

```bash
ls /home/eyadatak/demo_clinic/staticfiles/admin/  # should list files
```

### CSRF verification failed on form submit

`CSRF_TRUSTED_ORIGINS` is missing the scheme+host you're hitting. For
HTTP-only stage, all entries must start with `http://`. Restart Django
after editing.

### Browser keeps forcing HTTPS even after disabling FORCE_SSL

Cached HSTS from a previous test. Clear it: `chrome://net-internals/#hsts`
→ "Delete domain security policies" → enter your domain → Delete.

Also unregister the service worker (DevTools → Application → Service Workers
→ Unregister).

### `django.db.utils.OperationalError: no such column: clinic.specialty_type`

You forgot to run `python manage.py migrate` after pulling the latest
code. The migration files (`0003`–`0006`) define the new columns.

---

## Updating the deployment after pushing new code

The release loop is three commands once everything's wired up:

```bash
ssh eyadatak@<droplet-ip>
cd ~/demo_clinic
git pull
source .venv/bin/activate
pip install -r requirements.txt           # only when deps changed
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart eyadatak
```

Wrap that in a `deploy.sh` script if you find yourself repeating it.
