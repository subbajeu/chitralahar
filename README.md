# Chitralahar — Photography Portfolio CMS

An elegant, minimal-light CMS for a photography portfolio. Upload and manage
photos, write blog posts in Markdown, and edit your About page — all from a
clean admin panel. Built with Flask + SQLite + Pillow. No build step, no Node,
minimal dependencies.

*Free software under the [GNU GPL v3](LICENSE).*

```
chitralahar/
├── run.py                 # entry point
├── requirements.txt
├── instance/              # created at runtime: SQLite db + session secret
└── chitralahar/
    ├── __init__.py        # app factory (auto-creates db on first run)
    ├── config.py          # settings (db path, upload limits, image sizes)
    ├── schema.sql         # database schema
    ├── db.py              # connection + seeding helpers
    ├── images.py          # Pillow: orientation, display + thumbnail JPEGs
    ├── utils.py           # markdown rendering, slugs, dates
    ├── auth.py            # first-run setup, login/logout
    ├── public.py          # gallery, photo, blog, about (public site)
    ├── admin.py           # admin CRUD + markdown preview
    ├── static/
    │   ├── css/           # style.css (public) + admin.css
    │   ├── js/            # main.js (lightbox) + admin.js
    │   └── uploads/       # photos/ thumbs/ misc/  (your media lives here)
    └── templates/         # public/ and admin/ Jinja templates
```

## Quick start

```bash
# 1. Create a virtual environment and install dependencies
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# 2. Run
./.venv/bin/python run.py

# 3. Open the site and create your admin account
#    Site:  http://127.0.0.1:5050
#    Admin: http://127.0.0.1:5050/admin   (first visit -> account setup)
```

The database and folders are created automatically on first launch. The very
first visit to `/admin` walks you through creating your administrator account —
there is no default password.

> **Port note:** macOS reserves port 5000 for AirPlay Receiver, so Chitralahar uses
> **5050** by default. Change it with `PORT=8000 ./.venv/bin/python run.py`.

## Using the CMS

Sign in at `/admin`. The sidebar gives you:

- **Dashboard** — counts and quick links.
- **Home page** — control what the landing page shows: a custom **heading** and
  **intro**, an optional wide **hero image**, and which photos fill the gallery —
  **all** of them, **featured only** (the ones you star ★), or a **single category**.
- **Photos** — drag-and-drop (or browse) to upload many images at once (and
  optionally assign the whole batch to a category/subcategory — and **tags** — as you
  upload). Each upload is auto-rotated (EXIF) and saved as a high-quality display image
  plus a gallery thumbnail. Drag tiles to reorder, click ★ to feature, click the
  eye to show/hide, or open a photo to set its title, caption, **category /
  subcategory**, **tags**, and published state. **Click photos to select several**, then drag
  the selection onto a category/subcategory chip — or use the **Assign to** dropdown
  — to file them all at once. New uploads are **published** (visible) right away;
  click the eye to hide any. A collapsible **category tree** in the sidebar filters
  the grid (and doubles as drop targets) so you can browse exactly which photos are
  in each category — it stays tidy no matter how many categories you add.
- **Categories** — a two-level taxonomy. Create categories and, under each,
  subcategories. Rename, reorder by dragging, and **publish/hide** any category
  or subcategory. A photo can sit directly in a category or in a subcategory
  (which keeps it in the parent category too), or be left uncategorized.
  Deleting a category keeps its photos (they become uncategorized); deleting a
  subcategory moves its photos up to the parent. **Drag a subcategory onto another
  category** to move it, or onto the top bar to promote it; **drag a category onto
  another** (drop on its middle) to nest it as a subcategory — or use **Move**.
- **Tags** — add free-form, comma-separated tags to any photo (in its editor or on
  the uploader). Tags appear as chips on the photo page and each links to a
  `/tag/<name>` gallery of everything with that tag. Unused tags clean themselves up.
- **Private client galleries** — every **category and subcategory** has a **Share**
  button: flip it to a **Private album** (hidden from your public site) and you get a
  secret link (`/private/<token>`) with a one-click **Copy**. Share it **with or
  without a passphrase** — blank for an unlisted link, or set one to require it. Put a
  client's photos in that category/subcategory, publish them, and send the link.
  **Allow download** is on by default for private albums, so the client can grab the
  whole album as a **ZIP of full-resolution originals** (public albums have no
  download option).
- **Originals kept** — every upload is stored three ways: the untouched **original**
  (for private downloads), a **display** image (~2200px, what the public site shows),
  and a thumbnail.
- **Client proofing** — viewers of a private album can ♥ their favourite photos;
  you see the picks (count + per-photo hearts) in the admin Photos browser.
- **Contact form & inbox** — the Contact page has a form (honeypot + rate-limited);
  messages land in an admin **Messages** inbox with an unread badge.
- **SEO & feeds** — `sitemap.xml`, `robots.txt`, Open Graph tags (link previews),
  and an RSS feed for the blog. Gallery images use `srcset` for faster loading.
- **EXIF** — camera/lens/exposure details captured on upload; optionally shown on
  public photo pages (Settings → Photo details), with one-click backfill from originals.
- **Backup** — one click in Settings downloads a ZIP of the database + all uploads.
  Password change lives there too. Uploads show a progress bar.
- **Watermark** — optionally overlay a watermark on your **public** images: either
  **text** (pick a **font** and **size**) or your own **image/logo** (with a size %).
  Choose position and opacity. It's applied only to what visitors see — your stored
  originals stay clean, so client downloads from private albums are never watermarked.
  Drop extra `.ttf`/`.otf` fonts into `chitralahar/static/fonts/`. Configure in **Settings**.
- **Blog, About & Contact** — all three use a **full WYSIWYG editor** (headings,
  bold/italic/underline, lists, quotes, links) with an **image button that uploads and
  inserts photos** inline. Blog posts add a cover image, slug, excerpt, and draft/publish;
  About & Contact add an optional portrait/image. Contact also shows your social links.
- **Menu** — manage the public navigation: add items that link to a section, a
  category/subcategory, or any URL; nest items into **dropdowns** (drag a sub-item
  onto another item, or use **Move**); drag to reorder; and publish/hide each item.
- **Templates** — pick one of six looks for the public site (Minimal, Noir,
  Grid, Frame, Editorial, and **Slider**). Switching is instant and changes only the
  appearance — your photos, categories, and content are untouched. The **Slider**
  template opens the home page with a full-width, auto-advancing **slideshow of your
  featured (★) photos** (arrows, dots, and swipe), then your gallery below.
- **Settings** — site title, tagline, your name, and social/contact links
  (Instagram, Twitter/X, Facebook, email) shown in the footer, About, and Contact;
  plus **branding**: upload a **logo** (replaces the title in the header) and a
  **favicon** (the browser-tab icon).

**Publishing.** Categories, subcategories, and individual photos each have a
publish toggle. The public site only shows a photo when the photo *and* its
category *and* its subcategory are all published — so hiding a category hides
everything under it. **New uploads are published by default**; click the eye to
hide any. Private categories never appear publicly regardless. Everything
always stays visible and editable in admin.

The public site has three sections: **Work** (gallery with a click-to-zoom
lightbox; filter by category, then drill into subcategories at
`/category/<slug>` and `/category/<slug>/<subslug>`), **Blog**, and **About**.
It's fully **mobile-friendly** — a tap-to-open menu, touch-friendly controls, and
layouts that reflow on small screens.

### Supported uploads
JPG, PNG, WebP, TIFF, BMP, GIF. Everything is normalized to optimized progressive
JPEG. (HEIC/HEIF from iPhones works too if you install the optional
`pillow-heif` package — see `requirements.txt`.)

## Configuration

Environment variables (all optional — see `.env.example`):

| Variable              | Default            | Purpose                                  |
|-----------------------|--------------------|------------------------------------------|
| `PORT`                | `5050`             | Port to serve on                         |
| `SECRET_KEY`          | auto-generated     | Session signing key (persisted in `instance/.secret_key`) |
| `CHITRALAHAR_DATABASE`      | `instance/chitralahar.db`| SQLite database path                     |
| `CHITRALAHAR_MAX_UPLOAD_MB` | unlimited          | Max upload size per request, in MB (`0`/unset = no limit; a multi-file batch is one request) |
| `CHITRALAHAR_HTTPS`         | off                | Set to `1` when served over HTTPS → session cookie is marked `Secure` |
| `CHITRALAHAR_MAX_IMAGE_PIXELS` | `64000000`      | Reject images whose pixel count exceeds this (decompression-bomb guard) |

Image sizes and JPEG quality live in `chitralahar/config.py`
(`THUMB_SIZE`, `DISPLAY_SIZE`, `JPEG_QUALITY`).

## Backups

Everything you create is in two places — copy them and you've backed up the whole site:

- `instance/chitralahar.db` — all text content (photos metadata, posts, settings)
- `chitralahar/static/uploads/` — the image files: `originals/` (kept full-resolution
  masters), `photos/` (display), `thumbs/`, `misc/` (covers, logo), `wm/` (regenerable cache)

> Keeping originals means storage grows with your full-size files. When deploying,
> copy `static/uploads/` (and any custom `static/fonts/`) to the server too — both
> are git-ignored, so a fresh `git clone` won't include them.

## Notes on security

Chitralahar is built for self-hosting and ships with sensible defaults:

- **Passwords** are hashed with PBKDF2-SHA256. **Admin login and private-album
  passphrases are rate-limited**, and failed attempts are logged (point
  `fail2ban` at the log on a public server).
- **Sessions**: cookies are `HttpOnly` + `SameSite=Lax`, and `Secure` when
  `CHITRALAHAR_HTTPS=1`. State-changing requests also get a same-origin `Origin`
  check as defense-in-depth CSRF (SameSite=Lax already blocks the cross-site POST).
- **Security headers** on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy` (so `/private/<token>` share
  links don't leak via `Referer`), and a `Content-Security-Policy`.
- **Private albums**: images load through an authenticated route that re-checks
  the share token + passphrase (not a guessable public `/static` link), and the
  unlock is bound to the passphrase (changing it re-locks open sessions). Files
  keep unguessable random (UUID) names on disk.
- **Uploads** are always re-encoded through Pillow (an upload can't smuggle a
  script), with a decompression-bomb pixel cap.
- Behind a reverse proxy, `ProxyFix` trusts one hop of `X-Forwarded-Proto/Host/For`
  so HTTPS detection, absolute share links, and rate-limit IPs are correct.

`run.py` is Flask's development server (loopback, debug off by default) — fine for
local use. **To expose the site publicly, run it behind gunicorn + Apache with
HTTPS** (below), set a fixed `SECRET_KEY` and `CHITRALAHAR_HTTPS=1`, and work
through the hardening checklist. For a high-traffic public site you may also add
`Flask-WTF` CSRF tokens on top of the existing SameSite + Origin protections.

## Deploy on Apache

These steps assume **Apache (httpd) is already installed and running** on your
server — check with `httpd -v`. Paths below are for **Arch Linux** (`/etc/httpd/`);
on Debian/Ubuntu use `/etc/apache2/`, enable modules with
`sudo a2enmod proxy proxy_http headers`, and drop the vhost in `sites-available/`
(`sudo a2ensite chitralahar`). Ready-made config files live in [`deploy/`](deploy/)
— two options, the first recommended (most robust, clean env handling).

### Option A — Apache reverse-proxy → gunicorn (recommended)

```bash
# 1. Put the project on the server and build its venv
sudo mkdir -p /srv/chitralahar && sudo chown $USER /srv/chitralahar
git clone <your-repo> /srv/chitralahar      # or rsync the folder
cd /srv/chitralahar
python -m venv .venv
./.venv/bin/pip install -r requirements.txt          # includes gunicorn

# 2. Let Apache's user own the writable bits (db, secret key, uploads)
mkdir -p instance
sudo chown -R http:http /srv/chitralahar/instance /srv/chitralahar/chitralahar/static/uploads
sudo chmod 700 /srv/chitralahar/instance              # db + secret key stay private

# 3. gunicorn as a service — edit SECRET_KEY (and keep CHITRALAHAR_HTTPS=1) first!
sudo cp deploy/chitralahar.service /etc/systemd/system/
sudoedit /etc/systemd/system/chitralahar.service      # set SECRET_KEY to a long random value
sudo systemctl daemon-reload && sudo systemctl enable --now chitralahar

# 4. Configure the (already-installed) Apache vhost
sudo cp deploy/apache-reverse-proxy.conf /etc/httpd/conf/extra/chitralahar.conf
#    edit ServerName, then in /etc/httpd/conf/httpd.conf make sure these are loaded:
#       LoadModule proxy_module / proxy_http_module / headers_module
#    and add at the end:  Include conf/extra/chitralahar.conf
sudo apachectl configtest && sudo systemctl restart httpd

# 5. HTTPS — REQUIRED for a public site (the admin cookie must not cross HTTP)
#    (install certbot first if you don't have it: sudo pacman -S certbot certbot-apache)
sudo certbot --apache -d photos.example.com
```

Apache serves `/static` (your CSS/JS and *public* photos) directly from disk and
proxies everything else to gunicorn on `127.0.0.1:8000`. The shipped config sends
`X-Forwarded-Proto` so the app knows it's on HTTPS; the systemd unit sets
`CHITRALAHAR_HTTPS=1` so the session cookie is marked `Secure`. (Private-album
images load *through* the app with the passphrase enforced, not via a guessable
`/static` link.)

### Option B — mod_wsgi (runs inside Apache, no gunicorn)

```bash
sudo pacman -S mod_wsgi          # the Apache module only (if not already present; must match system python3)
sudo cp deploy/apache-mod-wsgi.conf /etc/httpd/conf/extra/chitralahar.conf
# In httpd.conf:  LoadModule wsgi_module modules/mod_wsgi.so + Include the file
```

Build the venv with the **system** `python3` (must match mod_wsgi's Python — and
note that on a rolling distro like Arch a `python3` upgrade means rebuilding both
`mod_wsgi` and the venv). mod_wsgi doesn't read `SetEnv`/systemd env, but
`SECRET_KEY` is fine left unset (the app creates `instance/.secret_key`) and the
database path defaults correctly. For HTTPS, set it at the top of `wsgi.py`:
`import os; os.environ["CHITRALAHAR_HTTPS"] = "1"`. For multiple instances, give
each a distinct `WSGIDaemonProcess` name with its own `python-home`/`python-path`.

> **gunicorn vs mod_wsgi:** prefer **Option A (gunicorn)** if you run several
> instances or want each app to restart/log independently and survive Python
> upgrades. Option B has fewer moving parts (no port, no service) but is more
> fragile on rolling distros and mixes env/logs into Apache.

### Custom install location

The project doesn't have to live in `/srv/chitralahar`. The **project root** is the
folder containing `wsgi.py`; the inner `chitralahar/` is the Python package, and the
static files are at `<root>/chitralahar/static`. For example, with root
`/srv/http/example.net/html/chitralahar`, use:

- `WorkingDirectory` (and `<root>/.venv` for the venv) → that root
- `Alias /static` → `/srv/http/example.net/html/chitralahar/chitralahar/static`
- `CHITRALAHAR_DATABASE` → `<root>/instance/chitralahar.db`

Make sure the `http` user can **traverse every parent folder** (`chmod o+x` up the
chain). If the root sits **inside Apache's web root** (e.g. under `/srv/http/`), the
vhost must proxy every request so the raw `.py` source is never served as a static
file — better still, keep the code *outside* the web root.

### Running more than one instance

One instance = **its own folder + venv + gunicorn port + systemd service + Apache
vhost**. To add another, copy the pattern and change only these — each folder keeps
its own database and uploads automatically:

| Thing             | Instance 1         | Instance 2          |
|-------------------|--------------------|---------------------|
| Folder (root)     | `/srv/site-a`      | `/srv/site-b`       |
| gunicorn `--bind` | `127.0.0.1:8000`   | `127.0.0.1:8001`    |
| systemd service   | `chitralahar-a`    | `chitralahar-b`     |
| `ServerName`      | `a.example.net`    | `b.example.net`     |

Two `*:80` vhosts can't share a `ServerName`. With a single (e.g. DDNS) hostname,
separate instances by **port** (`Listen 8080` + `<VirtualHost *:8080>`, reached at
`host:8080`) or by **subdomain** if your DNS supports it.

### Troubleshooting

- **`status=203/EXEC` — gunicorn won't start.** systemd can't execute the binary —
  almost always a `.venv` **copied from another machine** (e.g. macOS → Linux): its
  shebang points at a Python that isn't there. Never copy `.venv`; rebuild it on the
  server: `rm -rf .venv && python -m venv .venv && ./.venv/bin/pip install -r
  requirements.txt`, then `sudo systemctl restart chitralahar`. To see the real
  error, run it by hand: `sudo -u http ./.venv/bin/gunicorn --bind 127.0.0.1:8000 wsgi:application`.
- **The page shows raw Python source.** Apache is serving files instead of proxying —
  usually the app is down (fix gunicorn first), or the proxy modules aren't loaded
  (`httpd -M | grep -E 'proxy|headers'`), or the vhost `ServerName` doesn't match.
  Check the app directly with `curl -I http://127.0.0.1:8000/`.
- **Can't stay logged in.** You set `CHITRALAHAR_HTTPS=1` but are visiting over plain
  `http://`, so the session cookie is HTTPS-only. Switch to HTTPS (certbot), or
  comment out `CHITRALAHAR_HTTPS` until then.

### Production hardening checklist

- [ ] **`SECRET_KEY`** — set a fixed long random value in the systemd unit
  (`python -c "import secrets; print(secrets.token_hex(32))"`). Otherwise it's
  auto-generated into `instance/.secret_key` (created `0600`), which must persist
  and be writable.
- [ ] **HTTPS** — run `certbot`, and keep `CHITRALAHAR_HTTPS=1` (set in the unit)
  so the session cookie is `Secure`. The Apache config forwards `X-Forwarded-Proto`.
- [ ] **Permissions** — `instance/` (db + secret + WAL files) and
  `chitralahar/static/uploads/` writable by the `http` user; `chmod 700 instance`.
  Everything else can be read-only.
- [ ] **Uploads** — by default there is **no size limit** (so large batch uploads
  work). On a public server set `CHITRALAHAR_MAX_UPLOAD_MB` and the matching
  Apache `LimitRequestBody` (both shipped as unlimited). Pixel-bomb images are
  always rejected via `CHITRALAHAR_MAX_IMAGE_PIXELS`.
- [ ] **Run `wsgi:application` only** — never expose `run.py` (dev server). Keep
  `FLASK_DEBUG` unset.
- [ ] **One worker for first run** — `--preload` (gunicorn) or a single mod_wsgi
  process so the one-time DB init/migration doesn't race. SQLite uses WAL +
  busy-timeout, so multiple workers are fine afterwards.
- [ ] **Reduce version disclosure** — in `httpd.conf`: `ServerTokens Prod` and
  `ServerSignature Off`.
- [ ] **fail2ban** (optional) — Chitralahar logs failed admin logins and private
  passphrase attempts; add a filter to ban brute-forcers.
- [ ] **Back up** `instance/chitralahar.db` (+ `-wal`/`-shm`) and
  `chitralahar/static/uploads/` together.

## License

Chitralahar is free software, released under the **GNU General Public License
v3.0** — see [`LICENSE`](LICENSE). You may use, study, share, and modify it; if
you distribute a modified version, it must remain GPLv3.

> **Running it as a public web service?** Because Chitralahar is a network
> application, you may prefer the **GNU AGPL v3** instead — it additionally
> requires anyone who runs a *modified* version as a hosted service to offer
> their source to its users (closing the "SaaS loophole"). To switch, replace
> `LICENSE` with the AGPLv3 text from <https://www.gnu.org/licenses/agpl-3.0.txt>
> and update this section. It imposes no extra burden on a normal self-hoster.

Copyright © Chitralahar contributors. This program comes with ABSOLUTELY NO
WARRANTY, to the extent permitted by law.
