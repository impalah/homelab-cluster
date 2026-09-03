# 36 — Forgejo: repositorios Git autoalojados

> Este documento cubre la **instalación y operación** de Forgejo (arquitectura, despliegue, incidentes reales de infraestructura). Para el **manual de uso** (primeros pasos, claves SSH, repositorios, incidencias/PRs, la CLI `tea`, y un curso práctico de Git con incidentes reales), ver `docs/forgejo/`.

## Qué es y por qué está aquí

Mejora 7 del backlog (`docs/22-mejoras-futuras.md`). Todo el código de este clúster vive en GitHub — la intención de la mejora 7 es migrar a [Forgejo](https://forgejo.org/) (fork FOSS de Gitea, BSD-3, sin CLA corporativo) como sistema principal, con GitHub como espejo de solo lectura mientras haga falta. Mismo criterio "FOSS real, sin depender de un tercero para algo sensible" ya aplicado en este clúster a Vaultwarden/Infisical/ntfy.

**Esta primera ronda (2026-09-03) cubre solo la instalación núcleo** — Forgejo en sí, accesible por web (HTTPS) y Git (SSH), con su base de datos y almacenamiento. **No incluye todavía**:
- Migración de repositorios existentes (mejora 7, punto 7.2 del backlog) — ninguno se ha movido de GitHub.
- Forgejo Actions / CI (7.3) — no activado.
- Package Registry integrado de Forgejo (7.4, punto 1) — sigue usándose el `registry:2` standalone (`docs/29-registry-mantenimiento.md`).

Se abordó deliberadamente "poco a poco", decisión explícita del usuario — cada bloque de diseño (base de datos, acceso SSH, nodo) se confirmó antes de tocar ningún fichero.

## Arquitectura

- **Stack Swarm** (`docker-swarm/stacks/forgejo/docker-compose.yml`), **nace directamente como stack Swarm** — sin legado Compose que migrar (a diferencia de la mayoría de servicios con estado de la Fase 4, `docs/31-docker-swarm.md`). **Sin `constraints` de nodo** — puede aterrizar en cualquiera de los 5 managers, portable gracias al volumen NFS (ver abajo). Mismo patrón que `ntfy`/`open-webui`/`n8n-main` tras la mejora 47.
- **Imagen rootless fijada por versión** (`codeberg.org/forgejo/forgejo:16.0.3-rootless`, no `latest`, no la variante root) — uid/gid **1000** de fábrica, coherente con el resto del clúster (n8n/SonarQube ya corren como 1000, ver CLAUDE.md "Bind-mount ownership"). El directorio de datos real de esta variante es `/var/lib/gitea` (no `/data`, eso es solo la imagen root).
- **Almacenamiento: un único volumen Docker `driver: local` + `driver_opts: type: nfs`** contra el NAS (`ketekasko`, `/volume1/nfs-data/forgejo/data`, `vers=3` obligatorio — NFSv4 roto en este NAS, `docs/21-configuracion-nas-ugreen.md`) montado en `/var/lib/gitea`. Cubre repos, LFS, avatares, adjuntos, config (`app.ini`) y el índice de búsqueda `bleve`. No se separó el índice en almacenamiento local/efímero pese a ser regenerable — con `replicas: 1` (un solo escritor a la vez) no hay riesgo real de locking concurrente, mismo razonamiento "mecanismo neutro" ya aplicado a SQLite en `n8n-aux`/`open-webui` (mejora 47).
- **Base de datos: Postgres en `postgres-main`** (retaco), rol/BD aislados `forgejo`/`forgejo`, creados con el patrón habitual (`create-postgres-db.sh postgres-main dbadmin forgejo forgejo`) — **no** SQLite embebido. Con esta BD sí hay escritura real y frecuente (a diferencia del SQLite vestigial aceptado en otros servicios), mismo criterio que evitó ese riesgo en la mejora 47.
- **Git por SSH en el puerto 2222**, publicado **directo** (`ports: mode: ingress`, sin pasar por Traefik — SSH no es HTTP, Traefik necesitaría un entrypoint TCP dedicado que no existe hoy). Mismo mecanismo de bypass que ya usa `registry` para su propio protocolo no-HTTP. La imagen rootless ya escucha SSH en 2222 por defecto (no puede bindear el 22 privilegiado sin root); se fija explícito en el compose (`SSH_LISTEN_PORT`/`SSH_PORT`) para no depender de un valor por defecto no versionado.
- **HTTPS vía Traefik**, `traefik.http.routers.*` como labels del propio stack (`provider.swarm`, no `providers.file`) — mismo patrón que `ntfy`. Certificado real de Let's Encrypt (wildcard `*.404labo.net`).
- **Secretos vía Infisical**, mismo patrón que el resto del clúster: `docker secret` (`forgejo-infisical-client-id-v1`/`-client-secret-v1`/`-project-id-v1`, `external: true`) + `infisical run` antepuesto al entrypoint nativo de la imagen. La contraseña de Postgres (`FORGEJO__database__PASSWD`) vive **solo** en Infisical, carpeta `/forgejo/` del proyecto único "Homelab Cluster" (no un proyecto Infisical nuevo — todos los servicios comparten proyecto, separados por carpeta) — nunca en este repo.
- **`INSTALL_LOCK=true`** — evita el asistente web de instalación (todo preconfigurado por variables `FORGEJO__*`), igual que cualquier servicio expuesto vía Traefik.
- **DNS**: `forgejo.404labo.net → 192.168.1.175` (pinchi, por convención — igual que el resto de servicios enrutados por label, ver `shared/dns/dns-records.md`), cargado directamente en la UI de Pi-hole (**Settings → Local DNS Records**, ruta que cambió respecto a versiones antiguas de Pi-hole documentadas en otros sitios de este repo — ya no es `/admin/dns_records.php`).

## Incidente real durante el primer despliegue — healthcheck con patrón de grep incorrecto

**Síntoma**: el servicio arrancaba, Postgres conectaba, SSH y HTTP escuchaban, `/api/healthz` respondía `200 OK` repetidamente (confirmado en los logs vía Loki) — pero cada tarea moría con `SIGTERM` a los ~2-3 minutos y Swarm la reprogramaba en otro nodo indefinidamente (`0/1` réplicas persistente, `docker service ls`). El router de Traefik tampoco aparecía nunca (`docker exec <traefik> wget -qO- http://localhost:8080/api/http/routers` no listaba `forgejo`), lo que inicialmente hizo sospechar de un problema de red/ambigüedad de labels — varias horas se dedicaron a descartar esa vía (añadir `traefik.docker.network` explícito, quitar el `ports:` de SSH) sin efecto real.

**Causa real**: el `healthcheck.test` comparaba la salida de `/api/healthz` contra el patrón literal `"status":"pass"` (sin espacio), pero el JSON real que devuelve Forgejo lleva espacio tras los dos puntos:

```json
{
  "status": "pass",
  ...
}
```

`grep -q '"status":"pass"'` nunca coincidía, así que Docker marcaba el contenedor `unhealthy` tras `start_period` (90s) + los reintentos configurados, y Swarm lo mataba y reprogramaba en bucle — **el router de Traefik no aparecía como consecuencia indirecta**: Traefik sí necesita que la tarea esté sana/estable para publicar la ruta de forma consistente, así que el síntoma "router ausente" era en realidad el mismo problema, no uno distinto.

**Verificación en vivo** (la forma real de diagnosticarlo, no adivinada): `docker exec <contenedor> wget -q --tries=1 -O - http://127.0.0.1:3000/api/healthz` mostró el JSON pretty-printed con el espacio, confirmando el desajuste.

**Arreglo**, ya en el compose (`docker-swarm/stacks/forgejo/docker-compose.yml`):

```yaml
test: ["CMD-SHELL", "wget -q --tries=1 -O - http://127.0.0.1:3000/api/healthz | grep -q '\"status\": \"pass\"' || exit 1"]
```

**Lección para el futuro**: cuando un healthcheck personalizado usa `grep` contra un JSON de una API de terceros, comprobar el formato **real** de la respuesta (`curl`/`wget` directo, no asumir el formato "compacto" sin espacios) antes de escribir el patrón — especialmente con APIs que devuelven JSON pretty-printed por defecto, como el `/api/healthz` de Forgejo/Gitea.

## Instalación — pasos ejecutados (2026-09-03)

1. **Directorio NFS**, en un manager con `/mnt/nfs-data` montado (retaco) — un `mkdir` simple hereda la ACL de UGOS del directorio padre correctamente (`docs/21-configuracion-nas-ugreen.md`), pero como con cualquier directorio nuevo en el NAS, hace falta `sudo` (root pasa siempre vía `no_root_squash`):

   ```bash
   ssh u-data@192.168.1.174 "sudo mkdir -p /mnt/nfs-data/forgejo/data && sudo chown -R 1000:1000 /mnt/nfs-data/forgejo"
   ```

2. **Rol y base de datos Postgres**, contra el ID/nombre real del contenedor `postgres-main` (no siempre coincide con el nombre corto del servicio en un stack Swarm — `docker ps -f name=postgres-main_postgres-main` para obtenerlo):

   ```bash
   ssh u-data@192.168.1.174 "bash /srv/homelab/shared/scripts/create-postgres-db.sh <id-contenedor-postgres-main> dbadmin forgejo forgejo"
   ```

3. **Infisical** (UI, `https://infisical.404labo.net`, proyecto "Homelab Cluster" → Secrets Management → Production):
   - Carpeta nueva `/forgejo/`.
   - Secreto `FORGEJO__database__PASSWD` con la contraseña generada en el paso 2.
   - Identidad de máquina nueva (Access Control → Machine Identities → Add), nombre `forgejo`, rol **Viewer** (mismo rol que el resto de identidades de servicio), auth method **Universal Auth** (se crea automáticamente).
   - Client Secret generado desde la identidad (Universal Auth → Add Client Secret) — **se muestra una sola vez**, cópialo de inmediato.

4. **`docker secret` externos**, en un manager (los secrets de Swarm son cluster-wide, no hace falta repetir por nodo):

   ```bash
   printf '%s' '<client-id>'     | ssh u-data@192.168.1.174 "docker secret create forgejo-infisical-client-id-v1 -"
   printf '%s' '<client-secret>' | ssh u-data@192.168.1.174 "docker secret create forgejo-infisical-client-secret-v1 -"
   printf '%s' '<project-id>'    | ssh u-data@192.168.1.174 "docker secret create forgejo-infisical-project-id-v1 -"
   ```

5. **DNS**, Pi-hole → Settings → Local DNS Records → añadir `forgejo.404labo.net` → `192.168.1.175`.

6. **Deploy**, patrón habitual (`CLAUDE.md`, "Deploying to a Docker Swarm stack"):

   ```bash
   rsync -av docker-swarm/stacks/forgejo/docker-compose.yml u-data@192.168.1.174:/tmp/forgejo-docker-compose.yml
   ssh u-data@192.168.1.174 "docker stack deploy -c /tmp/forgejo-docker-compose.yml forgejo --with-registry-auth"
   ```

7. **Verificación**: `docker service ls | grep forgejo` hasta ver `1/1`, y `curl -sk https://forgejo.404labo.net/api/healthz` debe responder `{"status": "pass", ...}`.

## Alta del usuario administrador — obligatorio antes de usarlo

Forgejo **no** crea un usuario admin automáticamente desde las variables `FORGEJO__*` — hace falta un paso explícito con la CLI dentro del propio contenedor, en el nodo donde haya aterrizado la tarea (`docker service ps forgejo_forgejo` para verlo, puede cambiar de nodo en cada redeploy al no tener `constraints`):

```bash
ssh u-<x>@<ip-del-nodo>   # ver docs/01-topologia.md, tabla de acceso SSH

docker ps --filter name=forgejo_forgejo --format '{{.Names}}'

docker exec -it <nombre-del-contenedor> forgejo admin user create \
  --username <usuario> \
  --password '<contraseña>' \
  --email <email> \
  --admin
```

Si `forgejo` no se reconoce como comando dentro del contenedor, usar `gitea` (mismo binario, alias histórico que Forgejo conserva desde su origen como fork de Gitea — `/usr/local/bin/gitea`). No hace falta `--config`: la imagen ya localiza `app.ini` sola (`WorkPath: /var/lib/gitea`).

**Hecho y verificado en vivo (2026-09-03)**: usuario admin creado, login confirmado en `https://forgejo.404labo.net`.

## Operación

- **Logs**: como el resto de stacks Swarm, vía driver `loki` — `docker service logs forgejo_forgejo` no muestra nada (limitación conocida del driver, ver `CLAUDE.md`), consultar Loki directamente (`grafana.404labo.net`, datasource Loki, `{swarm_stack="forgejo"}`).
- **Backup**: pendiente de definir un script dedicado — mientras tanto, todo el estado real vive en dos sitios ya cubiertos por sus propios mecanismos: el árbol de datos en `/volume1/nfs-data/forgejo/data` (NAS, RAID1+SAI, mismo criterio que el resto del volumen NFS) y la base de datos en `postgres-main` (`shared/scripts/backup-postgres.sh retaco <contenedor> forgejo`, patrón ya usado para n8n/SonarQube/apikeys).
- **Auto-actualización**: sin la label de watchtower a propósito, mismo criterio que el resto de servicios con estado del clúster (`CLAUDE.md`) — actualizar la imagen (`codeberg.org/forgejo/forgejo:X.Y.Z-rootless`) es un cambio deliberado, no automático.
- **Redeploy**: patrón habitual del punto 6 de "Instalación" — el servicio no tiene `constraints`, puede reaparecer en cualquiera de los 5 managers.
- **Placement observado en la práctica**: durante la depuración de esta primera ronda, el scheduler de Swarm movió la tarea entre `pinchi`, `pi-sonar` y de vuelta a `pinchi` sin ningún problema — a diferencia del hallazgo aún no diagnosticado con SonarQube en `pinchi` (colgado en el paso `infisical run`, ver cabecera de `docker-swarm/stacks/sonarqube/docker-compose.yml` y mejora 43), Forgejo arrancó limpio en los tres nodos, sin reproducir ese cuelgue.

## Pendiente / próximas rondas (mejora 7)

1. **7.2 — Migración incremental de repositorios**, GitHub como espejo de solo lectura (*push mirror*) — empezar por `homelab-cluster` mismo, luego el resto empezando por los menos críticos. No iniciado.
2. **7.3 — Forgejo Actions (CI)** — activar Actions a nivel de instancia, `forgejo-runner` (candidato: `ryzen`, más CPU), decidir superficie de acceso a Docker (docker-in-docker vs `docker.sock`, misma decisión de exposición ya tomada para `portainer-agent`/`watchtower`), integración con SonarQube. No iniciado.
3. **7.4 — Package Registry integrado** (OCI/npm/PyPI/genérico/Debian/Maven) como alternativa o complemento al `registry:2` standalone actual — evaluar cuando llegue esa fase, no urgente mientras el registry actual cumpla (`docs/29-registry-mantenimiento.md`).
4. Automatizar `make build` de los microservicios (`services/`) vía CI en cuanto exista Forgejo Actions — hoy sigue siendo un comando manual.
