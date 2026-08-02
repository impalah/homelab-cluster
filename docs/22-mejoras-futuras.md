# 22 — Mejoras futuras propuestas (backlog)

Este documento recoge propuestas de mejora identificadas en revisiones del clúster ya montado, **ninguna implementada todavía** (salvo que se indique lo contrario). Se listan por prioridad, con detalle suficiente para retomar cada una directamente cuando se decida, sin rediscutir el diseño desde cero.

---

## 1. Automatizar las copias de seguridad existentes y copiarlas fuera del nodo de origen

**Prioridad: alta**

### Qué hay hoy

`shared/scripts/backup-postgres.sh` y `shared/scripts/backup-vaultwarden.sh` funcionan y están documentados en `docs/12-backups-y-restore.md`, pero **no hay ningún cron activo** en ninguno de los 6 nodos. Cada copia de seguridad se guarda en `/srv/homelab/backups/<nodo>/`, en el **mismo disco físico** que los datos originales.

### Qué haría falta

1. Programar las copias de seguridad ya existentes mediante cron (sintaxis en `docs/12-backups-y-restore.md`).
2. Copiar las copias de seguridad fuera del nodo que las genera — rsync a otro nodo (simple, sigue "dentro de casa") o rclone a la nube (protege ante desastre físico total, decidir conscientemente qué sube si contiene algo sensible — Vaultwarden sobre todo).
3. Retención con `find ... -mtime +30 -delete`, también por cron.
4. Verificación periódica de restauración (trimestral) — una copia de seguridad nunca probada no es una copia de seguridad fiable.

### Esfuerzo estimado
Bajo (crons + destino de copia) a medio (con rclone/nube).

---

## 2. Poner el propio repositorio bajo control de versiones (y fuera de esta máquina)

**Prioridad: alta**

### Qué hay hoy

`homelab-cluster/` **no es un repositorio git**. Toda la configuración vive únicamente como ficheros sueltos en el disco de `mole`.

### Qué haría falta

1. `git init`, `.gitignore` para `.env` reales, commit inicial.
2. Remoto: privado en GitHub/GitLab/Codeberg, o autoalojado (revisar antes que ningún secreto real quedara en un fichero versionado — los `.env.example` son plantillas `CHANGE_ME`, deberían ser seguros).
3. Commits regulares a partir de ahora.

### Esfuerzo estimado
Muy bajo (15–30 min), alto impacto.

---

## 3. Alertas de espacio en disco

**Prioridad: media**

### Qué hay hoy

Prometheus ya recoge `node_filesystem_avail_bytes` en los 6 nodos — sin ninguna regla de alerta sobre ello. Solo existe la de undervoltage (`docs/14-monitorizacion-completa-cluster.md`).

### Qué haría falta

Mismo patrón que la alerta de undervoltage:

1. `pi-obs/config/grafana/alerting/disk-space.yml`, condición tipo `(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes) * 100 < 15`.
2. Montar en `docker-compose.yml` de `pi-obs`, `docker compose up -d --force-recreate grafana`.
3. Decidir: ¿solo panel, o correo/ntfy? Ver punto 4.

### Esfuerzo estimado
Bajo — reutiliza infraestructura y patrón existentes.

---

## 4. Canal de notificación proactivo (ntfy)

**Prioridad: media**

### Qué hay hoy

La alerta de undervoltage y el panel de actualizaciones pendientes son **solo de consulta** — nada avisa activamente. No existe ningún canal de notificación en todo el clúster.

### Qué haría falta

1. Desplegar **ntfy** en `pi-utils`, mismo patrón que Vaultwarden/Portainer (`docs/10-instalacion-pi4-utils.md` como referencia de estilo).
2. Exponer como `ntfy.home.arpa` mediante nginx.
3. App ntfy (Android/iOS/desktop), suscripción al topic del clúster.
4. Conectar como *contact point* de Grafana: undervoltage + futura alerta de disco.
5. Opcional: `check-image-updates.sh` publicando también por ntfy.

### Esfuerzo estimado
Medio.

---

## 5. Integrar el SAI existente con NUT (Network UPS Tools)

**Prioridad: media**

### Qué hay hoy

Ya existe un SAI físico, sin ninguna integración software — ningún nodo sabe si está con batería ni cuánta autonomía queda.

### Qué haría falta

1. Confirmar a qué equipo está conectado (probablemente `mole`/`ryzen`) — actúa de servidor NUT.
2. `nut-server` con `usbhid-ups` (cubre APC, Eaton, CyberPower).
3. `upsmon` en el resto de nodos como clientes remotos.
4. Política de apagado ordenado ante batería baja (`pi-dns` con especial cuidado).
5. Exponer métricas a Prometheus (`nut_exporter`).
6. Conectar avisos al canal de notificación del punto 4.

### Esfuerzo estimado
Medio — depende de la compatibilidad del SAI con `usbhid-ups`.

---

## 6. Migrar el tooling de mantenimiento a Ansible

**Prioridad: media**

### Qué hay hoy

Todo el mantenimiento se gestiona con scripts bash independientes por SSH. Funciona y cada script se ha verificado en vivo, pero: **inventario duplicado** (`update-os.sh`/`check-image-updates.sh` mantienen cada uno su propio mapa nodo→IP) y **sin idempotencia garantizada** (la clase de fallo que causó el incidente de `chown -R` rompiendo `postgres-main` en `retaco`, `docs/13-troubleshooting.md`).

### Qué haría falta

```
ansible/
├── ansible.cfg
├── inventory/hosts.yml
├── group_vars/{all.yml, <grupo>/vault.yml}
├── roles/{common, docker-engine, pi-dns, pi-obs, pi-sonar, pi-utils, retaco, ryzen}
└── playbooks/{site.yml, update-os.yml, update-stack.yml, backup.yml}
```

Migración incremental: `common` role primero (watchtower + node-exporter/cadvisor/portainer-agent, hoy copiado a mano en 6 ficheros) → `update-os.yml` → roles por nodo con `template`/`ansible-vault` → `prepare-host.sh` → `file` (idempotente por diseño, sin el bug de `chown -R`). `check-health.sh` y los `restore-*.sh` interactivos, peores candidatos, se quedan en bash.

Nodo de control: `pi-obs` ya tiene clave SSH dedicada a los 6 nodos, reutilizable.

### Esfuerzo estimado
Medio-alto — por volumen, no por dificultad. Abordar incrementalmente.

---

## 7. Forgejo autoalojado — repositorios, CI y artefactos

**Prioridad: media**

### Qué hay hoy

Todo el código vive en GitHub. Intención: migrar a Forgejo autoalojado como sistema principal, GitHub como espejo mientras haga falta.

### Qué haría falta

#### 7.1 Instalación

1. Nodo: `pi-utils` (encaja por rol, pero puede pedir más recursos) o `retaco` (siempre encendido, ya multi-tenant — probablemente la opción más sensata).
2. Base de datos: Postgres, `create-postgres-db.sh postgres-main dbadmin forgejo forgejo`, mismo patrón que n8n/SonarQube/apikeys.
3. `forgejo.home.arpa` mediante nginx, mismo procedimiento de siempre.
4. SSH de Forgejo en puerto alternativo (`2222`, no `22` — ya usado por el `sshd` de administración de cada nodo).
5. Copia de seguridad del árbol de repos (`/data/git`) aparte de la base de datos.

#### 7.2 Migración incremental, GitHub como espejo

1. Empezar por este mismo repositorio (`homelab-cluster`), en cuanto exista el punto 2.
2. Resto, repo a repo, empezando por los menos críticos.
3. **Forgejo como fuente de verdad, GitHub como espejo de solo lectura** (*push mirror*) — evita conflictos de sincronización bidireccional.

#### 7.3 CI (Forgejo Actions)

1. Activar Actions a nivel de instancia.
2. `forgejo-runner` en `ryzen` (más CPU).
3. Acceso a Docker si se build-ean imágenes (docker-in-docker o `docker.sock`, misma decisión de superficie que `portainer-agent`/`watchtower`).
4. Sintaxis compatible en buena parte con GitHub Actions.
5. Integración con SonarQube (`docs/09-instalacion-pi3-sonarqube.md`) — un paso `sonar-scanner` cierra el círculo de calidad.

#### 7.4 Almacenamiento de artefactos

**Ya no es futuro, está hecho** — el registry Docker (`registry.home.arpa`, en `retaco`) se instaló como paso independiente, sin esperar al resto de Forgejo (`docs/05-instalacion-retaco.md` sección 5.3). Los tres microservicios (`apikey-service`, `markitdown-service`, `whisper-service`, en `services/` en la raíz del repo) se publican ahí mediante `make build` en cada uno; ningún `docker-compose.yml` de ningún nodo los construye ya, todos hacen `image: registry.home.arpa/<nombre>:latest` + `pull`. Esto también resuelve la limitación ya documentada en `docs/16-mantenimiento-actualizaciones.md` en cuanto se integre con `check-image-updates.sh` (todavía no revisado si el script ya los detecta correctamente al venir de un registry propio en vez de Docker Hub — pendiente de comprobar, no bloqueante).

La compilación cruzada (`pi-dns`/`pi-utils` son ARM64, se compila normalmente desde x86) también está resuelta para `apikey-service`/`markitdown-service` mediante `docker buildx build --platform linux/amd64,linux/arm64 --push` + emulación QEMU (`whisper-service` se queda solo amd64 a propósito — necesita GPU NVIDIA, que las Pi no tienen). Detalle completo, incluida una CA interna que hay que instalar a mano dentro del contenedor del builder de `buildx` (no hereda la del host) y el hecho de que cada nodo consumidor necesita la CA a nivel de sistema + `docker login`: `docs/05-instalacion-retaco.md` sección 5.3.

Lo que sigue pendiente de esta sección original:

1. Si además se quiere un Package Registry integrado en el propio Forgejo (OCI, npm, PyPI, genérico, Debian, Maven...) en vez del `registry:2` standalone actual, evaluarlo cuando llegue esa fase — no es urgente mientras el `registry:2` cumpla.
2. Automatizar el propio `make build` (disparo por webhook/CI en vez de manual) — sigue siendo un comando que hay que correr a mano tras cada cambio de código; eso es lo que de verdad falta para llamarlo "CI" y no solo "registry con build manual".

### Esfuerzo estimado
Alto — sobre todo por el volumen de migrar repositorios uno a uno, montar/probar CI, y decidir la estrategia de sincronización con calma. Abordar por fases.

---

## 8. Registry — limpieza y garbage collection

**Prioridad: media**

### Qué hay hoy

`registry.home.arpa` (contenedor `registry:2.8.3` en `retaco`, ver `docs/05-instalacion-retaco.md` sección 5.3) está desplegado y en uso, con `REGISTRY_STORAGE_DELETE_ENABLED=true` (deja la API DELETE lista) — pero **sin ninguna rutina de limpieza**. Cada `docker push` de una imagen con el mismo tag (p. ej. `:latest`) dobla el consumo de disco: el registry no sobrescribe capas antiguas automáticamente, solo deja de referenciarlas desde el manifest — quedan huérfanas hasta que algo las recolecte. Con imágenes como `whisper-service` (base `nvidia/cuda`, varios GB) esto crece rápido si se despliega con frecuencia.

Tampoco está cubierto por ninguna copia de seguridad (`shared/scripts/backup-*.sh` solo cubren Postgres y Vaultwarden) — `/srv/homelab/retaco/registry/data` no se respalda todavía; en principio no es grave (las imágenes se pueden reconstruir desde el código fuente), pero merece una decisión consciente, no un olvido.

### Qué haría falta

1. **Garbage collection periódico**: `docker exec registry bin/registry garbage-collect /etc/docker/registry/config.yml` (requiere `--dry-run` primero para revisar qué borraría) — programado por cron, con el contenedor parado o en modo solo-lectura durante la ejecución (el propio comando lo exige para no correr contra un registry recibiendo pushes a la vez).
2. **Política de retención de tags**: decidir cuántas versiones antiguas conservar por imagen (p. ej. últimas 3–5) antes de dejar que el GC las recolecte — sin esto, cada imagen solo tendría `:latest`, perdiendo la capacidad de rollback que fue una de las razones para montar el registry.
3. **Copia de seguridad de `/srv/homelab/retaco/registry/data`** (o decisión explícita de no respaldarlo, documentada) — encaja con el punto 1 de este mismo documento (copias de seguridad automatizadas) en cuanto se aborde.
4. **Alerta de espacio en disco específica** si crece más de lo esperado — reutiliza el patrón de la mejora 3 de este documento.

### Esfuerzo estimado
Bajo — es principalmente cron + decidir la política de retención, no hay pieza de infraestructura nueva que montar.

---

## 9. Tailscale — política de ACL

**Prioridad: baja**

### Qué hay hoy

Acceso remoto mediante Tailscale ya desplegado (`docs/18-tailscale.md`, subnet
router en `pi-dns`) — sin ACL personalizada, comportamiento por defecto:
cualquier dispositivo autenticado en el tailnet llega a todo el clúster.
Suficiente mientras el tailnet tenga un único usuario/cuenta.

### Qué haría falta

1. Decidir si conviene restringir por dispositivo/usuario (p. ej. un
   dispositivo de invitado que solo debería llegar a `open-webui`, no a
   `vaultwarden` o `postgresql.home.arpa`).
2. Escribir una política de ACL (tags + reglas) en el editor de políticas
   del panel de Tailscale — no es un fichero de este repo, vive en la
   configuración del tailnet.
3. Etiquetar el nodo `pi-dns` (p. ej. `tag:subnet-router`) para que la
   auth key deje de estar ligada a la cuenta personal — más robusto a
   largo plazo que una key de usuario.

### Esfuerzo estimado
Bajo-medio — configuración, no código; el esfuerzo real es decidir la
política, no aplicarla.

---

## 10. NAS UGREEN — migrar `nfs-data` a NFSv4

**Prioridad: baja**

### Qué hay hoy

NFSv3 funciona perfectamente para `nfs-data` (root sin squash, confirmado
en uso real con bind mounts de Docker) — ver
`docs/21-configuracion-nas-ugreen.md`. NFSv4 se negocia a nivel de kernel
(`/proc/fs/nfsd/versions` muestra `+4`), pero los montajes v4 fallan con
`No such file or directory` porque UGOS Pro no expone un pseudo-root de
NFSv4 (`fsid=0`) en el `/etc/exports` que genera desde la GUI. Sin
urgencia — v3 cubre el uso actual sin problema, se retoma cuando apetezca.

### Qué haría falta

1. Confirmar el mecanismo real que usa UGOS Pro para generar
   `/etc/exports` (¿desde `nfs.json`, igual que `nfs.conf`, o desde otro
   sitio?) antes de tocarlo a mano — mismo riesgo ya conocido de que la
   GUI lo sobrescriba en cuanto se vuelva a tocar esa pantalla.
2. Añadir a mano, por SSH, un export raíz con `fsid=0` (p. ej. algo del
   estilo `/volume1 192.168.1.0/24(ro,fsid=0,no_subtree_check)`, o el
   ajuste equivalente si UGOS Pro expone alguna opción para esto en la
   GUI que no se haya encontrado todavía).
3. Probar montaje v4 desde un cliente Linux con la ruta relativa a esa
   raíz (no la ruta real `/volume1/nfs-data` usada hoy con v3).
4. Si funciona: actualizar `docs/21-configuracion-nas-ugreen.md` y el
   `/etc/fstab` de los clientes que usen `nfs-data`.
5. Si UGOS Pro no lo permite de forma estable (revierte el export raíz al
   tocar la GUI): documentar como limitación permanente del NAS y
   descartar el punto, quedándose en v3 definitivamente.

### Esfuerzo estimado
Bajo-medio — la parte técnica es sencilla si UGOS Pro lo permite; la
incertidumbre real es si la GUI lo revierte.

---

## Resumen

| # | Mejora | Prioridad | Esfuerzo | Depende de |
|---|---|---|---|---|
| 1 | Automatizar las copias de seguridad y copiarlas fuera de nodo | Alta | Bajo–medio | — |
| 2 | `git init` del repo + remoto | Alta | Muy bajo | — |
| 3 | Alerta de espacio en disco | Media | Bajo | Reutiliza patrón de `docs/14` |
| 4 | ntfy (notificaciones proactivas) | Media | Medio | — |
| 5 | Integración NUT del SAI existente | Media | Medio | Modelo de SAI compatible con `usbhid-ups` |
| 6 | Migrar tooling de mantenimiento a Ansible | Media | Medio-alto | Punto 2 |
| 7 | Forgejo (repos + CI + artefactos), con GitHub como espejo | Media | Alto | Punto 2 |
| 8 | Registry: limpieza y garbage collection | Media | Bajo | Registry ya desplegado (`docs/05`) |
| 9 | Tailscale: política de ACL | Baja | Bajo-medio | Tailscale ya desplegado (`docs/18`) |
| 10 | NAS UGREEN: migrar `nfs-data` a NFSv4 | Baja | Bajo-medio | NAS ya configurado en NFSv3 (`docs/21`) |

Ninguna de estas mejoras es urgente ni bloqueante — el clúster funciona correctamente sin ellas.
