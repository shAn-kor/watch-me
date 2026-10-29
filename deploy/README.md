# Deploy runbook (ADR-0027)

One image (`api` + `worker` + built SPA), one volume `/data` (SQLite + media), Caddy in front for TLS.
Host: Oracle Cloud Always Free A1 (arm64). Run all commands from the repo root.

| Piece     | Where                                                                                                                                                                                                                           |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Image     | `Dockerfile` (node 22 + pnpm build, uv locked install, python 3.12 slim + ffmpeg, user `watchme` uid 10001)                                                                                                                     |
| Processes | `deploy/start.sh`: `alembic upgrade head`, then `uvicorn app.main:create_app --factory` and `python -m app.worker`. If one dies, the script stops the other and exits non-zero; Docker restarts the container. `tini` is PID 1. |
| Proxy     | `deploy/Caddyfile`: automatic HTTPS, `request_body max_size 220MiB` (01 section 5.3 needs at least 210 MiB), `/healthz` active check                                                                                            |
| Stack     | `docker-compose.yml`: `app`, `caddy`, volumes `watchme-data`, `caddy-data`, `caddy-config`                                                                                                                                      |
| Settings  | `deploy/settings.example` lists every field of `Settings` in `backend/app/config.py`                                                                                                                                            |

## Before you start

- VM: Ubuntu arm64 with Docker + compose plugin. Open ports 80, 443 (TCP) and 443 (UDP) in the Oracle security list and the VM firewall.
- DNS: an A record for your host name pointing at the VM public IP. Caddy cannot get a certificate without it.
- Idle A1 VMs can be reclaimed (ADR-0027). Keep some load or check the VM weekly.

## Build

On an arm64 machine (the VM itself, or an Apple Silicon Mac):

```sh
docker build --platform linux/arm64 -t watch-me:latest .
```

On an x86 machine use `docker buildx build --platform linux/arm64 --load -t watch-me:latest .` (needs QEMU; slow).

## Push or transfer

No registry (simplest):

```sh
docker save watch-me:latest | gzip > watch-me.tar.gz
scp watch-me.tar.gz docker-compose.yml ubuntu@VM:~/watch-me/
ssh ubuntu@VM 'cd ~/watch-me && gunzip -c watch-me.tar.gz | docker load'
```

Also copy `deploy/Caddyfile` to `~/watch-me/deploy/Caddyfile`.
With a registry: `docker tag` + `docker push`, then change `image:` in the compose file and `docker compose pull`.

## First run

```sh
cd ~/watch-me
cp deploy/settings.example deploy/settings   # on the VM; file is git-ignored
chmod 600 deploy/settings
$EDITOR deploy/settings                      # set SITE_ADDRESS, PUBLIC_BASE_URL, SECRET_KEY, IP_HASH_KEY, seed values
docker compose --env-file deploy/settings up -d
docker compose --env-file deploy/settings ps          # app should become "healthy"
curl -fsS https://YOUR_HOST/healthz
```

`SECRET_KEY` must be at least 32 bytes and `COOKIE_SECURE` must stay `true` with `APP_ENV=prod`. Real secrets stay in `deploy/settings` on the VM only. Keep AI adapters on `mock`/`rules` until `AI_API_KEY` is set.

The image pre-creates `/data` owned by uid 10001, and a new named volume copies that ownership, so no chown is needed. If you bind-mount a host folder instead, run `sudo chown 10001:10001 <folder>`.

## Seed

The seed tool creates one org, one staff member and one volunteer. It is safe to run again.

```sh
docker compose --env-file deploy/settings exec app python -m tools.seed
```

Then delete `SEED_STAFF_PASSWORD` and `SEED_VOLUNTEER_PASSWORD` from `deploy/settings` and run `docker compose --env-file deploy/settings up -d` again.

## Upgrade

```sh
# load or pull the new image, then:
docker compose --env-file deploy/settings up -d
```

Migrations run at start. Take a backup first (below). To roll back, re-tag the previous image and run `up -d`; a migration that already ran is not undone automatically.

## Backup

R1 has no automatic backup (02). A manual one must follow the rules: keep at most 30 days, and a dog delete must be honored after a restore (re-run deletes made since the backup).

```sh
mkdir -p ~/backups && ts=$(date +%Y%m%d-%H%M%S)
# consistent SQLite copy while the app runs (WAL safe)
docker compose --env-file deploy/settings exec -T app python -c \
  "import sqlite3; s=sqlite3.connect('/data/watchme.db'); d=sqlite3.connect('/data/backup.db'); s.backup(d); d.close()"
docker compose --env-file deploy/settings cp app:/data/backup.db ~/backups/watchme-$ts.db
docker compose --env-file deploy/settings exec -T app rm /data/backup.db
# media
docker run --rm -v watch-me_watchme-data:/data:ro -v ~/backups:/out alpine \
  tar czf /out/storage-$ts.tgz -C /data storage
find ~/backups -type f -mtime +30 -delete
```

The volume name is `<project>_watchme-data`; check it with `docker volume ls`.

Restore: `docker compose --env-file deploy/settings down`, copy the `.db` back to `/data/watchme.db` (and delete `watchme.db-wal` / `-shm`) and untar `storage`, then `up -d`.

## Logs and checks

```sh
docker compose --env-file deploy/settings logs -f app      # api + worker, one stream
docker compose --env-file deploy/settings logs -f caddy
docker compose --env-file deploy/settings ps               # health state
curl -fsS https://YOUR_HOST/healthz
```

Admin metrics: `GET /api/admin/metrics` (staff login required).

## Local smoke test without TLS

Set `SITE_ADDRESS=:80` and `PUBLIC_BASE_URL=http://localhost` in `deploy/settings`. Cookies need `COOKIE_SECURE=false` and `APP_ENV=dev` for plain HTTP.
