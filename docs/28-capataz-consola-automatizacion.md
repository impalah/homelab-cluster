# 28 — Capataz: consola de estado y automatización del clúster

Fecha: 2026-08-15

[Capataz](https://github.com/impalah/capataz) es una consola web privada, repositorio propio fuera de este monorepo (`/home/linus/projects/local-ia/capataz` en el puesto de desarrollo), que agrega el estado de los servicios Docker del clúster (Portainer), enlaza a Grafana/Prometheus, y ejecuta acciones pre-declaradas mediante un `runner` Celery+Ansible con auditoría y RBAC. Sustituye al panel HTML estático que antes ocupaba `index.home.arpa`.

## Qué cambió

- `index.home.arpa` sirve ahora el frontend compilado de Capataz. El panel estático original se movió a `old.index.home.arpa` (mismo contenido, sin cambios).
- `capataz-api` y `capataz-runner` corren en `pi-utils` (`192.168.1.173:8000`), como **servicios del `pi-utils/docker-compose.yml` de este repo** — no como stack separado. Imágenes publicadas en `registry.home.arpa` (ver "Origen del código" más abajo); la config no sensible vive en `pi-utils/.env` junto al resto de servicios del nodo, y las credenciales en `secrets:` (Compose, no Swarm) — ver "Secrets" más abajo.

  ⚠️ Historial de correcciones sobre la primera versión de este despliegue, ambas a petición expresa: (1) se montó al principio como proyecto Compose **independiente** (`docker compose` suelto dentro de `/srv/homelab/pi-utils/capataz/`, con su propio nombre de proyecto y redes) — en este repo todo servicio que vive en un nodo se declara en el `docker-compose.yml`/`.env` de ESE nodo, sin excepciones por venir de un repo externo; (2) después de integrarlo, seguía construyéndose con `build:` local en vez de tirar de `registry.home.arpa/capataz-api:latest` / `capataz-runner:latest`, que ya existían — corregido publicando ambas imágenes multi-arch, ver "Origen del código".
- `capataz-postgres`/`capataz-redis` (los contenedores que trae el `docker-compose.yml` propio de Capataz para un quickstart local) **no se levantan en ningún caso**: `api`/`runner` apuntan a la infraestructura ya compartida del clúster (`postgres-main` en `retaco`, `valkey` en `retaco`).

## Origen del código: `image:` de `registry.home.arpa`, multi-arch

Igual que `apikey-service`/`markitdown-service`/`whisper-service` (dentro de este mismo repo, en `services/`): `pi-utils/docker-compose.yml` declara `capataz-api`/`capataz-runner` con `image: registry.home.arpa/capataz-api:latest` / `capataz-runner:latest` — el nodo solo hace `pull`, nunca `build`. La diferencia real es **dónde** vive el build/push: para los tres servicios de `services/` está en ESTE repo (`Makefile` de cada uno); para Capataz vive en su propio repositorio externo (`impalah/capataz`), en `api/Makefile` y `runner/Makefile` (`make build` en cada uno) — ya preparados de fábrica para multi-arch vía la variable `PLATFORMS` de su `.env` (antes fijada a `linux/amd64` únicamente, cambiada a `linux/amd64,linux/arm64` al integrar Capataz en `pi-utils`, que es arm64).

**Gotcha real encontrado**: la máquina de build (este puesto de trabajo, `ryzen`/`mole`) ya tenía un builder `docker-container` (`mybuilder`) de una sesión anterior, pero sin el emulador QEMU de `arm64` registrado (`docker buildx inspect` solo listaba `linux/amd64`) — el primer `make build` con `PLATFORMS=linux/amd64,linux/arm64` habría fallado o (peor) publicado silenciosamente solo `amd64` de nuevo. Se resolvió con `docker run --privileged --rm tonistiigi/binfmt --install all` (mismo comando que documenta `CLAUDE.md` para el setup inicial de este repo) antes de construir. Confirmado con `docker manifest inspect registry.home.arpa/capataz-api:latest` que el manifest list final incluye `amd64` y `arm64`.

`catalog/`, `api/alembic.ini`, `api/alembic/` y `certs/` (bind-mounts en `pi-utils/docker-compose.yml`) siguen viniendo de un checkout parcial del repo Capataz en `/srv/homelab/pi-utils/capataz/` — no se empaquetan en la imagen (el propio `Dockerfile` de Capataz no los `COPY`a), así que ese checkout sigue haciendo falta aunque ya no se construya nada localmente en el nodo.

Para actualizar Capataz: `make build` en `api/` y en `runner/` del repo `capataz` (puesto de desarrollo, requiere `REGISTRY_USER`/`REGISTRY_PASSWORD` en `api/.env`/`runner/.env` — ya configurados), luego en `pi-utils`: `docker compose pull capataz-api capataz-runner && docker compose up -d capataz-api capataz-runner`. Si cambia `catalog/services.example.yaml` o las migraciones Alembic, repetir además el export+rsync del checkout parcial a `/srv/homelab/pi-utils/capataz/`.

## Por qué `pi-utils`

Comparado en vivo (`free -h`, 2026-08-15): `retaco` tenía 7,8 GiB disponibles pero ya es el nodo más cargado (`postgres-main`, `qdrant`, `n8n-main`, `registry`, `open-webui`, `open-terminal`, Infisical, Authentik, `valkey`) y concentra los secretos/SSO del clúster — añadir ahí una cuenta de automatización con alcance SSH a los 6 nodos aumenta su radio de fallo. `pi-obs` está dedicado a observabilidad, rol distinto. `pi-utils` tenía 5,3 GiB disponibles, ya aloja **Portainer** (integración principal de Capataz) y encaja por rol ("utilidades"). Las imágenes de `api`/`runner` (`python:3.14-slim-*` + `ghcr.io/astral-sh/uv`) son multi-arch, así que `docker compose build` nativo en el propio Pi 5 (arm64) funcionó sin necesitar buildx/QEMU.

`api` y `runner` no necesitan red Docker compartida entre sí (se comunican solo vía la cola en Redis/Valkey), así que podrían separarse en dos nodos distintos, pero con límites de 768M/1024M y ese margen libre no hay coste real en colocar ambos juntos.

## Secrets y config no sensible

Capataz lee sus credenciales sensibles (DSN de Postgres/Redis, token de Portainer, clave SSH del runner, contraseña del vault de Ansible) de ficheros bajo `/run/secrets/<nombre>` — así lo exige su propio código (`file_secret_reader.py` en `api`, `config.py` en `runner`), nunca variables de entorno para eso. `pi-utils/docker-compose.yml` usa el `secrets:` de Compose v2 (funciona sin Swarm, solo bind-mounts los ficheros) apuntando a `./capataz/secrets/<nombre>` — ficheros reales en `/srv/homelab/pi-utils/capataz/secrets/`, `chmod 644` (no `600`: los contenedores corren como uid `10001`, no como el usuario del host — documentado así por el propio Capataz). Es la única diferencia real de patrón frente al resto de servicios de este nodo (que llevan toda su config, sensible o no, por variables de entorno desde `.env`).

La config NO sensible (`CAPATAZ_ENV`, `CAPATAZ_AUTH_MODE`, URLs de Portainer/Grafana...) sí sigue el patrón habitual: bloque `x-capataz-env` en `docker-compose.yml`, valores reales en `pi-utils/.env`, plantilla en `pi-utils/.env.example`.

⚠️ **Gotcha real con `CAPATAZ_LOKI_URL`**: el campo correspondiente en el código de Capataz es `AnyHttpUrl | None`. Si la variable de entorno está **presente pero vacía** (`CAPATAZ_LOKI_URL=` en `.env`, interpolada a `CAPATAZ_LOKI_URL: ${CAPATAZ_LOKI_URL:-}` en el compose), Pydantic intenta parsear `""` como URL y el arranque de `capataz-api` falla (`ValidationError: Input should be a valid URL, input is empty`) — visto en real, causó que el contenedor quedara en crash-loop tras la primera integración. Solo con la variable **totalmente ausente** del entorno del contenedor cae al valor por defecto `None` del propio código. Por eso `CAPATAZ_LOKI_URL` no aparece en absoluto en `x-capataz-env` (ni con default vacío) ni en `pi-utils/.env` — `loki.home.arpa` no está expuesto en este clúster de todos modos (se consulta vía Grafana).

## Postgres y Valkey compartidos, no los contenedores de quickstart

- Base de datos `capataz` creada con `shared/scripts/create-postgres-db.sh postgres-main dbadmin capataz capataz` en `postgres-main` (retaco) — aislada, sin acceso a otras bases del servidor. **Gotcha real encontrado en el despliegue**: la contraseña autogenerada inicial contenía `+`, que URL-encodeado (`%2B`) rompe `alembic upgrade head` — el `env.py` de Capataz pasa la URL a `configparser.set_main_option`, y `ConfigParser` con `BasicInterpolation` interpreta `%` como inicio de una secuencia de interpolación. Se regeneró la contraseña sin caracteres que necesiten URL-encoding (`openssl rand -hex 24`, solo alfanumérico) para evitar el problema de raíz en vez de tocar el código de Capataz.
- Usuario ACL dedicado `capataz` en `retaco/config/valkey/users.acl`:
  ```
  user capataz on >{contraseña} ~* &* +@all -@admin -@dangerous +info
  ```
  **Sin restringir por prefijo de key** (`~*`, no `~capataz:*`) — Celery/kombu no usa un prefijo fijo por defecto, mismo motivo ya documentado para Infisical/BullMQ en `docs/25-valkey-cache.md` y `docs/26-infisical-secretos.md` (restringir por prefijo ahí causó fallos reales). Desplegado con el patrón `/tmp` + `sudo cp`, aplicado recreando el contenedor `valkey` (`docker compose up -d --force-recreate valkey`) en vez de `ACL LOAD` — evita necesitar la contraseña de `valkey-admin`, a costa de un pequeño corte del caché para el resto de consumidores (Infisical/Authentik), aceptable en un homelab.
  - Secreto `redis_url`: `rediss://capataz:<password>@valkey.home.arpa:6379/0?ssl_cert_reqs=required&ssl_ca_certs=/run/ca-certs/ca-bundle.pem` — TLS obligatorio (Valkey tiene `--port 0`), CA montada vía `./certs:/run/ca-certs:ro` (`make trust-ca`, `CA_URL` por defecto ya apunta a `http://pi-dns.home.arpa/ca.crt` en el propio repo de Capataz).

## Cuenta SSH dedicada del runner: `capataz_automation`

El `runner` trae por defecto (`runner/inventories/homelab.yml`) `ansible_user: capataz_automation` — se creó ese usuario de sistema, sin sudo, shell normal, en los 5 nodos SSH-accesibles (`retaco`, `pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils`). En `ryzen`/`mole` (sin usuario dedicado tipo `u-*`, es el puesto de desarrollo) se autorizó la misma clave bajo el usuario existente `linus` — override explícito `ansible_user: linus` solo para ese host en el inventario.

- Clave ed25519 **nueva y dedicada** (nunca la personal/GitHub del usuario), autorizada con `no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty` en cada `authorized_keys` — los tres playbooks que trae Capataz V1 (`check_connectivity.yml`, `restart_service.yml`, `backup_service.yml`) solo hacen `ansible.builtin.ping`/`debug` (simulaciones, sin ejecutar nada real todavía), así que no hace falta ni `pty` ni pertenencia al grupo `docker` ni sudo.
- `secrets/runner_known_hosts` construido con `ssh-keyscan -t ed25519` contra los 6 hosts.
- `runner/inventories/homelab.yml` (en la copia desplegada en `pi-utils`, no en el repo de Capataz en el puesto de desarrollo) actualizado con los 6 nodos reales, sustituyendo los placeholders `node-ai-01`/`node-gpu-01` del ejemplo original.
- Verificado con `ssh -i <clave> <usuario>@<host> whoami` contra los 6 hosts antes de dar el despliegue por bueno.

**Ninguna acción del catálogo dispara todavía un playbook real contra la infraestructura** — la confianza SSH queda operativa de extremo a extremo, pero los tres playbooks de Capataz V1 son simulaciones. Nota: el catálogo YAML importado sí referencia una acción `backup` con `limit: node-ai-01` (placeholder del ejemplo original) — quedaría rota si se invocase tal cual; no se ha tocado el catálogo en este despliegue.

## Frontend: build estático, sin contenedor propio

Siguiendo la sección "Standalone Frontend Deployment" de `docs/07-operations.en.md` del propio repo de Capataz:

1. `docker build --target build -t capataz-frontend-build:tmp ./frontend` (solo la etapa de build del `Dockerfile`, sin necesitar Node en el host) + `docker cp` para extraer `dist/`.
2. `dist/config.js` que trae el build (`frontend/public/config.js`) son valores de *desarrollo local* — se sustituyó a mano con el mismo motor (`envsubst` sobre `frontend/nginx/config.js.template`) y los valores reales: `API_BASE_URL=/api/v1`, `USE_MSW=true`, `DEV_USER=ana.admin`, OIDC vacío.
3. `dist/*` + `config.js` desplegados a `/srv/homelab/pi-dns/nginx/capataz-html/` (nuevo volumen `:ro` en el `nginx` de `pi-dns`, ver `pi-dns/docker-compose.yml`).
4. Bloque `server_name index.home.arpa` en `pi-dns/config/nginx/nginx.conf`: SPA (`try_files ... /index.html`), `location = /config.js` con `Cache-Control: no-store`, `location /api/ { proxy_pass http://192.168.1.173:8000; ... proxy_buffering off; }` — réplica exacta del `frontend/nginx/default.conf` propio de Capataz, adaptado a proxy cross-host en vez de `proxy_pass http://api:8000` (red Docker interna).

**Limitación real de este patrón**: al no haber contenedor con `frontend/nginx/40-render-runtime-config.sh`, `config.js` no se re-renderiza en cada arranque. Cualquier cambio en `CAPATAZ_FRONTEND_*` (URL de la API, activar login real, etc.) exige repetir el paso 2 a mano y redesplegar el fichero — no basta con cambiar una variable de entorno y recrear un contenedor, como en el despliegue Docker estándar de Capataz.

## Estado del piloto — `dev_mock`

`CAPATAZ_ENV=development` + `CAPATAZ_AUTH_MODE=dev_mock` + `CAPATAZ_FRONTEND_USE_MSW=true`: sin login, el frontend usa una identidad sintética con selector de rol (viewer/operator/admin) y llama a la API real (nunca mockea datos en el navegador). `CAPATAZ_ENV=development` es requisito **técnico**, no un descuido: el validador `development_mock_only` en `api/src/capataz_api/core/settings.py` rechaza `dev_mock` si `CAPATAZ_ENV≠development`.

⚠️ El propio `docs/07-operations.en.md` de Capataz advierte: `USE_MSW` (sin autenticación real) solo debería ser `true` en un entorno no alcanzable "desde fuera de tu red de confianza". Este clúster tiene un subnet router Tailscale en `pi-dns` (`docs/18-tailscale.md`) — el acceso remoto exige autenticación Tailscale antes de llegar a la LAN, pero una vez dentro de la LAN (o del túnel), `index.home.arpa` queda sin login propio. Aceptado explícitamente como decisión del piloto; revisar antes de dar por buena una fase con datos/acciones sensibles.

Otras notas del piloto:

- Límites de memoria con `mem_limit` (no `deploy.resources.limits`, sintaxis de Swarm que `docker compose up` normal ignora en silencio) — mismo criterio que `crawl4ai-scraper-service` en este mismo fichero; el `docker-compose.yml` original de Capataz usa `deploy.resources.limits`, que aquí no aplicaba.
- `CAPATAZ_CORS_ORIGINS=https://index.home.arpa` — en la práctica el navegador llama en same-origin (todo pasa por el proxy de `index.home.arpa`), pero se fija igualmente por higiene.
- El token de Portainer usado en `secrets/portainer_token` fue proporcionado directamente por el usuario (no se creó un usuario técnico dedicado en Portainer en este pase — pendiente si se quiere acotar su alcance más adelante, ver `docs/07-operations.en.md` sección "Portainer Token" del propio repo de Capataz).
- `secrets/*` desplegados con `chmod 644` (no `600`) — documentado así por el propio Capataz: los contenedores corren como uid `10001`, no como el usuario del host que hace el bind mount.
