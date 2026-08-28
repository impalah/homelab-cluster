# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

`homelab-cluster` is the **infrastructure-as-config** source of truth for a 6-node home cluster (two x86 PCs + four Raspberry Pi 5s), orchestrated with **Docker Swarm** (mejora 33/39, closed 2026-08-27 — explicitly no Kubernetes). `pi-dns` is deliberately **outside** the Swarm (DNS + Tailscale subnet router only, always-on but not a workload host); the other five nodes are all Swarm managers. Most stateless/lightly-stateful services live in `docker-swarm/stacks/<name>/`, deployed with `docker stack deploy` — the per-node `<node>/docker-compose.yml` files (`ryzen/`, `retaco/`, `pi-obs/`, `pi-sonar/`, `pi-utils/`) now hold only what's genuinely still classic Compose (ryzen's GPU-bound services, node-level observability sidecars) or historical narrative comments about what already migrated out. See `docs/31-docker-swarm.md` for the full migration history and current stack inventory, `docker-swarm/README.md` for the day-to-day Swarm operating guide. This is not an application monorepo — it's Docker Compose/Swarm stacks, Traefik/DNS config, shell scripts, and a shared top-level `services/` directory of small FastAPI microservices. There is no CI, no test suite. The repo **is** under git and pushed to `github.com/impalah/homelab-cluster` (first real commit landed 2026-08-02) — but this checkout is still a separate copy from what's actually running in each node's `/srv/homelab/<node>/`: local edits are not live until deployed (see "Connecting to cluster nodes" below), and the reverse — never assume the checkout matches deployed reality without checking; multiple real deploys this repo's history have found the two had quietly diverged (see the `pi-dns` path gotcha below).

**Services are built and pushed from `services/<name>/` (`make build`), never built by the consuming stack's `docker-compose.yml`.** Every compose file just does `image: registry.404labo.net/<name>:latest` and pulls — see "The three FastAPI microservices" below and `docs/05-instalacion-retaco.md` section 5.3 for the private registry.

**`404labo.net` is the cluster's only hostname suffix** (mejora 41, closed 2026-08-28 — `home.arpa` was retired everywhere: Pi-hole records, Traefik routers/cert, Unbound config, `nginx` on `pi-dns` decommissioned entirely). Split-horizon DNS: Pi-hole resolves `*.404labo.net` only inside the LAN, to private IPs — Route53 (where the domain is really delegated, for the wildcard Let's Encrypt cert's DNS-01 challenge only) never receives a record for it. Historical comments/incident logs in `docs/` that predate the cutover still say `home.arpa` where that was literally true at the time — that's expected, not a sign something was missed.

Language note: all docs, comments, and commit-worthy prose in this repo are in **Spanish**. Match that when editing existing files (READMEs, docs/, inline comments); code identifiers stay in English as they already are.

## Repository layout

```
homelab-cluster/
├── docs/               ← Numbered install/ops guides, 01 through 31+, ordered by real install sequence (docs/01-topologia.md has the full index) — read before touching a node
├── docker-swarm/       ← Swarm stacks (docker stack deploy), one directory per stack — traefik, authentik,
│                          apikey-service, valkey, infisical, vaultwarden, sonarqube, and most other
│                          services now live here, not under a node directory. See docker-swarm/README.md.
├── services/           ← apikey-service, markitdown-service, whisper-service source — built/pushed from
│                          here (make build), NOT from any stack's docker-compose.yml (see below)
├── shared/
│   ├── env/            ← <node>.env.example templates (never real secrets)
│   ├── scripts/        ← Cross-node operational scripts (see below)
│   └── dns/            ← DNS record table + router DHCP notes
├── ryzen/              ← GPU node, classic Compose (never migrated to Swarm): ollama, vllm, open-webui,
│                          whisper-service, comfyui (+ separate observability stack)
├── retaco/             ← Mostly historical now — postgres-main/qdrant/n8n-main/authentik/valkey/infisical
│                          etc. migrated out to docker-swarm/stacks/; registry (private Docker registry)
│                          is the one still classic Compose here
├── pi-dns/             ← Unbound + Pi-hole only — deliberately OUTSIDE the Swarm. nginx reverse proxy +
│                          apikey-service both decommissioned here (mejora 41) — Traefik (in the Swarm)
│                          is the front door now
├── pi-obs/             ← otel-collector, prometheus, grafana, loki, tempo (mostly migrated to
│                          docker-swarm/stacks/pi-obs/ — check before assuming this is live)
├── pi-sonar/           ← Mostly historical — sonarqube/bifrost migrated to docker-swarm/stacks/
└── pi-utils/           ← Mostly historical — rsshub/markitdown/n8n-aux/portainer/vaultwarden migrated to
                           docker-swarm/stacks/; capataz-frontend's nginx config is what's still live here
```

Each node directory follows the same shape: `docker-compose.yml`, `.env.example`, `README.md`, `config/` (bind-mounted, mostly static config), `data/` (bind-mounted runtime state, gitignored-equivalent) — where any of that is still genuinely deployed from the node directory rather than `docker-swarm/stacks/`. Node directories do **not** have their own `services/` — `apikey-service`/`markitdown-service`/`whisper-service` live in the top-level `services/`, images distributed via the private registry (`registry.404labo.net`, on `retaco`).

## Architecture — read this before editing any compose file

- **Swarm stacks each get their own overlay network** (`docker-swarm/stacks/<name>/docker-compose.yml`), most with `attachable: true`; classic-Compose nodes (ryzen, and whatever's left of retaco/pi-obs/pi-sonar/pi-utils) each still get their own bridge network (`<node>-net`) too. No shared Docker network across the two worlds — inter-service traffic that crosses that boundary goes over the real LAN using `*.404labo.net` hostnames (via Pi-hole/Unbound, resolved through Traefik) or raw IPs, never Docker container/service names, **except** within the same stack/compose file.
- **Fixed node IPs** (documented in `docs/02-plan-ip-y-dns.md` and the root `README.md`): ryzen `.150`, retaco `.174`, pi-dns `.170`, pi-obs `.171`, pi-sonar `.172`, pi-utils `.173`, pinchi `.175`. `pi-dns`'s internal Docker network additionally uses fixed IPs in `172.20.0.0/24` (see `pi-dns/docker-compose.yml`) because Unbound/Pi-hole reference each other by IP, not name.
- **`pinchi` (192.168.1.175, x86_64 PC) is the newest node** (added 2026-08-22) — base system only (`docs/30-instalacion-pinchi.md`): static IP, Docker Engine installed, no services deployed yet, no `pinchi/docker-compose.yml`. Its SSH gotcha, real and worth knowing before touching any node's `sshd_config`: an `/etc/ssh/sshd_config.d/50-cloud-init.conf` drop-in set `PasswordAuthentication yes` and was processed *before* the main `sshd_config`'s own directive (`Include` runs mid-file, and OpenSSH keeps the first value seen per keyword) — a plain `sed` on `sshd_config` silently had no effect until overridden with a same-named-scheme drop-in (`00-homelab.conf`, sorts before `50-cloud-init.conf`). Don't assume `docs/03`'s `sed`-based `PasswordAuthentication no` recipe works unmodified on a node provisioned via cloud-init — check `/etc/ssh/sshd_config.d/` first.
- **Traefik is the front door** (`docker-swarm/stacks/traefik/`, `mode: global` — one replica per Swarm manager, routing mesh gives HA without needing `constraints`). Terminates TLS with a real Let's Encrypt wildcard cert for `*.404labo.net` (DNS-01 via Route53, `shared/scripts/renew-letsencrypt.sh` on `pi-dns` + `shared/scripts/deploy-traefik-cert.sh` auto-rotates the Swarm secret on real renewal — see `docs/15-ca-interna.md`), and routes every `*.404labo.net` hostname to the right backend — either the `providers.file` static routes (`docker-swarm/stacks/traefik/dynamic/routes.yml`, for backends not yet Swarm services) or `providers.swarm` labels declared directly on the target stack. New exposed services need: a router (file route or `traefik.http.routers.*` labels), a DNS record (`shared/dns/dns-records.md` + `shared/scripts/load-dns-records.sh`), and a row in the root `README.md` service table. `nginx` on `pi-dns` — the original front door before the Swarm migration — is fully decommissioned (mejora 41); its config is kept under `pi-dns/config/nginx/` purely as historical reference, marked retired, never deployed.
- **apikey-service** (`services/apikey-service/`, now a Swarm stack — `docker-swarm/stacks/apikey-service/`, reachable cluster-wide via routing mesh on port 8091; FastAPI + SQLAlchemy async + Postgres) issues/validates API keys used by Traefik's `apikey-auth` forwardAuth middleware to protect services with no auth of their own (e.g. Ollama). See `docs/06-instalacion-pi1-dns.md`.
- **`pi-dns` is the Tailscale subnet router** (`tailscale` container, `network_mode: host`, `docs/18-tailscale.md`) — authenticated remote access to the whole `192.168.1.0/24` LAN from outside, with `*.404labo.net` resolving over the tunnel via Tailscale's Split DNS (nameserver `192.168.1.170` restricted to domain `404labo.net`, configured in the Tailscale admin console, not in this repo). Needs `TS_USERSPACE=false` + `/dev/net/tun` under `devices:` (not `volumes:`, or it silently falls back to non-routable userspace networking) + kernel netfilter modules pre-loaded on the **host** (`ip_tables`, `iptable_filter`/`nat`, `ip6` equivalents — the container can't `modprobe` them itself without `CAP_SYS_MODULE`, deliberately not granted). Interactive `tailscale up` login (no `TS_AUTHKEY`) does not work in this container — `containerboot` kills the login after ~60s and Docker's restart regenerates a new node identity/login URL each time; always use a reusable, non-ephemeral `TS_AUTHKEY`.
- **Pi-hole's admin panel is published directly on the LAN, no hostname, no proxy** (`http://192.168.1.170:8053`, mejora 41) — before nginx was decommissioned it lived at `pihole.home.arpa`; that hostname was retired without a replacement, by design.
- **`ryzen` ("mole") supports Wake-on-LAN** (`docs/19-wake-on-lan.md`) — it's the only node meant to be powered off when idle (GPU desktop, not always-on infra). NIC (`enp6s0`, Intel `igc`) confirmed to support and have `Wake-on: g` active, persisted explicitly via `nmcli connection modify ... 802-3-ethernet.wake-on-lan magic` (don't rely on the driver default alone). Wake it from any other node with `shared/scripts/wake-mole.sh [nodo]` (defaults to `pi-utils`, needs `wakeonlan` installed there — already done) — must run from a node OTHER than `mole` itself (it's off), so the script is deployed as a local copy on all 5 always-on nodes' `/srv/homelab/shared/scripts/` (same `rsync`-per-node convention as the rest of `shared/`, `docs/03-instalacion-base-ubuntu-raspi.md`), not just in this checkout. Full poweroff (S5) is the state used (not suspend/hibernate — NVIDIA GPU resume from S3/S4 is unreliable on Linux for this node's dual-GPU setup, RTX 5070 + RTX 3070), confirmed working end-to-end with a real poweroff + magic packet test. Motherboard is an ASUS ROG STRIX B550-XE — its WoL toggle ("Power On By PCI-E/PCI") is hidden/disabled by a separate "ErP Ready" BIOS setting under `Advanced → APM Configuration`; had to disable ErP first before the WoL option even showed up. See `docs/19-wake-on-lan.md`.
- **`ketekasko` (192.168.1.180) is a UGREEN NASync DH2300 NAS on the LAN, NOT part of this repo's Docker cluster** — no `docker-compose.yml`, no node directory, runs its own OS (UGOS Pro). `ketekasko.404labo.net` is a direct DNS alias (same pattern as `postgresql.404labo.net`), bypassing Traefik since UGOS Pro serves its own HTTPS on `:9443` with its own cert. NFSv4 required an SSH-side workaround the GUI doesn't expose: edit `/etc/nfs.conf` (`[nfsd]` section, standard `nfs-utils`) AND `/etc/nfs.json` (UGOS-specific, `"maximumNFSProtocol"` — the GUI regenerates `nfs.conf` from this on "Apply", so editing only one reverts on next GUI save) — but even with `nfsd` negotiating v4 (`/proc/fs/nfsd/versions` shows `+4`), actual v4 mounts fail (`No such file or directory`) because UGOS Pro's GUI-generated `/etc/exports` doesn't expose an NFSv4 pseudo-root (`fsid=0`); NFSv3 on the same export works fine (confirmed with `no_root_squash` — root writes as root). Client mounts use NFSv3 (`mount -t nfs -o vers=3`) against the **real** export path (`showmount -e <nas>`, not the shared-folder name — e.g. `/volume1/nfs-data`, not `/nfs-data`) as a result — see `docs/21-configuracion-nas-ugreen.md`.
- **postgres-main lives on retaco** and is multi-tenant: every consumer (n8n, SonarQube, future projects) gets its own isolated DB + role via `shared/scripts/create-postgres-db.sh` — never share a role across projects. It's deliberately published to the LAN (`5432:5432`) because pi-obs's postgres-exporter and pi-sonar's SonarQube reach it cross-node; isolation is by password/role, not network.
- **The `services/` images (`apikey-service`/`markitdown-service`/`whisper-service`) never carry the watchtower auto-update label** (`com.centurylinklabs.watchtower.enable=true`) — only stateless upstream images do, even now that they're pulled from `registry.404labo.net` instead of built per-node. Stateful services (databases, Pi-hole, SonarQube) are also deliberately excluded from auto-update; see `docs/16-mantenimiento-actualizaciones.md`.
- **Bind-mount ownership is UID-sensitive and inconsistent by design** — n8n and SonarQube containers run as UID 1000, Grafana as 472, Postgres as 70, Prometheus as 65534, Loki as 10001. `shared/scripts/prepare-host.sh` chowns the generic node directory first, then re-chowns specific data subdirectories for the UIDs above. If you add a new stateful service, add its own `chown` line — don't rely on the generic one. Re-running `prepare-host.sh` against a node that already has real data is only safe for directories that already have an explicit chown (see `docs/13-troubleshooting.md`).
- **ryzen has two independent compose stacks** — `docker-compose.yml` (GPU/AI: ollama, vllm, open-webui, whisper-service, comfyui) and `docker-compose.observability.yml` (host-level, no `.env`) — so the heavy GPU stack can be stopped without losing node-exporter/cadvisor. Commands without `-f` only touch the first.
- **ryzen's two GPUs are each shared by a pair of services that must never run simultaneously.** GPU 0 (RTX 5070, 12GB — also drives the physical display, so real free VRAM is less than nominal) alternates `ollama`/`vllm` via `ryzen/switch-llm-backend.sh`; GPU 1 (RTX 3070, 8GB) alternates `whisper-service`/`comfyui` via `ryzen/switch-gpu1-backend.sh`. Never `docker compose up -d <service>` either pair member directly — always go through the switch script, or you'll get GPU OOM / VRAM contention. See `docs/07-instalacion-ryzen.md`.
- Every service that has a healthcheck is wired with `depends_on: condition: service_healthy` where startup order matters (e.g. `pi-dns/docker-compose.yml`'s `pihole` waits on `unbound`).

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

(Full table with SSH groups: `docs/01-topologia.md`, section "Acceso SSH a los nodos".) Key-based auth is already set up for this workstation — a bare `ssh u-<x>@192.168.1.17x` should just work; if it prompts for a password or is refused, the username is wrong before assuming the key is missing (this has happened — don't guess a username pattern for a node not in the table above without confirming first). Each user can write to their own `/srv/homelab/<node>/` tree without `sudo`; `sudo` is only needed for OS-level operations, root-owned config subtrees, or bind-mounted data owned by a specific container UID (see the "Bind-mount ownership" bullet further down). `pi-dns`'s `u-dns` additionally holds a dedicated, single-purpose SSH key (`~/.ssh/id_ed25519_retaco_certs`) to `u-data@retaco` — used *only* by `shared/scripts/deploy-traefik-cert.sh` to rotate the Traefik TLS secret; don't repurpose it for anything else.

**Deploying to a Docker Swarm stack is different from deploying to a node directory** — most services now live under `docker-swarm/stacks/<name>/docker-compose.yml`, not any single node's `/srv/homelab/<node>/`. There's no persistent checkout of `docker-swarm/` on any node; deploy by rsync-ing the stack's compose file (and `dynamic/routes.yml` for `traefik`) to `/tmp` on a Swarm manager (any of retaco/pi-obs/pi-sonar/pi-utils/pinchi) and running `docker stack deploy -c <file> <stack-name> --with-registry-auth` from there. Swarm `configs`/`secrets` are immutable — a content change needs a new `-vN+1` suffix (bump it in the compose file's `configs:`/`secrets:` blocks) before `docker stack deploy` will pick it up; the old `docker service inspect <service> --format '{{...}}'` trick is the fast way to check what version a running service is actually using before assuming the git-tracked number is current (rotation scripts like `deploy-traefik-cert.sh` bump versions without touching git at all).

**Deploying a changed file to a node — standard pattern, works everywhere, sidesteps permission surprises:**
```bash
rsync -av <local-file> u-<x>@192.168.1.17x:/tmp/<basename>
ssh u-<x>@192.168.1.17x "sudo cp /tmp/<basename> <real-destination-path> && rm /tmp/<basename>"
```
Land in `/tmp` first, then `sudo cp` into place, rather than `rsync`/`scp` straight to the final path — this also sidesteps the single-file-bind-mount inode-swap gotcha already noted below (`cp` overwriting an existing file preserves the inode; `rsync`/`scp` rename-into-place and orphan it). For paths the SSH user already owns outright (most of `/srv/homelab/<node>/`), a direct `rsync -av <local-file> u-<x>@192.168.1.17x:/srv/homelab/<node>/<path>` is fine and one step shorter — reach for the `/tmp` + `sudo cp` version whenever the destination might be root- or container-UID-owned, or whenever unsure.

⚠️ **A node's real deployed bind-mount path does not always mirror this repo's own directory layout** — historically confirmed on `pi-dns` for the now-retired `nginx` (repo versioned it under `pi-dns/config/nginx/`, the real bind mount was `/srv/homelab/pi-dns/nginx/conf/`). Deploying to the repo-shaped path silently no-ops (the container keeps serving the old file) — this has caused real, confusing bugs more than once. Before deploying *any* config to *any* node/stack, confirm the real bind-mount source in the actual `docker-compose.yml` (`grep -A3 '<service>:' <path>/docker-compose.yml` for the `volumes:` block) rather than assuming it matches the repo's folder name.

Traefik's dynamic file-provider config can be validated/applied without restarting the service — `providers.file.watch=true` picks up a changed `docker config` on its own once redeployed:
```bash
# after `docker stack deploy` with a bumped traefik-dynamic-routes-vN in docker-compose.yml
docker service logs traefik_traefik --since 1m   # loki-driver logging -- query Loki directly instead if this returns nothing
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

# Close/reopen direct IP:port access to Traefik-fronted services (bypasses apikey-auth otherwise)
bash shared/scripts/setup-firewall.sh <node|all>            # once per node, installs prereqs
bash shared/scripts/toggle-direct-access.sh <node|all> off   # restrict to the 5 Swarm manager nodes only
bash shared/scripts/toggle-direct-access.sh <node|all> on    # reopen to the LAN

# Deploy/redeploy a Swarm stack (from a Swarm manager -- retaco/pi-obs/pi-sonar/pi-utils/pinchi --
# after rsync-ing docker-swarm/stacks/<name>/ there, see "Connecting to cluster nodes" above)
docker stack deploy -c docker-compose.yml <stack-name> --with-registry-auth
docker service ls                                 # N/N replicas across the whole Swarm
docker service logs <stack>_<service> --since 5m   # empty for the `loki` logging driver -- query Loki directly instead
```

Plain `ufw deny <port>` does NOT block Docker-published ports (Docker's DNAT rules bypass the INPUT chain where ufw lives) — `toggle-direct-access.sh` manages the `DOCKER-USER` iptables chain directly instead. See `docs/17-firewall-acceso-directo.md`.

Valid node names for the classic-Compose scripts (`update-stack.sh`, `check-health.sh`, `toggle-direct-access.sh`...): `ryzen | retaco | pi-dns | pi-obs | pi-sonar | pi-utils` — `pinchi` isn't in that set (Swarm-only, no classic `docker-compose.yml` of its own). Swarm stacks aren't addressed by node name at all — by stack name instead (`docker-swarm/stacks/<name>/`).

### The three FastAPI microservices

`services/apikey-service/`, `services/markitdown-service/`, `services/whisper-service/` (top-level, not under any node directory) — each is a standalone `uv`/hatchling Python project (no monorepo tooling, no shared package). All three have real tooling — each configured independently in its own `pyproject.toml` (`[tool.ruff]`, `[tool.mypy]`, not shared between them): `tests/` (pytest, `make test`, `>80%` coverage enforced via `--cov-fail-under=80`), `ruff` (`make lint` / `make format`), `mypy --strict`-ish (`make typecheck`), and SonarQube analysis via `pysonar` (`make sonar` / `make sonar-check`, project keys `apikey-service` / `markitdown-service` / `whisper-service` on `pi-sonar` — `sonar-project.properties`). All `SONAR_*`/service-specific secrets for local dev come from each service's own `.env` (gitignored, copy from `.env.example`) — each `Makefile` deliberately does `-include .env` **without** a blanket `export`, since exporting would leak DB URLs or other settings into `make test`'s subprocess env and override test-isolation defaults set with `os.environ.setdefault(...)`/`monkeypatch`; each target that needs a `.env` value passes it explicitly on that one command line instead (see `sonar:` target). `whisper-service`'s tests never load a real `WhisperModel`/touch CUDA — `/transcribe` is tested by monkeypatching the module-level `_model` in `whisper_service.infrastructure.whisper_model` with a fake object, so the suite runs on any machine without a GPU.

**All three now share the same layered structure** (`apikey-service`'s shape, extended to the other two): `src/<package_name>/main.py` (thin — app factory, `lifespan` if needed, router registration only), `config.py` (pydantic-settings), `schemas.py` (Pydantic request/response models), `dependencies.py` (FastAPI `Depends()` providers), `controllers/` (routers — translate domain exceptions to `HTTPException`, no business logic), `services/` (business rules — no FastAPI, no external-library imports, raise plain domain exceptions like `UnsupportedFormatError`/`ModelNotLoadedError`), and either `repositories/` (apikey-service, SQLAlchemy) or `infrastructure/` (markitdown-service/whisper-service — wraps `MarkItDown`/`faster_whisper` respectively, keeps the external library out of the service layer). `whisper-service`'s loaded model lives as module state in `infrastructure/whisper_model.py` (`set_model()`/`get_model()`), not in `main.py`.

**Build/push lives in the Makefile, not in any stack's `docker-compose.yml`.** `make build` in `services/<name>/` reads the version from `pyproject.toml`, logs into `registry.404labo.net` (credentials from `.env` — `REGISTRY_USER`/`REGISTRY_PASSWORD`), and pushes both `:<version>` and `:latest`. Consuming stacks only do `image: registry.404labo.net/<name>:latest` + `docker compose pull`/`up -d` (or `docker service update`/`docker stack deploy` for a Swarm stack) — no `build:` block anywhere anymore. `make bump-version` (`PART ?= patch`, override with `PART=minor|major`) bumps `pyproject.toml` via `bump2version`; it's a separate, explicit step, not auto-chained into `build`.

⚠️ **`apikey-service` and `markitdown-service` must be multi-arch** (`linux/amd64,linux/arm64`) — they run on `pi-dns`/`pi-utils`, Raspberry Pi 5s (arm64), while this repo is normally worked on from x86 machines. Their `build` targets use `docker buildx build --platform $(PLATFORMS) --push` (not plain `docker build`, which can't produce multi-platform manifests), with QEMU emulation for the arm64 leg. One-time setup on any build machine: `docker run --privileged --rm tonistiigi/binfmt --install all` + a `docker-container`-driver builder (`docker buildx create --driver docker-container --use`). `whisper-service` stays **amd64-only, plain `docker build`, on purpose** — it needs NVIDIA CUDA, which the Pi's don't have; it only ever runs on `ryzen` (x86).

⚠️ **The `docker-container` buildx driver runs builds in a separate BuildKit container with its own cert store — it does NOT inherit the host's trusted CAs**, even after `update-ca-certificates` on the host. Pushing to `registry.404labo.net` from that builder fails with `x509: certificate signed by unknown authority` until a CA is added inside the `buildx_buildkit_<name>0` container's own `/etc/ssl/certs/ca-certificates.crt` (`docker cp` it in, append, `docker restart` the buildkit container — Alpine-based, no `update-ca-certificates` binary, so append the PEM directly). Hit this live building `apikey-service`/`markitdown-service`, back when `registry.home.arpa` used the internal CA (pre-mejora-41). **Not re-verified since the cutover to `registry.404labo.net`'s real Let's Encrypt wildcard cert** (mejora 41) — BuildKit's own image may or may not ship a standard system CA bundle that already trusts Let's Encrypt; check before assuming either this note or its fix (append the internal CA) still applies verbatim.

⚠️ **`dockerd`'s own TLS verification for a registry needs the right CA trusted at the *system* level.** Historical, from when `registry.home.arpa` used the internal CA (`docs/15-ca-interna.md`) — `pi-dns` and `pi-utils` didn't have it installed even though they're cluster nodes (only `ryzen`/dev machines did); fix was installing it (`docs/15-ca-interna.md`, "Linux (Ubuntu/Debian)" section) **plus a `sudo systemctl restart docker`** (Go's cert pool is read once per daemon lifetime, doesn't pick up a mid-run `update-ca-certificates`). Since mejora 41, `registry.404labo.net` serves a real Let's Encrypt wildcard cert via Traefik — confirmed with a plain `curl` (no `-k`, no internal-CA-trusting flags) that the chain validates against a stock system trust store, so this class of problem is likely moot for `dockerd` itself now (a standard `ca-certificates` package already trusts ISRG's roots) — not exhaustively re-verified on every node, though. Still needs a one-time `docker login registry.404labo.net` on each node/stack, as whichever OS user runs `docker compose`/is the Swarm's registry-auth identity (credentials in Vaultwarden, "Docker Registry").

Port convention: services deliberately avoid `8000` (FastAPI's ubiquitous default) to prevent collisions — e.g. apikey-service uses 8090, whisper-service uses 9800. Follow this when adding a new service.

All Python microservices (now six: the three below plus `crawl4ai-scraper-service`, `epub2pdf-service`, `pdf2chunks-service`) log via `loguru`, not stdlib `logging` directly — but stdlib logging isn't ignored: an `InterceptHandler` (`logging_setup.py`/`core/logging.py`) redirects uvicorn/fastapi/asyncio (plus any service-specific library that logs via stdlib — playwright/crawl4ai, faster_whisper/ctranslate2...) into loguru, so everything ends up through the same sink with the same format. `Settings` carries `log_level`/`log_format` (`Literal["text", "json"]`, code default `"text"`, overridden to `json` in each node's `docker-compose.yml` for production); the stdout sink uses `serialize=settings.log_format == "json"`. `uvicorn.access` (one line per HTTP request, including every Docker healthcheck) is pinned to `WARNING` unless `log_level=DEBUG`, since otherwise it floods Loki with zero-value "GET /health 200" lines every few seconds — see `docs/desarrollo-microservicios-python.md` section 7 for the full pattern. Messages use `{}`-style placeholders (not `%s`). The one exception is `apikey-service`'s `audit_logger` (`logging_setup.py`), which deliberately stays on stdlib `logging.Handler` because the OpenTelemetry Python SDK integrates with `logging.Handler`, not loguru sinks — that one feeds the OTel→Loki audit pipeline and must not be converted. All container stdout/stderr (this logging included) also reaches Loki independently via Promtail (`docs/04-servicios-comunes.md`), auto-discovered per container — no per-service wiring needed for that path.

⚠️ **`[tool.hatch.build.targets.wheel] packages = ["src"]` does NOT make `import <pkg_name>` work** for a `src/<pkg_name>/` layout — hatchling installs the literal `src` directory as the top-level package, not its contents, so a normal/editable install only adds the project root to `sys.path`, not `src/`. Historical: `apikey-service` had this bug silently at first (fixed to `packages = ["src/apikey_service"]`); `markitdown-service`/`whisper-service` used to be genuinely flat (`src/main.py`, package literally named `src`, `packages = ["src"]` was correct there) until both were restructured to match `apikey-service`'s layered shape — now all three use `packages = ["src/<package_name>"]` and the matching `mypy_path = "src"` + `explicit_package_bases = true`. If a service's `pyproject.toml` ever has `packages = ["src"]` again, check whether the layout underneath is genuinely flat before assuming it's fine — it silently breaks `uv run pytest`/a real `pip install .` otherwise (Docker builds don't notice, since `CMD` uses `uvicorn ... --app-dir src`, bypassing installed-package resolution).

⚠️ **A service pulling in `onnxruntime` (transitively, e.g. via `markitdown`) needs a `.python-version` pinning it to a Python version `onnxruntime` actually ships wheels for** (3.12/3.13 as of this writing, not 3.14) — otherwise `uv run` silently picks the system's default Python and dependency resolution fails outright. `markitdown-service/.python-version` pins `3.12` to match its `Dockerfile`'s `FROM python:3.12-slim`. `whisper-service` also pulls in `onnxruntime` transitively (via `faster-whisper`/`ctranslate2`) but did **not** hit this problem — `uv sync` resolved fine even under Python 3.14 — so no `.python-version` was added there; if it ever breaks the same way, this is why.

## Working conventions in this repo

- **No hardcoded IPs in config except where structurally required** — Traefik's `providers.file` static backends (`docker-swarm/stacks/traefik/dynamic/routes.yml`) and Prometheus scrape targets are the accepted exceptions; everything else should resolve via `*.404labo.net`.
- **Secrets are always `CHANGE_ME` placeholders in `.env.example`**, never real values, never committed. Real `.env` files exist only on the deployment host under `/srv/homelab/<node>/`.
- **`N8N_ENCRYPTION_KEY` is irreversible once set** — losing/changing it breaks all existing stored credentials in that n8n instance. Never regenerate casually.
- Every service in a compose file gets a healthcheck with a start_period sized to its actual boot time (whisper-service 90s, SonarQube 120s are the current outliers because of model/JVM warmup).
- When a docker-compose.yml or script encodes a non-obvious decision (a UID quirk, a port choice, a migration reason, why something is/isn't on the LAN), that reasoning is captured as an inline comment right above it — keep that pattern rather than moving rationale into docs only.
- Corresponding `docs/NN-*.md` and the relevant node `README.md` should be updated alongside any structural change (new service, new exposed hostname, new backup target) — this repo's docs are treated as authoritative operational runbooks, not incidental.
- **`rsync`/`scp` to a single-file bind mount (e.g. `pi-utils/config/capataz-frontend/default.conf`) orphans the running container's mount** — both tools rename-into-place by default, which swaps the inode; the container keeps watching the old one. An in-place reload (e.g. `nginx -s reload` inside `capataz-frontend`) then silently keeps serving the stale config. After syncing a single-file mount, recreate the container (`docker compose up -d --force-recreate <service>`), don't just reload/restart. Bitten by this more than once historically deploying apikey-service/nginx changes (back when nginx on `pi-dns` was still the front door) — see `docs/13-troubleshooting.md`.
