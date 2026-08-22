# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

`homelab-cluster` is the **infrastructure-as-config** source of truth for a 6-node home cluster (two x86 PCs + four Raspberry Pi 5s), orchestrated with **Docker Engine + Docker Compose v2 only** (explicitly no Kubernetes, no Docker Swarm). This is not an application monorepo — it's Docker Compose stacks, nginx/DNS config, shell scripts, and a shared top-level `services/` directory of small FastAPI microservices. There is no CI, no test suite. The repo **is** under git and pushed to `github.com/impalah/homelab-cluster` (first real commit landed 2026-08-02) — but this checkout is still a separate copy from what's actually running in each node's `/srv/homelab/<node>/`: local edits are not live until deployed (see "Connecting to cluster nodes" below), and the reverse — never assume the checkout matches deployed reality without checking; multiple real deploys this repo's history have found the two had quietly diverged (see the `pi-dns` path gotcha below).

**Services are built and pushed from `services/<name>/` (`make build`), never built by the consuming node's `docker-compose.yml`.** Each node's compose file just does `image: registry.home.arpa/<name>:latest` and pulls — see "The three FastAPI microservices" below and `docs/05-instalacion-retaco.md` section 5.3 for the private registry.

Language note: all docs, comments, and commit-worthy prose in this repo are in **Spanish**. Match that when editing existing files (READMEs, docs/, inline comments); code identifiers stay in English as they already are.

## Repository layout

```
homelab-cluster/
├── docs/               ← Numbered install/ops guides, 01 through 22, ordered by real install sequence (docs/01-topologia.md has the full index) — read before touching a node
├── services/           ← apikey-service, markitdown-service, whisper-service source — built/pushed from
│                          here (make build), NOT from any node's docker-compose.yml (see below)
├── shared/
│   ├── env/            ← <node>.env.example templates (never real secrets)
│   ├── scripts/        ← Cross-node operational scripts (see below)
│   └── dns/            ← DNS record table + router DHCP notes
├── ryzen/              ← GPU node: ollama, vllm, open-webui, whisper-service, comfyui (+ separate observability stack)
├── retaco/             ← postgres-main (shared, multi-tenant), qdrant, n8n-main, registry (private Docker registry)
├── pi-dns/             ← Unbound + Pi-hole + nginx reverse proxy + apikey-service
├── pi-obs/             ← otel-collector, prometheus, grafana, loki, tempo
├── pi-sonar/           ← SonarQube (DB lives in retaco's postgres-main)
└── pi-utils/           ← rsshub, markitdown-service, n8n-aux, portainer, vaultwarden
```

Each node directory follows the same shape: `docker-compose.yml`, `.env.example`, `README.md`, `config/` (bind-mounted, mostly static config), `data/` (bind-mounted runtime state, gitignored-equivalent). Node directories do **not** have their own `services/` anymore — `apikey-service`/`markitdown-service`/`whisper-service` moved to the top-level `services/` once the private registry (`registry.home.arpa`, on `retaco`) took over distributing their images.

## Architecture — read this before editing any compose file

- **One Docker Compose stack per physical node**, each with its own bridge network (`<node>-net`) and no shared Docker network across hosts — inter-node traffic goes over the real LAN using `*.home.arpa` hostnames (via Pi-hole/Unbound) or raw IPs, never Docker container names, **except** within a single node's compose file.
- **Fixed node IPs** (documented in `docs/02-plan-ip-y-dns.md` and the root `README.md`): ryzen `.150`, retaco `.174`, pi-dns `.170`, pi-obs `.171`, pi-sonar `.172`, pi-utils `.173`, pinchi `.175`. `pi-dns`'s internal Docker network additionally uses fixed IPs in `172.20.0.0/24` (see `pi-dns/docker-compose.yml`) because Unbound/Pi-hole/nginx/apikey-service reference each other by IP, not name, in some configs.
- **`pinchi` (192.168.1.175, x86_64 PC) is the newest node** (added 2026-08-22) — base system only (`docs/30-instalacion-pinchi.md`): static IP, Docker Engine installed, no services deployed yet, no `pinchi/docker-compose.yml`. Its SSH gotcha, real and worth knowing before touching any node's `sshd_config`: an `/etc/ssh/sshd_config.d/50-cloud-init.conf` drop-in set `PasswordAuthentication yes` and was processed *before* the main `sshd_config`'s own directive (`Include` runs mid-file, and OpenSSH keeps the first value seen per keyword) — a plain `sed` on `sshd_config` silently had no effect until overridden with a same-named-scheme drop-in (`00-homelab.conf`, sorts before `50-cloud-init.conf`). Don't assume `docs/03`'s `sed`-based `PasswordAuthentication no` recipe works unmodified on a node provisioned via cloud-init — check `/etc/ssh/sshd_config.d/` first.
- **pi-dns is the front door.** nginx there terminates TLS (self-signed CA, 10-year validity — `pi-dns/config/nginx/generate-ca.sh` / `generate-cert.sh`, see `docs/15-ca-interna.md`) and reverse-proxies every `*.home.arpa` hostname to the right node:port. New exposed services need: an nginx server block, a DNS record (`shared/dns/dns-records.md` + added manually in Pi-hole), and a row in the root `README.md` service table.
- **apikey-service** (`services/apikey-service/`, runs on `pi-dns`; FastAPI + SQLAlchemy async + Postgres) issues/validates API keys used by nginx's `auth_request` to protect services with no auth of their own (e.g. Ollama). See `docs/06-instalacion-pi1-dns.md`.
- **`pi-dns` is also the Tailscale subnet router** (`tailscale` container, `network_mode: host`, `docs/18-tailscale.md`) — authenticated remote access to the whole `192.168.1.0/24` LAN from outside, with `*.home.arpa` resolving over the tunnel via Tailscale's Split DNS (nameserver `192.168.1.170` restricted to domain `home.arpa`, configured in the Tailscale admin console, not in this repo). Needs `TS_USERSPACE=false` + `/dev/net/tun` under `devices:` (not `volumes:`, or it silently falls back to non-routable userspace networking) + kernel netfilter modules pre-loaded on the **host** (`ip_tables`, `iptable_filter`/`nat`, `ip6` equivalents — the container can't `modprobe` them itself without `CAP_SYS_MODULE`, deliberately not granted). Interactive `tailscale up` login (no `TS_AUTHKEY`) does not work in this container — `containerboot` kills the login after ~60s and Docker's restart regenerates a new node identity/login URL each time; always use a reusable, non-ephemeral `TS_AUTHKEY`.
- **`ryzen` ("mole") supports Wake-on-LAN** (`docs/19-wake-on-lan.md`) — it's the only node meant to be powered off when idle (GPU desktop, not always-on infra). NIC (`enp6s0`, Intel `igc`) confirmed to support and have `Wake-on: g` active, persisted explicitly via `nmcli connection modify ... 802-3-ethernet.wake-on-lan magic` (don't rely on the driver default alone). Wake it from any other node with `shared/scripts/wake-mole.sh [nodo]` (defaults to `pi-utils`, needs `wakeonlan` installed there — already done) — must run from a node OTHER than `mole` itself (it's off), so the script is deployed as a local copy on all 5 always-on nodes' `/srv/homelab/shared/scripts/` (same `rsync`-per-node convention as the rest of `shared/`, `docs/03-instalacion-base-ubuntu-raspi.md`), not just in this checkout. Full poweroff (S5) is the state used (not suspend/hibernate — NVIDIA GPU resume from S3/S4 is unreliable on Linux for this node's dual-GPU setup, RTX 5070 + RTX 3070), confirmed working end-to-end with a real poweroff + magic packet test. Motherboard is an ASUS ROG STRIX B550-XE — its WoL toggle ("Power On By PCI-E/PCI") is hidden/disabled by a separate "ErP Ready" BIOS setting under `Advanced → APM Configuration`; had to disable ErP first before the WoL option even showed up. See `docs/19-wake-on-lan.md`.
- **`ketekasko` (192.168.1.180) is a UGREEN NASync DH2300 NAS on the LAN, NOT part of this repo's Docker cluster** — no `docker-compose.yml`, no node directory, runs its own OS (UGOS Pro). `ketekasko.home.arpa` is a direct DNS alias (same pattern as `postgresql.home.arpa`), bypassing nginx since UGOS Pro serves its own HTTPS on `:9443` with its own cert. NFSv4 required an SSH-side workaround the GUI doesn't expose: edit `/etc/nfs.conf` (`[nfsd]` section, standard `nfs-utils`) AND `/etc/nfs.json` (UGOS-specific, `"maximumNFSProtocol"` — the GUI regenerates `nfs.conf` from this on "Apply", so editing only one reverts on next GUI save) — but even with `nfsd` negotiating v4 (`/proc/fs/nfsd/versions` shows `+4`), actual v4 mounts fail (`No such file or directory`) because UGOS Pro's GUI-generated `/etc/exports` doesn't expose an NFSv4 pseudo-root (`fsid=0`); NFSv3 on the same export works fine (confirmed with `no_root_squash` — root writes as root). Client mounts use NFSv3 (`mount -t nfs -o vers=3`) against the **real** export path (`showmount -e <nas>`, not the shared-folder name — e.g. `/volume1/nfs-data`, not `/nfs-data`) as a result — see `docs/21-configuracion-nas-ugreen.md`.
- **postgres-main lives on retaco** and is multi-tenant: every consumer (n8n, SonarQube, future projects) gets its own isolated DB + role via `shared/scripts/create-postgres-db.sh` — never share a role across projects. It's deliberately published to the LAN (`5432:5432`) because pi-obs's postgres-exporter and pi-sonar's SonarQube reach it cross-node; isolation is by password/role, not network.
- **The `services/` images (`apikey-service`/`markitdown-service`/`whisper-service`) never carry the watchtower auto-update label** (`com.centurylinklabs.watchtower.enable=true`) — only stateless upstream images do, even now that they're pulled from `registry.home.arpa` instead of built per-node. Stateful services (databases, Pi-hole, nginx, SonarQube) are also deliberately excluded from auto-update; see `docs/16-mantenimiento-actualizaciones.md`.
- **Bind-mount ownership is UID-sensitive and inconsistent by design** — n8n and SonarQube containers run as UID 1000, Grafana as 472, Postgres as 70, Prometheus as 65534, Loki as 10001. `shared/scripts/prepare-host.sh` chowns the generic node directory first, then re-chowns specific data subdirectories for the UIDs above. If you add a new stateful service, add its own `chown` line — don't rely on the generic one. Re-running `prepare-host.sh` against a node that already has real data is only safe for directories that already have an explicit chown (see `docs/13-troubleshooting.md`).
- **ryzen has two independent compose stacks** — `docker-compose.yml` (GPU/AI: ollama, vllm, open-webui, whisper-service, comfyui) and `docker-compose.observability.yml` (host-level, no `.env`) — so the heavy GPU stack can be stopped without losing node-exporter/cadvisor. Commands without `-f` only touch the first.
- **ryzen's two GPUs are each shared by a pair of services that must never run simultaneously.** GPU 0 (RTX 5070, 12GB — also drives the physical display, so real free VRAM is less than nominal) alternates `ollama`/`vllm` via `ryzen/switch-llm-backend.sh`; GPU 1 (RTX 3070, 8GB) alternates `whisper-service`/`comfyui` via `ryzen/switch-gpu1-backend.sh`. Never `docker compose up -d <service>` either pair member directly — always go through the switch script, or you'll get GPU OOM / VRAM contention. See `docs/07-instalacion-ryzen.md`.
- Every service that has a healthcheck is wired with `depends_on: condition: service_healthy` where startup order matters (e.g. nginx waits on pi-hole and apikey-service).

## Connecting to cluster nodes

**`ryzen` (alias `mole`) is very likely the machine this assistant is already running on.** If the current working directory's real path resolves outside any container/VM and `hostname`/the local IP matches `192.168.1.150`, you're already *on* `ryzen` — no SSH needed, run `docker`/`docker compose`/file edits directly, and `/srv/homelab/ryzen/` is a real local path, not a remote one. Don't reflexively `ssh ryzen` or treat it like the other five nodes. It's also the only node normally powered off when idle (`docs/19-wake-on-lan.md`) — if it's unreachable, it's probably just asleep, wake it from another node with `shared/scripts/wake-mole.sh`, don't assume a network/config problem.

**The other five nodes need SSH, with a distinct dedicated user per node (no shared/generic username, no root login):**

| Node | IP | SSH user |
|---|---|---|
| `retaco` | 192.168.1.174 | `u-data` |
| `pi-dns` | 192.168.1.170 | `u-dns` |
| `pi-obs` | 192.168.1.171 | `u-obs` |
| `pi-sonar` | 192.168.1.172 | `u-sonar` |
| `pi-utils` | 192.168.1.173 | `u-utils` |
| `pinchi` | 192.168.1.175 | `u-forge` |

(Full table with SSH groups: `docs/01-topologia.md`, section "Acceso SSH a los nodos".) Key-based auth is already set up for this workstation — a bare `ssh u-<x>@192.168.1.17x` should just work; if it prompts for a password or is refused, the username is wrong before assuming the key is missing (this has happened — don't guess a username pattern for a node not in the table above without confirming first). Each user can write to their own `/srv/homelab/<node>/` tree without `sudo`; `sudo` is only needed for OS-level operations, root-owned config subtrees (e.g. `pi-dns`'s nginx config, see gotcha below), or bind-mounted data owned by a specific container UID (see the "Bind-mount ownership" bullet further down).

**Deploying a changed file to a node — standard pattern, works everywhere, sidesteps permission surprises:**
```bash
rsync -av <local-file> u-<x>@192.168.1.17x:/tmp/<basename>
ssh u-<x>@192.168.1.17x "sudo cp /tmp/<basename> <real-destination-path> && rm /tmp/<basename>"
```
Land in `/tmp` first, then `sudo cp` into place, rather than `rsync`/`scp` straight to the final path — this also sidesteps the single-file-bind-mount inode-swap gotcha already noted below (`cp` overwriting an existing file preserves the inode; `rsync`/`scp` rename-into-place and orphan it). For paths the SSH user already owns outright (most of `/srv/homelab/<node>/`), a direct `rsync -av <local-file> u-<x>@192.168.1.17x:/srv/homelab/<node>/<path>` is fine and one step shorter — reach for the `/tmp` + `sudo cp` version whenever the destination might be root- or container-UID-owned, or whenever unsure.

⚠️ **On `pi-dns`, the real deployed path for nginx does not mirror this repo's own directory layout.** The repo versions nginx config under `pi-dns/config/nginx/`, but `pi-dns/docker-compose.yml`'s actual bind mounts on the host point at `/srv/homelab/pi-dns/nginx/conf/` (configs: `nginx.conf`, `proxy-common.conf`, `apikey-auth.conf`) and `/srv/homelab/pi-dns/nginx/html/` (the static `index.home.arpa` site + `icons/`) — **not** `/srv/homelab/pi-dns/config/nginx/...`. Deploying to the repo-shaped path silently no-ops (nginx keeps serving the old file, `nginx -s reload` "succeeds" against nothing) — this has caused real, confusing 404s more than once. Before deploying *any* config to *any* node, confirm the real bind-mount source in that node's `docker-compose.yml` (`grep -A3 '<service>:' <node>/docker-compose.yml` for the `volumes:` block) rather than assuming it matches the repo's folder name — `pi-dns` is the one confirmed instance of this drift, but treat it as a reason to verify, not a promise every other node matches its own repo layout either.

After deploying config to nginx specifically, validate before reloading:
```bash
ssh u-dns@192.168.1.170 "cd /srv/homelab/pi-dns && docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload"
```

## Common commands

There is no build/lint/test pipeline — validate changes by running the affected stack. On the deployment host, each node's config lives at `/srv/homelab/<node>/`, which is what all scripts below assume.

```bash
# First-time node setup (creates + chowns bind-mount dirs)
sudo bash shared/scripts/prepare-host.sh <node>

# Bring a stack up (from within /srv/homelab/<node>/)
docker compose up -d
docker compose logs -f <service>
docker compose restart <service>

# ryzen's second stack needs -f explicitly:
docker compose -f docker-compose.observability.yml up -d

# ryzen GPU alternation — never start these services directly, always via the switch script
bash ryzen/switch-llm-backend.sh ollama|vllm            # GPU 0
bash ryzen/switch-gpu1-backend.sh whisper-service|comfyui # GPU 1

# Pull + recreate + prune for one node (or ryzen's non-default compose file)
bash shared/scripts/update-stack.sh <node> [docker-compose.observability.yml]

# HTTP + docker-health checks for one node or all (needs SSH for 'all')
bash shared/scripts/check-health.sh <node|all>

# Add an isolated Postgres DB+role to postgres-main (retaco)
bash shared/scripts/create-postgres-db.sh <container> <admin-user> <new-db> <new-user> [password]

# Postgres backup/restore (gzip pg_dump)
bash shared/scripts/backup-postgres.sh <node> <container> <db-name>
bash shared/scripts/restore-postgres.sh <node> <container> <db-name> <dump-file>

# Close/reopen direct IP:port access to nginx-fronted services (bypasses apikey-service otherwise)
bash shared/scripts/setup-firewall.sh <node|all>            # once per node, installs prereqs
bash shared/scripts/toggle-direct-access.sh <node|all> off   # restrict to pi-dns only
bash shared/scripts/toggle-direct-access.sh <node|all> on    # reopen to the LAN
```

Plain `ufw deny <port>` does NOT block Docker-published ports (Docker's DNAT rules bypass the INPUT chain where ufw lives) — `toggle-direct-access.sh` manages the `DOCKER-USER` iptables chain directly instead. See `docs/17-firewall-acceso-directo.md`.

Valid node names throughout every script: `ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils`.

nginx config changes on pi-dns can be validated/applied without a restart:
```bash
docker exec nginx nginx -t
docker exec nginx nginx -s reload
```

### The three FastAPI microservices

`services/apikey-service/`, `services/markitdown-service/`, `services/whisper-service/` (top-level, not under any node directory) — each is a standalone `uv`/hatchling Python project (no monorepo tooling, no shared package). All three have real tooling — each configured independently in its own `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`, not shared between them): `tests/` (pytest, `make test`, `>80%` coverage enforced via `--cov-fail-under=80`), `ruff` (`make lint` / `make format`), `mypy --strict`-ish (`make typecheck`), and SonarQube analysis via `pysonar` (`make sonar` / `make sonar-check`, project keys `apikey-service` / `markitdown-service` / `whisper-service` on `pi-sonar` — `sonar-project.properties`). All `SONAR_*`/service-specific secrets for local dev come from each service's own `.env` (gitignored, copy from `.env.example`) — each `Makefile` deliberately does `-include .env` **without** a blanket `export`, since exporting would leak DB URLs or other settings into `make test`'s subprocess env and override test-isolation defaults set with `os.environ.setdefault(...)`/`monkeypatch`; each target that needs a `.env` value passes it explicitly on that one command line instead (see `sonar:` target). `whisper-service`'s tests never load a real `WhisperModel`/touch CUDA — `/transcribe` is tested by monkeypatching the module-level `_model` in `whisper_service.infrastructure.whisper_model` with a fake object, so the suite runs on any machine without a GPU.

**All three now share the same layered structure** (`apikey-service`'s shape, extended to the other two): `src/<package_name>/main.py` (thin — app factory, `lifespan` if needed, router registration only), `config.py` (pydantic-settings), `schemas.py` (Pydantic request/response models), `dependencies.py` (FastAPI `Depends()` providers), `controllers/` (routers — translate domain exceptions to `HTTPException`, no business logic), `services/` (business rules — no FastAPI, no external-library imports, raise plain domain exceptions like `UnsupportedFormatError`/`ModelNotLoadedError`), and either `repositories/` (apikey-service, SQLAlchemy) or `infrastructure/` (markitdown-service/whisper-service — wraps `MarkItDown`/`faster_whisper` respectively, keeps the external library out of the service layer). `whisper-service`'s loaded model lives as module state in `infrastructure/whisper_model.py` (`set_model()`/`get_model()`), not in `main.py`.

**Build/push lives in the Makefile, not in any node's `docker-compose.yml`.** `make build` in `services/<name>/` reads the version from `pyproject.toml`, logs into `registry.home.arpa` (credentials from `.env` — `REGISTRY_USER`/`REGISTRY_PASSWORD`), and pushes both `:<version>` and `:latest`. Consuming nodes only do `image: registry.home.arpa/<name>:latest` + `docker compose pull`/`up -d` — no `build:` block anywhere anymore. `make bump-version` (`PART ?= patch`, override with `PART=minor|major`) bumps `pyproject.toml` via `bump2version`; it's a separate, explicit step, not auto-chained into `build`.

⚠️ **`apikey-service` and `markitdown-service` must be multi-arch** (`linux/amd64,linux/arm64`) — they run on `pi-dns`/`pi-utils`, Raspberry Pi 5s (arm64), while this repo is normally worked on from x86 machines. Their `build` targets use `docker buildx build --platform $(PLATFORMS) --push` (not plain `docker build`, which can't produce multi-platform manifests), with QEMU emulation for the arm64 leg. One-time setup on any build machine: `docker run --privileged --rm tonistiigi/binfmt --install all` + a `docker-container`-driver builder (`docker buildx create --driver docker-container --use`). `whisper-service` stays **amd64-only, plain `docker build`, on purpose** — it needs NVIDIA CUDA, which the Pi's don't have; it only ever runs on `ryzen` (x86).

⚠️ **The `docker-container` buildx driver runs builds in a separate BuildKit container with its own cert store — it does NOT inherit the host's trusted CAs**, even after `update-ca-certificates` on the host. Pushing to `registry.home.arpa` (internal CA, `docs/15-ca-interna.md`) from that builder fails with `x509: certificate signed by unknown authority` until the CA is added inside the `buildx_buildkit_<name>0` container's own `/etc/ssl/certs/ca-certificates.crt` (`docker cp` the CA in, append, `docker restart` the buildkit container — Alpine-based, no `update-ca-certificates` binary, so append the PEM directly). Hit this live building `apikey-service`/`markitdown-service`.

⚠️ **Every node that runs `docker compose pull`/`up -d` for these three services needs the internal CA trusted at the *system* level, not just nginx-side** — `dockerd`'s own TLS verification for `registry.home.arpa` fails otherwise. `pi-dns` and `pi-utils` didn't have it installed even though they're cluster nodes (only `ryzen`/dev machines did) — fix is the same as any device (`docs/15-ca-interna.md`, "Linux (Ubuntu/Debian)" section) **plus a `sudo systemctl restart docker`** afterward (Go's cert pool is read once per daemon lifetime, doesn't pick up a mid-run `update-ca-certificates`). Also needs a one-time `docker login registry.home.arpa` on each node, as whichever OS user runs `docker compose` there (`u-dns`, `u-utils`, etc. — credentials in Vaultwarden, "Docker Registry (registry.home.arpa)").

Port convention: services deliberately avoid `8000` (FastAPI's ubiquitous default) to prevent collisions — e.g. apikey-service uses 8090, whisper-service uses 9800. Follow this when adding a new service.

All Python microservices (now six: the three below plus `crawl4ai-scraper-service`, `epub2pdf-service`, `pdf2chunks-service`) log via `loguru`, not stdlib `logging` directly — but stdlib logging isn't ignored: an `InterceptHandler` (`logging_setup.py`/`core/logging.py`) redirects uvicorn/fastapi/asyncio (plus any service-specific library that logs via stdlib — playwright/crawl4ai, faster_whisper/ctranslate2...) into loguru, so everything ends up through the same sink with the same format. `Settings` carries `log_level`/`log_format` (`Literal["text", "json"]`, code default `"text"`, overridden to `json` in each node's `docker-compose.yml` for production); the stdout sink uses `serialize=settings.log_format == "json"`. `uvicorn.access` (one line per HTTP request, including every Docker healthcheck) is pinned to `WARNING` unless `log_level=DEBUG`, since otherwise it floods Loki with zero-value "GET /health 200" lines every few seconds — see `docs/desarrollo-microservicios-python.md` section 7 for the full pattern. Messages use `{}`-style placeholders (not `%s`). The one exception is `apikey-service`'s `audit_logger` (`logging_setup.py`), which deliberately stays on stdlib `logging.Handler` because the OpenTelemetry Python SDK integrates with `logging.Handler`, not loguru sinks — that one feeds the OTel→Loki audit pipeline and must not be converted. All container stdout/stderr (this logging included) also reaches Loki independently via Promtail (`docs/04-servicios-comunes.md`), auto-discovered per container — no per-service wiring needed for that path.

⚠️ **`[tool.hatch.build.targets.wheel] packages = ["src"]` does NOT make `import <pkg_name>` work** for a `src/<pkg_name>/` layout — hatchling installs the literal `src` directory as the top-level package, not its contents, so a normal/editable install only adds the project root to `sys.path`, not `src/`. Historical: `apikey-service` had this bug silently at first (fixed to `packages = ["src/apikey_service"]`); `markitdown-service`/`whisper-service` used to be genuinely flat (`src/main.py`, package literally named `src`, `packages = ["src"]` was correct there) until both were restructured to match `apikey-service`'s layered shape — now all three use `packages = ["src/<package_name>"]` and the matching `mypy_path = "src"` + `explicit_package_bases = true`. If a service's `pyproject.toml` ever has `packages = ["src"]` again, check whether the layout underneath is genuinely flat before assuming it's fine — it silently breaks `uv run pytest`/a real `pip install .` otherwise (Docker builds don't notice, since `CMD` uses `uvicorn ... --app-dir src`, bypassing installed-package resolution).

⚠️ **A service pulling in `onnxruntime` (transitively, e.g. via `markitdown`) needs a `.python-version` pinning it to a Python version `onnxruntime` actually ships wheels for** (3.12/3.13 as of this writing, not 3.14) — otherwise `uv run` silently picks the system's default Python and dependency resolution fails outright. `markitdown-service/.python-version` pins `3.12` to match its `Dockerfile`'s `FROM python:3.12-slim`. `whisper-service` also pulls in `onnxruntime` transitively (via `faster-whisper`/`ctranslate2`) but did **not** hit this problem — `uv sync` resolved fine even under Python 3.14 — so no `.python-version` was added there; if it ever breaks the same way, this is why.

## Working conventions in this repo

- **No hardcoded IPs in config except where structurally required** — nginx server blocks and Prometheus scrape targets are the accepted exceptions; everything else should resolve via `*.home.arpa`.
- **Secrets are always `CHANGE_ME` placeholders in `.env.example`**, never real values, never committed. Real `.env` files exist only on the deployment host under `/srv/homelab/<node>/`.
- **`N8N_ENCRYPTION_KEY` is irreversible once set** — losing/changing it breaks all existing stored credentials in that n8n instance. Never regenerate casually.
- Every service in a compose file gets a healthcheck with a start_period sized to its actual boot time (whisper-service 90s, SonarQube 120s are the current outliers because of model/JVM warmup).
- When a docker-compose.yml or script encodes a non-obvious decision (a UID quirk, a port choice, a migration reason, why something is/isn't on the LAN), that reasoning is captured as an inline comment right above it — keep that pattern rather than moving rationale into docs only.
- Corresponding `docs/NN-*.md` and the relevant node `README.md` should be updated alongside any structural change (new service, new exposed hostname, new backup target) — this repo's docs are treated as authoritative operational runbooks, not incidental.
- **`rsync`/`scp` to a single-file bind mount (e.g. `pi-dns/config/nginx/nginx.conf`) orphans the running container's mount** — both tools rename-into-place by default, which swaps the inode; the container keeps watching the old one. `nginx -s reload` (or any in-place reload) then silently keeps serving the stale config. After syncing a single-file mount, recreate the container (`docker compose up -d --force-recreate <service>`), don't just reload/restart. Bitten by this twice deploying apikey-service/nginx changes — see `docs/13-troubleshooting.md`.
