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

## 2. ~~Poner el propio repositorio bajo control de versiones (y fuera de esta máquina)~~ — hecho

**Prioridad: alta** — **completado**

### Qué hay hoy

`homelab-cluster/` ya es un repositorio git, con `.gitignore` (excluye `.env` reales, `.venv/`, cachés de herramientas y demás ficheros que no deben versionarse) y remoto en GitHub: [`github.com/impalah/homelab-cluster`](https://github.com/impalah/homelab-cluster). Commit inicial hecho y verificado sin secretos colados.

### Qué haría falta

Nada — se mantiene este punto en el documento solo como constancia histórica del backlog. Sí queda como hábito pendiente: hacer commits regulares a partir de ahora, en vez de dejar que se acumulen cambios sin versionar durante semanas.

---

## 3. ~~Alertas de espacio en disco~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

`pi-obs/config/grafana/alerting/disk-space.yml`, mismo patrón que `undervoltage.yml` (`docs/14-monitorizacion-completa-cluster.md`), condición literal propuesta aquí: `(node_filesystem_avail_bytes{fstype!~"tmpfs|overlay"} / node_filesystem_size_bytes) * 100 < 15`. Verificado en vivo contra Prometheus antes de escribir la regla (no asumido): los `fstype` reales en los 6 nodos son `ext4`/`vfat`/`tmpfs`/`nfs`, sin `overlay`/`squashfs` que hubieran dado falsos positivos — ninguno está hoy cerca del umbral (mínimo real observado ~33% libre en raíces, ~98% libre en el NFS compartido `/mnt/nfs-data`), así que la regla se desplegó sin disparar nada. `for: 5m` e `interval: 1m` (a diferencia del `for: 0s`/10s de undervoltage) — el espacio en disco se acumula durante horas/días, no es un evento puntual como un corte de tensión.

Punto 3 original ("¿solo panel, o correo/ntfy?"): decidido a favor de ntfy, ya disponible tras la mejora 4 — `category: disk` añadida al matcher de `pi-obs/config/grafana/alerting/notification-policies.yml` (`power|hardware` → `power|hardware|disk`), verificado en la UI real de Grafana (**Alerting → Notification policies**) que la ruta queda provisionada y apuntando a `ntfy-cluster-alerts`, y en **Alerting → Alert rules** que la regla evalúa 17 instancias (una por combinación nodo/sistema de ficheros real) en estado `Normal`.

### Qué hay hoy (histórico, previo a la implementación)

Prometheus ya recogía `node_filesystem_avail_bytes` en los 6 nodos — sin ninguna regla de alerta sobre ello. Solo existía la de undervoltage (`docs/14-monitorizacion-completa-cluster.md`).

### Esfuerzo estimado
Bajo — reutiliza infraestructura y patrón existentes.

---

## 4. ~~Canal de notificación proactivo (ntfy)~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

**ntfy** desplegado como stack Swarm (`docker-swarm/stacks/ntfy/`, no en `pi-utils`/nginx como se planteaba originalmente — ese plan es de antes del cierre de la migración a Swarm y de la retirada de `home.arpa`, mejoras 33/39/41). Sin `node.hostname` fijo — `node.labels.role == stateful` (`retaco`/`pinchi`, destino por defecto de cualquier servicio nuevo con estado, `docs/31-docker-swarm.md`). Expuesto en `ntfy.404labo.net` vía Traefik (labels de descubrimiento en el propio stack, mismo patrón que `markitdown`), auth propia con `NTFY_AUTH_DEFAULT_ACCESS=deny-all` (sin topics públicos). Desplegado y verificado en vivo (2026-09-01) en el clúster real, no solo en el repo: healthcheck sano, DNS cargado en Pi-hole, usuario/token del topic `homelab-alerts` creados con `ntfy user`/`ntfy access`/`ntfy token`.

Conectado como *contact point* de Grafana (`pi-obs/config/grafana/alerting/ntfy-contactpoint.yml` + `notification-policies.yml`): las alertas de undervoltage, del SAI (`docs/33-nut-sai.md`) y de espacio en disco (mejora 3, cerrada el mismo día, `category` en `power|hardware|disk`) ya enrutan hacia ntfy. `shared/scripts/check-image-updates.sh` también publica por ntfy si se exporta `NTFY_TOKEN` (punto 5 original, opcional, implementado). **Incidente real encontrado y corregido probándolo de verdad con el botón "Test" de Grafana**: la primera versión del contact point usaba el token de ntfy como contraseña de HTTP Basic Auth — Grafana lo provisionó sin quejarse, pero dio `401 Unauthorized` real al enviar (los tokens de ntfy solo valen como `Authorization: Bearer`); corregido usando el campo dedicado "Authorization Header" de Grafana (`authorization_scheme`/`authorization_credentials`, soportado desde la 9.1, muy anterior a la 10.4.2 de este clúster). Confirmado end-to-end tras el fix: "Test alert sent." en Grafana y la notificación real recibida en la app de ntfy.

Documentación completa (despliegue, alta de usuarios/tokens, todos los sistemas de notificación disponibles —web/PWA/apps/CLI/API HTTP para suscripción externa—, y cómo conseguir push nativo de verdad en cada plataforma —Firebase/Android, relé de sondeo/iOS, Web Push/navegador, ninguno activado todavía—, más ejemplos concretos en Python/n8n para integrarlo desde fuera del clúster): `docs/34-ntfy-notificaciones.md`.

### Qué hay hoy (histórico, previo a la implementación)

La alerta de undervoltage y el panel de actualizaciones pendientes eran **solo de consulta** — nada avisaba activamente. No existía ningún canal de notificación en todo el clúster.

### Esfuerzo estimado
Medio.

---

## 5. ~~Integrar el SAI existente con NUT (Network UPS Tools)~~ — hecho

**Prioridad: media**

### Qué hay hoy

**Completado (2026-09-01)** — ver `docs/33-nut-sai.md` para el detalle completo. El SAI
(Salicru SPS 2200 SOHO+) resultó estar conectado a `pi-obs`, no a `mole`/`ryzen` como
suponía este documento originalmente. Servidor NUT (`usbhid-ups`) en `pi-obs`, clientes
`upsmon` en los 6 nodos con apagado real vía D-Bus/logind (validado con hardware real en
`pinchi`), métricas en Prometheus (`nut_exporter`) y alerta en Grafana
(`sai-bateria.yml`). El aviso al canal de notificación (punto 6 original) quedó cerrado
el mismo día al implementarse la mejora 4 (`ntfy`) — `sai-bateria.yml` ya enruta a ntfy
vía `pi-obs/config/grafana/alerting/notification-policies.yml`, ver `docs/34-ntfy-notificaciones.md`.

### Qué haría falta

1. ~~Confirmar a qué equipo está conectado (probablemente `mole`/`ryzen`) — actúa de servidor NUT.~~
2. ~~`nut-server` con `usbhid-ups` (cubre APC, Eaton, CyberPower).~~
3. ~~`upsmon` en el resto de nodos como clientes remotos.~~
4. ~~Política de apagado ordenado ante batería baja (`pi-dns` con especial cuidado).~~
5. ~~Exponer métricas a Prometheus (`nut_exporter`).~~
6. ~~Conectar avisos al canal de notificación del punto 4 — pendiente de la mejora 4 (`ntfy`).~~

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

**Decisión de secuenciación (2026-08-24)**: se planteó abordar Forgejo como parte de la migración a Docker Swarm (mejora 33, `docs/31-docker-swarm.md`) — servicio nuevo, sin legado Compose, buena validación de bajo riesgo del patrón `constraints`+bind-mount. El usuario decidió sacarlo de esa migración explícitamente: Forgejo se aborda en su propio esfuerzo, **después** de que el clúster esté migrado a Swarm por completo y el DNS esté resuelto — no antes, no mezclado con la migración a Swarm. Sin dependencia técnica añadida hacia la mejora 33 más allá de esto. Con el Swarm cerrado (mejora 33/39) y el DNS ya en `404labo.net` (mejora 41), esta precondición está cumplida — se retoma el 2026-09-03.

### 7.1 Instalación — primera ronda (2026-09-03), solo núcleo

Abordada explícitamente "poco a poco" (petición del usuario) — esta ronda cubre únicamente Forgejo en sí (web + git HTTPS/SSH), no la migración de repos (7.2) ni Forgejo Actions/CI (7.3), que quedan para rondas de decisión posteriores. Fichero: `docker-swarm/stacks/forgejo/docker-compose.yml`.

Decisiones tomadas (todas confirmadas por el usuario antes de tocar nada):

1. **Docker Swarm desde el primer despliegue, sin Compose clásico** — el planteamiento original de este documento (nodo fijo `pi-utils`/`retaco`) queda superado por el patrón consolidado en la mejora 47: volumen Docker `driver: local` + `driver_opts: type: nfs` contra el NAS (`ketekasko`, `/volume1/nfs-data/forgejo/data`), portable entre los 5 managers **sin `constraints` de nodo** desde el día uno — no hay legado que migrar, así que no hace falta pasar primero por bind-mount+nodo fijo como sí tuvo sentido para los servicios de la Fase 4.
2. **Base de datos: Postgres en `postgres-main`** (rol aislado `forgejo`/BD `forgejo`, creado ya con `create-postgres-db.sh postgres-main dbadmin forgejo forgejo`), no SQLite embebido — mismo criterio que el resto del clúster: SQLite tendría escritura real y frecuente aquí (a diferencia del SQLite vestigial que sí se aceptó en n8n-aux/open-webui en la mejora 47).
3. **Imagen rootless** (`codeberg.org/forgejo/forgejo:16.0.3-rootless`, versión fijada, no `latest`) — uid/gid 1000 de fábrica, coherente con el resto del clúster (n8n/SonarQube). Directorio de datos real de esta variante: `/var/lib/gitea`, no `/data`.
4. **Git por SSH en el puerto 2222**, además de HTTPS — publicado directo (`mode: ingress`, sin pasar por Traefik, mismo bypass que ya usa `registry` para su propio protocolo no-HTTP). La imagen rootless ya escucha ahí por defecto (no puede bindear el 22 privilegiado sin root).
5. Secretos (contraseña de Postgres, credenciales de Infisical) — mismo patrón que el resto del clúster: `docker secret` + `infisical run`, nunca en claro en este repo.

**Hecho y verificado en vivo (2026-09-03)** — instalación núcleo completa, `https://forgejo.404labo.net` accesible y con usuario admin funcionando. Documentación completa (arquitectura, comandos exactos, operación) en su propio documento: `docs/36-forgejo-repositorios-git.md`, no repetida aquí.

Ejecutado por Claude de punta a punta en esta ronda (incluidos los pasos que en la mejora 45 habían quedado como acción manual del usuario — aquí, con acceso a `claude-in-chrome`, Claude pudo operar también la UI de Infisical/Pi-hole): directorio NFS preparado y con owner correcto; rol y base de datos Postgres creados; proyecto/carpeta/secreto en Infisical; identidad de máquina + client secret; los tres `docker secret` en Swarm; registro DNS cargado en Pi-hole; `docker stack deploy`; y, con el usuario ejecutando solo el paso con contraseña (por norma de seguridad, Claude no maneja contraseñas), el alta del usuario administrador.

**Incidente real encontrado y resuelto durante el despliegue**: el `healthcheck` del compose comparaba la respuesta de `/api/healthz` contra el patrón `"status":"pass"` (sin espacio), pero el JSON real de Forgejo lleva espacio tras los dos puntos (`"status": "pass"`) — el healthcheck fallaba siempre pese a que el servicio respondía bien, y Swarm mataba y reprogramaba la tarea cada ~2-3 minutos creyéndola no sana (síntoma colateral: el router de Traefik nunca llegaba a aparecer, lo que inicialmente hizo sospechar —incorrectamente— de un problema de red/labels). Detalle completo de la investigación y el arreglo en `docs/36-forgejo-repositorios-git.md`.

#### 7.2 Migración incremental, GitHub como espejo

1. Empezar por este mismo repositorio (`homelab-cluster`), en cuanto exista el punto 2.
2. Resto, repo a repo, empezando por los menos críticos.
3. **Forgejo como fuente de verdad, GitHub como espejo de solo lectura** (*push mirror*) — evita conflictos de sincronización bidireccional.

#### 7.3 CI (Forgejo Actions) — runners, primera ronda (2026-09-04)

Dos runners, decisión explícita del usuario (2026-09-04), ambos con modo de ejecución `docker://`
(cada job en un contenedor nuevo vía sidecar `docker:dind` propio, **nunca** el socket Docker real
del host en ninguno de los dos — ver justificación de seguridad más abajo):

1. **`forgejo-runner-pinchi`** — siempre en ejecución, **runner por defecto**. Corre en Compose
   CLÁSICO directo en el host (`pinchi/docker-compose.yml`, junto a `nut-upsmon`), NO como stack
   Swarm — la intención inicial era un stack Swarm de verdad (decisión original del usuario),
   descartada tras una prueba real en vivo, ver el aparte de más abajo ("Por qué no es un stack
   Swarm"). Etiquetas `docker`/`ubuntu-latest`/`ubuntu-22.04` (imágenes
   `ghcr.io/catthehacker/ubuntu:act-latest`/`act-22.04`) — recoge cualquier workflow que no pida
   explícitamente otra cosa. `restart: unless-stopped` basta para "siempre en ejecución" incluida
   la persistencia tras un reinicio del host.
2. **`forgejo-runner-ryzen`** — lanzamiento manual, Compose clásico
   (`ryzen/docker-compose.forgejo-runner.yml`, mismo patrón que `switch-llm-backend.sh`: nunca
   arranca solo). Etiqueta propia y distinta, `ryzen` (no comparte `ubuntu-latest`/`docker` con
   pinchi a propósito) — así los workflows genéricos van siempre al runner por defecto, y este
   solo recibe jobs que lo pidan explícitamente (`runs-on: ryzen`), sin competir por trabajos
   normales cuando esté encendido. Pensado para CPU/RAM libres cuando el nodo ya está arriba por
   otro motivo, no para tenerlo encendido solo para CI.

**Por qué `forgejo-runner-pinchi` NO es un stack Swarm, pese a ser la decisión inicial**: probado
en vivo (2026-09-04) como stack Swarm real primero — falló en crash-loop. **Docker Swarm no puede
ejecutar contenedores privilegiados, en ningún caso.** `privileged: true` se ignora en silencio
("Ignoring unsupported options: privileged" en el propio `docker stack deploy`). Se intentó
reconstruir el mismo conjunto de permisos a mano (`cap_add: [ALL]` + `security_opt:
[seccomp=unconfined, apparmor=unconfined]` + bind-mount de `/sys/fs/cgroup`, todo verificado antes
por separado con `docker run` normal, donde sí funciona) — `cap_add` **sí** se aplica en modo
Swarm, pero `security_opt` **también** se ignora en silencio ("Ignoring unsupported options:
security_opt"), y sin él el perfil seccomp por defecto bloquea `mount()`, syscall imprescindible
para que un `dockerd` anidado arranque. Confirmado además que `docker service create --help` ni
siquiera tiene un flag `--security-opt` — no es una limitación de sintaxis del compose, el propio
modelo de Swarm no expone ese control. Limitación real y documentada de Swarm en general (Docker-
in-Docker no funciona en modo Swarm), no específica de este clúster — y coincide, además, con un
hallazgo ya real y anterior en este mismo repo: `pinchi/docker-compose.yml` ya existía por el
mismo motivo exacto para `nut-upsmon` (mejora 5, `docs/33-nut-sai.md`, 2026-09-01), que necesita
`privileged: true` para D-Bus real. Se optó por añadir `forgejo-runner-pinchi` + su sidecar `dind`
a ese mismo fichero en vez de crear un stack Swarm nuevo — la excepción de `pinchi` a estar
gestionado por Swarm ya existía, esto la reutiliza en vez de duplicarla. Coherente con lo que el
usuario ya había anticipado en la petición original de este punto ("si no es posible usar Docker
Swarm, pinchi es el nodo más adecuado").

**Decisión de seguridad tomada explícitamente (2026-09-04): sin acceso a GPU en ningún runner.**
Se evaluó montar el socket Docker real de `ryzen` para que los jobs pudieran pedir `--gpus` igual
que `ollama`/`vllm` — descartado: cualquier workflow con permiso de escritura sobre un repo con
Actions tendría entonces control total del host mientras el runner esté arriba (equivalente a
acceso root), y el modelo de amenaza de Forgejo Actions asume que quien puede hacer push a un repo
puede ejecutar código arbitrario en el runner que lo sirve. Los dos runners usan el mismo sidecar
`docker:dind` aislado — si en el futuro hace falta GPU en CI (tests de `whisper-service`/`vllm`,
por ejemplo), revisar esta decisión aparte, con los ojos abiertos sobre ese coste.

**Registro: OFFLINE, no interactivo** (`forgejo forgejo-cli actions register --name <nombre>
--secret <40 hex>`, disponible desde Forgejo ≥ 1.21) — permite generar el secreto nosotros mismos
y registrar ambos runners desde dentro del propio contenedor `forgejo` (que ya trae el binario
`forgejo` y el CLI de `infisical` embebidos) sin depender de la UI web ni de un token de un solo
uso. Comando idempotente — reejecutarlo con el mismo secreto no rompe nada. Los dos runners están
registrados **sin `--scope`** (globales, visibles para todos los repos de la instancia) — el
filtrado de qué runner ejecuta qué job se hace por etiquetas (`runs-on:`), no por scope.

**Credenciales — sin Infisical en ninguno de los dos**, a propósito. La idea inicial era usar
Infisical al menos para `forgejo-runner-pinchi` (por ser, en teoría, un stack Swarm declarativo) —
al pasar también a Compose clásico (ver más arriba), esa justificación desapareció, así que se
simplificó para quedar simétrico con `ryzen`: `.env` real (no versionado, solo en el host) con
`FORGEJO_RUNNER_UUID`/`FORGEJO_RUNNER_TOKEN`, `.env.example` con placeholders versionado
(`pinchi/.env.example`, junto a `NUT_MONUSER_PASSWORD`; `ryzen/.env.forgejo-runner.example`,
aparte del `.env.example` del stack de IA). De paso evita depender de que `pinchi`/`ryzen` tengan
sincronizados el binario y la CA de Infisical (no es el caso de `ryzen` hoy).

*(Nota histórica: durante el diseño se llegaron a crear las carpetas `/forgejo-runner-pinchi/` y
`/forgejo-runner-ryzen/` en Infisical —proyecto `forgejo`, entorno `prod`— con estos mismos
secretos dentro, incluyendo ampliar el rol de la identidad de máquina a Admin para poder crearlas
desde CLI sin acceso a la UI. Al descartarse Infisical para ambos runners, esas carpetas se
borraron de nuevo — no quedó nada huérfano.)*

**Validado en vivo de punta a punta (2026-09-04) para los dos runners**: contenedor arrancado,
registrado y visible `online` en la tabla `action_runner` de Postgres; desde dentro de la red
anidada del propio `dind` (`docker -H tcp://127.0.0.1:2375 run ghcr.io/catthehacker/ubuntu:act-
latest ...`), resolución DNS correcta de `forgejo.404labo.net` contra Pi-hole
(`--dns=192.168.1.170` explícito en el `dockerd` del sidecar — sin esto los contenedores de cada
job no resuelven `*.404labo.net`, un `dockerd` anidado no hereda el DNS del host) y `HTTP/2 200`
real contra `/api/healthz`. El de `ryzen` se probó primero y se paró después (arranque manual es
la idea — no se deja corriendo de fondo); el de `pinchi` se dejó arriba (es el runner por
defecto, siempre en ejecución).

**Caché de Actions desactivada a propósito en esta primera ronda** (`cache.enabled: false` en los
dos) — la caché la sirve el propio proceso `runner`, pero los contenedores de cada job viven
*dentro* de la red anidada de `dind`, no en la red del runner; alcanzar ese proxy desde ahí
necesitaría fijar `cache.host` a una IP alcanzable desde esa red anidada, no investigado todavía.
Sin caché, los jobs no aceleran `npm ci`/`pip install` entre ejecuciones — funcionalmente
correcto, solo más lento. Revisar cuando el uso real de Actions lo justifique.

**Hecho y verificado en vivo (2026-09-04)** — los dos runners desplegados y `online`:
`forgejo-runner-pinchi` arriba de forma permanente (`pinchi/docker-compose.yml`, junto a
`nut-upsmon`), `forgejo-runner-ryzen` parado tras la prueba (arranque manual, ver
`ryzen/docker-compose.forgejo-runner.yml`).

**Pendiente de esta ronda**:
1. Probar con un workflow real, no solo con `docker run` a mano — `container.docker_host:
   "automount"` ya está puesto en los dos runners (para que un `step:` pueda hacer `docker
   build`/`buildx push` dentro de un job, necesario en cuanto la mejora 7.2 traiga este mismo
   repo y su `make build` de `services/`), sin probar todavía con un workflow de verdad.
2. Integración con SonarQube (`docs/09-instalacion-pi3-sonarqube.md`) — un paso `sonar-scanner`
   cierra el círculo de calidad. No abordado en esta ronda.
3. Cerrar `DISABLE_REGISTRATION` (ver hallazgo de seguridad más abajo, en 7.4) — evaluado y
   descartado para esta ronda a petición explícita del usuario (2026-09-04); queda pendiente para
   una ronda posterior.

**Investigado (2026-09-03), sin implementar todavía — dónde corre el runner y cómo se define, para cuando se aborde este punto de verdad:**

- **El runner es un proceso totalmente aparte del servidor Forgejo** — binario/imagen distinto (`forgejo-runner`), instalado donde se quiera (binario + `systemd`, o contenedor con la imagen `data.forgejo.org/forgejo/runner:<versión>`). Es el runner quien se conecta *hacia fuera* a `forgejo.404labo.net` — sin puerto entrante ni DNS propio que gestionar, solo salida HTTPS. Encaja como servicio Compose clásico en `ryzen` (candidato ya apuntado en el punto 2), no como stack Swarm.
- **Registro**: el token se genera desde la UI de Forgejo, con el alcance elegido explícitamente — instancia completa (`/admin/actions/runners`, solo admin), una organización, un usuario, o un repositorio concreto (`Configuración del repo → Acciones → Nodos`, ya visto en `docs/forgejo/03-repositorios.md`). El alcance determina qué workflows puede recoger ese runner en concreto. El comando clásico `forgejo-runner register` está deprecado a favor de un subcomando más nuevo (`actions register`) — confirmar la sintaxis exacta en la documentación oficial en el momento de implementarlo, no fiarse de una nota de hace tiempo.
- **Configuración del runner** (qué etiquetas acepta, modo de ejecución, caché, credenciales de conexión) vive en un `config.yaml` **local a la máquina del runner** (generado con `forgejo-runner generate-config`) — no en el almacenamiento de Forgejo, así que no interfiere con el volumen NFS de la mejora 7.4.
- **Cómo se ejecutan los steps de un job — esto es lo que resuelve de verdad el punto 3**: cada "etiqueta" del runner mapea un nombre (el que usa `runs-on:` en el workflow) a un modo de ejecución: `docker://imagen`/`lxc://...` (cada job arranca en un contenedor aislado nuevo — necesita que el runner tenga acceso a Docker, vía un sidecar `docker:dind` propio, **no** el `docker.sock` real del host, mismo criterio de aislamiento ya aplicado en este clúster a `portainer-agent`/registry) o `host` (los pasos corren directos en el SO del runner, **sin aislamiento** — advertencia explícita de la documentación oficial: "un solo job puede destruir el host de forma permanente"). Decisión para cuando se implemente: `docker://` con `dind` en un contenedor propio, nunca `host` como modo por defecto ni el `docker.sock` real de `ryzen`.
- **No hace falta un runner activo todo el rato — el modelo es "pull", el runner conecta hacia fuera**: mientras no haya ningún runner conectado con las etiquetas que pide un job, ese job se queda en estado `waiting` en la cola indefinidamente (no falla, no se pierde). Esto habilita varias formas de operar sin gasto de recursos permanente, de menos a más automatizado:
  1. **Manual** — sin runner por defecto; se arranca el contenedor a mano justo antes de necesitar CI, recoge lo pendiente, se para después. Sin configuración especial.
  2. **Aprovechando el Wake-on-LAN ya existente de `ryzen`** (`docs/19-wake-on-lan.md`, `shared/scripts/wake-mole.sh`) — si el runner vive ahí, "despertar `ryzen` + arrancar el runner" es una extensión natural del mismo gesto que ya se usa para las tareas de GPU.
  3. **Runners efímeros bajo demanda, sin intervención manual** — un script/temporizador que consulta `GET /api/v1/repos/<owner>/<repo>/actions/runners/jobs` buscando jobs en `waiting`, y cuando encuentra uno, registra un runner con `ephemeral: true` y lo lanza con `forgejo-runner one-job` apuntando a ese job — Forgejo lo borra solo al terminar, nada queda residente. Existe una variante "nativa" vía KEDA (tiene un *scaler* específico para Forgejo), pero requiere Kubernetes — este clúster no lo usa hoy (aparte está la mejora, todavía no iniciada, de k3s sobre VMs en el backlog, sin relación con esta decisión).
  - **Recomendación**: opción 1 o 2 de sobra para el uso esporádico esperado en un homelab — la 3 es infraestructura real a construir/mantener por un beneficio (latencia cero) que probablemente no compensa todavía. Revisar si el uso de Actions crece.
  - **Decisión (2026-09-03)**: lanzamiento manual (opción 1) — arrancar el runner a mano en el nodo que convenga en cada momento, sin fijarlo de antemano a `ryzen` en concreto. Sin más desarrollo por ahora; se retoma cuando se aborde 7.3 de verdad.
- **Persistencia de lo instalado durante un job (Docker, `aws cli`, cualquier paquete) — depende por completo del modo de ejecución de arriba**: con `docker://` (el modo elegido para este clúster), cada job arranca un contenedor **nuevo** desde la imagen indicada y ese contenedor se destruye al terminar — todo lo instalado en los `steps:` desaparece con él, el siguiente job vuelve a partir limpio, sin deriva de estado ni conflictos entre proyectos (mismo modelo que los runners alojados de GitHub Actions). Matices:
  - La **imagen base** sí queda cacheada por capas en el sidecar `docker:dind` entre jobs (por rendimiento, evita redescargarla) — pero es solo el punto de partida; ningún job hereda lo que instaló uno anterior, todos parten del mismo contenido de la imagen.
  - Para cachear algo entre ejecuciones **a propósito** (dependencias de `npm`/`pip`/`cargo` para acelerar builds), la vía correcta es la acción `cache` (compatible con la de GitHub Actions) — persistencia explícita, con clave y alcance, no un efecto colateral.
  - Para tener herramientas siempre disponibles sin reinstalarlas en cada job (`aws cli` de forma estable, por ejemplo), la vía correcta es construir una imagen propia con eso ya incluido y publicarla en `registry.404labo.net` (ya operativo, `docs/29-registry-mantenimiento.md`) — estado persistente pero versionado y controlado por quien lo construye, no una acumulación silenciosa.
  - **Con `host` (descartado como modo por defecto, ver arriba) el problema sí es real**: sin ningún contenedor de por medio, lo que instale un job se queda en el sistema operativo del runner para siempre, hasta que alguien lo desinstale o reinstale la máquina a mano — la razón de fondo detrás del aviso oficial ya citado ("un solo job puede destruir el host de forma permanente").
- **⚠️ Sistema operativo del runner — hallazgo importante antes de comprometerse a "todo en Forgejo"**: `forgejo-runner` **solo tiene soporte oficial para Linux** (amd64/arm64) — confirmado en la propia documentación de instalación del proyecto, no es una limitación menor. Windows existe como binario **no oficial**, mantenido por la comunidad (`Crown0815/forgejo-runner-windows`), y el propio repo "oficial-experimental" en `code.forgejo.org/windows/runner` se autodescribe como *"alpha release, should not be considered secure enough to deploy in production"*. macOS no tiene ni siquiera eso — solo una discusión abierta en el proyecto sobre si algún día se soportará. Además, por licencia de Apple, macOS no se puede virtualizar fuera de hardware Apple real (por eso GitHub/Codemagic/Bitrise mantienen granjas de Macs físicos para sus runners macOS) — no hay atajo software posible, a diferencia de Windows, donde la única barrera es la madurez del runner, no la licencia. **Ningún nodo actual del clúster es hardware Apple** (`docs/01-topologia.md`) — para builds de iOS/macOS haría falta comprar un Mac real; no hay alternativa autoalojada. Si en algún momento hace falta compilar apps iOS/macOS o Windows nativo, la opción más alineada con el plan ya existente de la mejora 7 (GitHub como espejo) es un **híbrido**: Linux en Forgejo Actions autoalojado, y esos jobs concretos disparados en GitHub Actions sobre el propio espejo (GitHub ya tiene runners macOS/Windows oficiales y maduros) — no añade una dependencia nueva, GitHub ya iba a seguir ahí de todos modos. Para Windows autoalojado sin depender de GitHub, la alternativa es una VM Windows (encajaría con la mejora, todavía no iniciada, de Cockpit+libvirt en `ryzen`) corriendo el runner no oficial, asumiendo conscientemente el riesgo "alpha".

#### 7.4 Almacenamiento de artefactos

**Ya no es futuro, está hecho** — el registry Docker (`registry.home.arpa`, en `retaco`) se instaló como paso independiente, sin esperar al resto de Forgejo (`docs/05-instalacion-retaco.md` sección 5.3). Los tres microservicios (`apikey-service`, `markitdown-service`, `whisper-service`, en `services/` en la raíz del repo) se publican ahí mediante `make build` en cada uno; ningún `docker-compose.yml` de ningún nodo los construye ya, todos hacen `image: registry.home.arpa/<nombre>:latest` + `pull`. Esto también resuelve la limitación ya documentada en `docs/16-mantenimiento-actualizaciones.md` en cuanto se integre con `check-image-updates.sh` (todavía no revisado si el script ya los detecta correctamente al venir de un registry propio en vez de Docker Hub — pendiente de comprobar, no bloqueante).

La compilación cruzada (`pi-dns`/`pi-utils` son ARM64, se compila normalmente desde x86) también está resuelta para `apikey-service`/`markitdown-service` mediante `docker buildx build --platform linux/amd64,linux/arm64 --push` + emulación QEMU (`whisper-service` se queda solo amd64 a propósito — necesita GPU NVIDIA, que las Pi no tienen). Detalle completo, incluida una CA interna que hay que instalar a mano dentro del contenedor del builder de `buildx` (no hereda la del host) y el hecho de que cada nodo consumidor necesita la CA a nivel de sistema + `docker login`: `docs/05-instalacion-retaco.md` sección 5.3.

Lo que sigue pendiente de esta sección original:

1. Si además se quiere un Package Registry integrado en el propio Forgejo (OCI, npm, PyPI, genérico, Debian, Maven...) en vez del `registry:2` standalone actual, evaluarlo cuando llegue esa fase — no es urgente mientras el `registry:2` cumpla.
2. Automatizar el propio `make build` (disparo por webhook/CI en vez de manual) — sigue siendo un comando que hay que correr a mano tras cada cambio de código; eso es lo que de verdad falta para llamarlo "CI" y no solo "registry con build manual".

**Investigado (2026-09-03), sin implementar todavía — dónde dejan artefactos las Forgejo Actions y los adjuntos de releases, y qué hace falta configurar cuando llegue la 7.3:**

Dos mecanismos distintos, ambos ya soportados por Forgejo, ninguno de los dos activado a propósito hoy (no hay ningún `forgejo-runner` registrado — sin runner, "Actions" no ejecuta nada aunque esté "activo" a nivel de instancia por defecto desde Forgejo 1.21):

- **Adjuntos de releases/incidencias** (equivalente a subir ficheros a un release de GitHub) — sección `[attachment]` de `app.ini`. Confirmado en vivo contra esta instancia: `PATH = /var/lib/gitea/data/attachments` (sin override explícito en el `app.ini` desplegado, todo por defecto). Límites por defecto: `FILE_MAX_SIZE = 50` (MB por adjunto) y `MAX_FILES = 5` por subida — bajos comparados con los releases de GitHub (varios GB); si algún día se suben binarios grandes a un release, subir `FILE_MAX_SIZE` vía `FORGEJO__attachment__FILE_MAX_SIZE` en el compose.
- **Artefactos de Forgejo Actions** (equivalente a `actions/upload-artifact` de GitHub Actions — build outputs de un job, no confundir con los adjuntos de arriba) — sección `[actions]`, `ARTIFACT_RETENTION_DAYS = 90` por defecto (se borran solos pasado ese plazo, configurable; `-1` los deja indefinidamente). Confirmado en vivo: los directorios `actions_artifacts/`, `actions_log/` y `actions_id_token/` **ya existen** en el contenedor real (`/var/lib/gitea/actions_artifacts`, etc.), creados automáticamente al arrancar aunque Actions no tenga ningún runner registrado todavía.

**Lo importante para cuando llegue la 7.3**: tanto los adjuntos como los artefactos de Actions (y también el Package Registry del punto 1, si se activa: `/var/lib/gitea/packages`, mismo patrón) viven bajo `/var/lib/gitea/`, que es **el mismo volumen NFS único** ya provisionado en la instalación núcleo de la mejora 7 (`docs/36-forgejo-repositorios-git.md`). Es decir: **no hace falta ningún volumen ni configuración de almacenamiento nueva** para que Actions guarde sus artefactos o para que funcionen los adjuntos de releases — ya está cubierto. Si el volumen NFS se quedara corto algún día, Forgejo soporta redirigir cualquiera de estas categorías a un backend S3/MinIO por separado (`[storage.attachments]`, `[storage.artifacts]`, etc., con `STORAGE_TYPE = minio` + `MINIO_ENDPOINT`/`MINIO_BUCKET`/credenciales) — no evaluado, no es necesario a la escala actual de este clúster.

**Hallazgo aparte, no relacionado con artefactos pero encontrado durante esta revisión**: `DISABLE_REGISTRATION = false` en el `app.ini` desplegado — el auto-registro público de cuentas está abierto en esta instancia. Mitigado hoy porque Forgejo solo es alcanzable desde la LAN/Tailscale (`docs/36-forgejo-repositorios-git.md`), pero no fue una decisión deliberada documentada — revisar si se quiere cerrar (`FORGEJO__service__DISABLE_REGISTRATION=true`) antes de dar por cerrada la mejora 7 del todo.

### Esfuerzo estimado
Alto — sobre todo por el volumen de migrar repositorios uno a uno, montar/probar CI, y decidir la estrategia de sincronización con calma. Abordar por fases.

---

## 8. Registry — limpieza y garbage collection

**Prioridad: media** — **implementado (uso manual), 2026-08-15**

### Qué se hizo

Los tres scripts (`shared/scripts/registry-garbage-collect.sh`, `registry-prune-tags.sh`, `backup-registry.sh`) están listos y sincronizados en los 5 nodos — detalle completo, comandos y verificación en vivo en `docs/29-registry-mantenimiento.md`. Alcance decidido explícitamente al implementarlo:

1. **Garbage collection**: script listo, **solo ejecución manual** (sin cron) — el propio comando exige que el registry no reciba pushes mientras corre, automatizarlo sin supervisión era más riesgo que beneficio en un clúster con pocos pushes reales.
2. **Retención de tags**: **3 versiones antiguas por imagen** (además de `latest`) — script propio (`registry-prune-tags.sh`, vía la API HTTP del registry), también solo manual.
3. **Copia de seguridad**: script listo (`backup-registry.sh`, mismo patrón que `backup-vaultwarden.sh`) pero **sin ejecutar todavía** — decisión explícita, las imágenes son reconstruibles desde el código fuente.
4. **Alerta de espacio en disco**: cubierta por la mejora 3 (`docs/14-monitorizacion-completa-cluster.md`), cerrada el mismo día — la regla genérica por nodo ya vigila `retaco` (y el resto de nodos que montan `/mnt/nfs-data`, donde vive `registry` desde el 2026-08-31) sin necesidad de una alerta específica.

### Qué hay hoy (histórico, previo a la implementación)

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

Acceso remoto mediante Tailscale ya desplegado (`docs/18-tailscale.md`, subnet router en `pi-dns`) — sin ACL personalizada, comportamiento por defecto: cualquier dispositivo autenticado en el tailnet llega a todo el clúster. Suficiente mientras el tailnet tenga un único usuario/cuenta.

### Qué haría falta

1. Decidir si conviene restringir por dispositivo/usuario (p. ej. un dispositivo de invitado que solo debería llegar a `open-webui`, no a `vaultwarden` o `postgresql.home.arpa`).
2. Escribir una política de ACL (tags + reglas) en el editor de políticas del panel de Tailscale — no es un fichero de este repo, vive en la configuración del tailnet.
3. Etiquetar el nodo `pi-dns` (p. ej. `tag:subnet-router`) para que la auth key deje de estar ligada a la cuenta personal — más robusto a largo plazo que una key de usuario.

### Esfuerzo estimado
Bajo-medio — configuración, no código; el esfuerzo real es decidir la política, no aplicarla.

---

## 10. ~~NAS UGREEN — migrar `nfs-data` a NFSv4~~ — completada (investigada y descartada, no viable en este NAS)

**Prioridad: baja** — **completada**

### Qué se investigó (2026-08-22)

Retomada e investigada a fondo por SSH contra `ketekasko` (cuenta `linus`, con sudo — hubo que activar antes el servicio de directorio home de usuario y el rol de administrador para esa cuenta en el Panel de control de UGOS Pro, ninguno de los dos estaba operativo). Confirmado el mecanismo de `/etc/exports`: no hay ningún fichero tipo `nfs.json` que lo regenere, la GUI lo reescribe directamente al tocar la pestaña "Permiso NFS" de una carpeta.

Se añadió a mano un export raíz `fsid=0` con `crossmnt` (`/volume1 192.168.1.0/24(ro,fsid=0,no_subtree_check,crossmnt)`, antepuesto al export real de `nfs-data`), aplicado con `exportfs -ra` sin error. El montaje NFSv4.2 desde un cliente Linux **funcionó** (`ketekasko.home.arpa:/nfs-data`, ruta relativa al pseudo-root) y la lectura inicial fue correcta. Pero al cabo de pocos minutos, **sin tocar la GUI en ningún momento**, `/etc/exports` en el NAS volvió solo a su estado original (sin el export raíz) — confirmado con `diff` contra un backup. El cliente, con el montaje ya activo, empezó a devolver `Stale file handle` en cualquier operación, incluida la raíz del propio punto de montaje.

**Conclusión**: UGOS Pro revierte `/etc/exports` de forma espontánea en segundo plano, no solo al interactuar con su GUI — peor que un simple fallo de montaje, porque puede tumbar un montaje ya activo en mitad de una sesión. Inviable para cualquier uso real. Detalle completo del intento en `docs/21-configuracion-nas-ugreen.md`.

### Qué hay hoy

NFSv3 sigue siendo la única opción viable en este NAS mientras se use UGOS Pro (root sin squash, confirmado en uso real con bind mounts de Docker) — ver `docs/21-configuracion-nas-ugreen.md`. No hay plan de reintentar NFSv4 salvo que UGOS Pro cambie su comportamiento en una actualización futura de firmware.

### Esfuerzo estimado
Ya invertido — bajo-medio, como se estimaba. El resultado fue negativo, no un problema de esfuerzo.

---

## 11. k6 para automatizar pruebas de carga

**Prioridad: media**

### Qué hay hoy

No existe ninguna prueba de carga automatizada contra los servicios del clúster — cuando hace falta comprobar cómo aguanta `apikey-service`, `markitdown-service` o el propio `nginx` bajo concurrencia, se ha hecho de forma manual y puntual.

### Qué haría falta

1. k6 no es un servicio persistente sino una herramienta que se ejecuta bajo demanda (contenedor `grafana/k6`, o binario) — no necesita un nodo dedicado, solo un sitio desde donde lanzarlo sin sesgar la medición ejecutándolo en el mismo nodo que se está probando. `pi-utils` encaja por rol (herramientas, poca carga propia).
2. Crear un directorio `load-tests/` en el repo, un script k6 (JavaScript) por servicio a probar — ahora que el repo está bajo git (punto 2), estos scripts se versionan igual que el resto.
3. Conectar la salida a la observabilidad ya existente: k6 soporta `--out experimental-prometheus-rw=http://prometheus.home.arpa/api/v1/write` para mandar sus métricas directamente a Prometheus — requiere activar `--web.enable-remote-write-receiver` en la configuración de Prometheus (`pi-obs/config/prometheus.yml`).
4. Dashboard en Grafana para visualizar los resultados — buscar un dashboard oficial de k6 en Grafana.com en vez de construir uno desde cero, mismo criterio que con el resto de dashboards importados (`docs/08-instalacion-pi2-observabilidad.md`).
5. Decidir qué endpoints tiene sentido cargar: los protegidos por `apikey-service` necesitarán una key válida en el propio script de prueba.

### Esfuerzo estimado
Bajo-medio — la herramienta en sí es un contenedor suelto; el trabajo real es escribir los escenarios de prueba y conectar la salida a Prometheus.

---

## 12. RAG para libros en PDF, consultable desde Open WebUI

**Prioridad: media**

### Qué hay hoy

Desarrollo ya iniciado (parcial, fuera de esta documentación todavía) para poder ingerir libros en PDF y consultarlos desde Open WebUI, reutilizando piezas que el clúster ya tiene: `markitdown-service` ya convierte PDF a Markdown, Qdrant ya aloja las colecciones `articles` y `transcripts`, y Ollama ya sirve los embeddings (`nomic-embed-text`) que usa el resto del pipeline de contenido.

### Qué haría falta

1. Decidir el diseño final: una colección Qdrant nueva y separada (p. ej. `books`), o usar el RAG nativo de Open WebUI apuntando directamente a Qdrant (`VECTOR_DB=qdrant` en su configuración) en vez de construir un pipeline de ingesta propio.
2. Pipeline de ingesta: PDF → `markitdown-service` → texto limpio → chunking → embeddings → Qdrant. Los libros son mucho más largos que un artículo de RSS o una transcripción; la estrategia de *chunking* que sirva para artículos cortos probablemente no sea la adecuada para cientos de páginas seguidas — hay que revisarla específicamente para este caso.
3. Conectar la colección resultante a Open WebUI como fuente de conocimiento ("Knowledge") para poder preguntar sobre los libros desde el chat.
4. Espacio de almacenamiento de los PDF originales: pesan bastante más que un artículo — valorar si tiene sentido guardarlos en el NAS (`docs/21-configuracion-nas-ugreen.md`) en vez de en el disco del nodo que haga la ingesta.

### Esfuerzo estimado
Medio — parte del trabajo ya está hecho según el propio desarrollo en curso; queda sobre todo pulir el *chunking* para documentos largos y la integración con Open WebUI.

---

## 13. Copiar logs y métricas del clúster al NAS para liberar espacio en pi-obs

**Prioridad: media**

### Qué hay hoy

Prometheus, Loki (retención 14 días) y Tempo (retención 72h) guardan todos sus datos en el disco local de `pi-obs` — una Raspberry Pi 5, con el almacenamiento limitado que eso implica (`docs/08-instalacion-pi2-observabilidad.md`). No hay ninguna copia ni descarga hacia el NAS.

### Qué haría falta

1. Descartar servir los datos "en caliente" directamente desde el NAS por NFS — la latencia de red no es ideal para escritura constante de series temporales, y complica innecesariamente algo que hoy funciona bien en local.
2. En su lugar, copiar periódicamente al NAS los datos ya "fríos" (los que están a punto de expirar por retención) antes de que `pi-obs` los borre — mismo patrón que las copias de seguridad existentes (`shared/scripts/backup-*.sh`, ver mejora 1): un script nuevo, por cron, con `rsync` sobre el NFS ya montado del NAS.
3. Para Prometheus en concreto, valorar si compensa un snapshot periódico (`/api/v1/admin/tsdb/snapshot`) en vez de copiar el directorio de datos completo.
4. Decidir si esta copia va a la misma carpeta compartida `nfs-data` que ya usan los bind mounts de Docker (`docs/21-configuracion-nas-ugreen.md`) o si merece una carpeta separada, para no mezclar datos de aplicación con datos de observabilidad.
5. Confirmar cuota disponible en el NAS antes de comprometerse — hoy `nfs-data` tiene 1.5 TB asignados, compartidos con el resto de usos.

### Esfuerzo estimado
Medio — es sobre todo cron + `rsync`, reutilizando infraestructura ya montada (NFS del NAS, patrón de backups); la parte que requiere pensar es qué copiar y cuándo, para no duplicar el trabajo de las retenciones que ya existen.

---

## 14. Evaluar Floci como emulador local de AWS

**Prioridad: media**

### Qué hay hoy

Ninguna emulación de servicios AWS en el clúster todavía. [Floci](https://github.com/floci-io/floci) es una alternativa de código abierto a LocalStack: emula 69 servicios de AWS (S3, DynamoDB, Lambda, SQS, RDS, ElastiCache, EKS...) en un único contenedor, con contenedores Docker reales por debajo para los servicios con estado (Lambda, RDS, ElastiCache), sin necesidad de cuenta ni token de AWS.

### Qué haría falta

1. Desplegar el contenedor (`docker run -d -p 4566:4566 -v /var/run/docker.sock:/var/run/docker.sock floci/floci:latest`) — **necesita acceso a `docker.sock`** para lanzar sus propios contenedores de servicios con estado, lo que le da control total sobre el Docker del host, igual que ya se advierte para `portainer-agent` (`docs/04-servicios-comunes.md`). No es un detalle menor.
2. Elegir nodo: como necesita `docker.sock` y puede lanzar bastantes contenedores propios de golpe (RDS, Lambda, ElastiCache...), mejor en `ryzen` o `retaco` —con más CPU/RAM de margen— que en una Raspberry Pi ya ajustada de recursos.
3. Elegir modo de almacenamiento (memoria, persistente, híbrido o *write-ahead log*) según si interesa que el estado sobreviva a un reinicio del contenedor o si basta con un entorno efímero por sesión de pruebas.
4. Decidir si se expone mediante `nginx`/`apikey-service` o si se queda solo accesible en la red interna del nodo — para el caso de uso previsto (pruebas puntuales de código propio contra servicios AWS simulados) probablemente basta con esto último, mismo criterio que `node-exporter`/`cadvisor` (`docs/17-firewall-acceso-directo.md`).
5. Caso de uso concreto: encaja directamente con el motivo original del clúster (aprendizaje y comparativas en hardware controlado) — probar código dependiente de AWS sin cuenta real ni coste, y sin las limitaciones de un mock superficial.

### Esfuerzo estimado
Bajo — es un único contenedor Docker; la decisión real es dónde vive y cómo se acota el riesgo de darle acceso a `docker.sock`.

---

## 15. ~~Panel de control para arrancar/parar servicios y estado en `index.home.arpa`~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

Capataz desplegado como panel de control real, sustituyendo la página estática de `index.home.arpa` — detalle completo en `docs/28-capataz-consola-automatizacion.md`. Resumen:

- Backend (`capataz-api`) y `capataz-runner` en `pi-utils`, hablando con la API REST de Portainer para arrancar/parar/reiniciar contenedores por nombre — mismo criterio de "envoltorio ligero sobre algo que ya existe" apuntado en el punto 2 original, en vez de reimplementar esa lógica.
- Frontend desplegado como build estático (patrón "Standalone Frontend Deployment" de Capataz) servido por el `nginx` de `pi-dns` en `index.home.arpa`, reemplazando la página HTML+CSS sin JavaScript que había antes — sí necesitó salir de "cien por cien estática" para mostrar estado en vivo, como anticipaba el punto 3 original.
- Login real vía Authentik (OIDC, Authorization Code + PKCE) desde 2026-08-19, tras una fase piloto previa en `dev_mock` (identidad sintética con selector de rol viewer/operator/admin) — cierra la superficie de riesgo señalada en el punto 5 original ("candidato claro para ir detrás de auth" ahora que el panel sí puede apagar servicios): tres grupos RBAC en Authentik (`capataz-viewer`/`-operator`/`-admin`) en vez de `apikey-service`, por ser Capataz quien gestiona su propio login OIDC.
- Pendiente de seguimiento (no bloquea el cierre de esta mejora): confirmar que el usuario/grupo Authentik usado durante el piloto tiene membresía real en uno de los tres grupos RBAC — ver nota en `docs/28-capataz-consola-automatizacion.md`.

### Qué hay hoy (histórico, previo a la implementación)

Arrancar o parar un servicio hoy es manual: por SSH y `docker compose up`/`down`, documentado en `docs/11-operacion-diaria.md`. Portainer ya permite hacer lo mismo desde su interfaz (start/stop/restart por contenedor), pero hay que entrar a Portainer y navegar hasta el nodo y el contenedor concretos — no hay un panel unificado. `index.home.arpa` (`docs/06-instalacion-pi1-dns.md`) es hoy una página HTML+CSS estática servida directamente por nginx, sin JavaScript: enlaza a cada servicio, pero no dice si está arriba o caído.

### Qué haría falta

1. Decidir el alcance antes de nada: ¿construir un panel de control propio, o simplemente aprovechar mejor lo que Portainer ya ofrece (Environments → nodo → contenedor) sin reinventar la rueda?
2. Si se opta por un panel propio: apoyarse en la API REST de Portainer para arrancar/parar contenedores por nombre, en vez de reimplementar esa lógica — mismo criterio de "envoltorio ligero sobre algo que ya existe" que se siguió con `apikey-service`.
3. Para mostrar estado en vivo en `index.home.arpa`, la página deja de poder ser cien por cien estática — necesitaría un mínimo de JavaScript que consulte periódicamente algo (la API de Portainer, o el `/health` de cada microservicio propio). Valorar si compensa ese cambio de naturaleza de la página.
4. Alternativa más barata: un panel de Grafana dedicado a "estado de servicios" (reutilizando Prometheus, que ya sabe si un contenedor responde) enlazado desde `index.home.arpa`, en vez de construir estado en vivo dentro de la propia página.
5. Si el panel llega a tener capacidad de **apagar** servicios (no solo consultarlos), esa es una superficie nueva que proteger — hoy nada expuesto en la LAN puede apagar otra cosa. Candidato claro para ir detrás de `apikey-service`, igual que el resto de servicios sin autenticación nativa.

### Esfuerzo estimado
Medio — muy distinto según se opte por un panel propio (más trabajo, más control) o por aprovechar Portainer/Grafana tal cual (mucho menos trabajo, menos a medida).

---

## 16. ~~Sistema de secretos para consumo programático — Infisical~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó (2026-08-09)

Infisical desplegado en `retaco`, en producción, con `apikey-service` migrado como primer servicio piloto y verificado de extremo a extremo — detalle completo en `docs/26-infisical-secretos.md`. Dos decisiones de arquitectura con ADR propia: `docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md` (cómo se inyectan los secretos — distinto de lo previsto originalmente en el punto 4 de más abajo, ver nota ahí) y `docs/adr/0002-infisical-postgres-dedicado.md` (Postgres dedicado, no compartido con `postgres-main`, decidido tras revisión — el plan original de este mismo documento asumía compartir `postgres-main`, como el resto de servicios).

Esta mejora se da por completada con la infraestructura desplegada y el patrón de migración validado en producción con un servicio real — no con todos los servicios del clúster ya migrados. Migrar el resto (auditoría completa ya hecha, `docs/26-infisical-secretos.md`) pasa a ser la mejora 28, para no bloquear esto en algo que va a llevar varias iteraciones separadas.

El razonamiento de la decisión Infisical-vs-Vault de abajo sigue vigente tal cual — no se repite, se implementó como estaba planteado.

### Qué hay hoy (histórico, previo a la implementación)

Vaultwarden guarda las credenciales del clúster, pero está pensado para que una persona las desbloquee, no para que un contenedor las pida solo al arrancar — no tiene secretos dinámicos, ni permisos finos por servicio, ni auditoría de quién leyó qué y cuándo. El patrón real hoy es manual: los valores se copian a mano desde Vaultwarden a los `.env.example` → `.env` de cada nodo/servicio durante el despliegue (`docs/05` a `docs/10`), y ahí se quedan, fijos, hasta que alguien los rota también a mano.

### Decisión: Infisical, no HashiCorp Vault

Se evaluaron las dos opciones y se descartó Vault, por varios motivos combinados:

- **Vault es matar moscas a cañonazos** para un clúster de un solo operador sobre Docker Compose (no Kubernetes): exige aprender a operar `AppRole`, políticas de acceso granulares y motores de secretos — infraestructura pensada para equipos, no para un homelab.
- El problema práctico real de Vault es el **sellado**: arranca sellado tras cada reinicio y, sin desellado automático, deja bloqueados todos los servicios que dependen de él hasta que alguien lo desbloquea a mano — inviable con el apagado/encendido completo del clúster (`docs/20-apagado-y-encendido-cluster.md`). La única forma práctica de evitarlo es el auto-unseal vía un KMS externo (típicamente AWS KMS), y ahora mismo **no se quiere añadir esa dependencia sobre AWS** solo para operar el propio sistema de secretos — la cuenta AWS que ya existe (Bedrock/Bifrost, `docs/23`) es para otra cosa y no debe mezclarse con esto.
- Lo único que Vault ofrecía y Infisical no —secretos dinámicos, p. ej. credenciales de Postgres de vida corta— no compensa la complejidad operativa añadida para el caso de uso real de este clúster: secretos que casi nunca rotan, un solo operador.
- Infisical resuelve el mismo problema de fondo (nada de secretos fijos en `.env` en claro, identidades de máquina, auditoría) con una superficie operativa mucho menor: sin concepto de sellado, backend en Postgres (que ya se opera en `retaco`), interfaz web sencilla — mismo espíritu que Vaultwarden pero para máquinas en vez de personas.

### Qué haría falta (implementación con Infisical)

1. ~~**Despliegue**: contenedor `infisical` en `retaco`... Backend propio en Postgres... compartiendo `postgres-main`... Redis dedicado...~~ **Superado por la implementación real**: Postgres DEDICADO (`postgres-infisical`, no `postgres-main` — ver ADR 0002), y Redis reutiliza el `valkey` ya desplegado (mejora 24) en vez de un contenedor dedicado. Ver `docs/26-infisical-secretos.md`.
2. **Acceso**: `infisical.home.arpa` vía el `nginx` de `pi-dns`, sin pasar por `apikey-service` — Infisical gestiona su propio login. Igual que se planteaba para Vault, el acceso queda limitado a la red interna del clúster. **Implementado tal cual.**
3. **Identidades de máquina**: cada servicio migrado obtiene una *Machine Identity* propia con **Universal Auth** (`client_id`/`client_secret`), con acceso restringido a un único proyecto/entorno/ruta de secretos — nunca una identidad compartida para todo el clúster. **Implementado tal cual** — nota: el *IP allowlisting* de estas identidades es una función de pago (Infisical Pro/Enterprise), no disponible en la edición community autoalojada; el alcance mínimo se consigue solo con el rol/ruta del proyecto, no con restricción de IP.
4. ~~**Integración con Docker Compose**: ... El binario de la CLI `infisical` se añade a la imagen del microservicio (una línea más en el `Dockerfile`...)~~ **Descartado y sustituido**, ver `docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md`: hornear el CLI en la imagen obligaría a reconstruirla solo para subir de versión el CLI. Mecanismo real: binario estático por nodo, montado por bind-mount, `entrypoint:`/`command:` sobreescritos en el `docker-compose.yml` del nodo — ninguna imagen se toca. Además, el `entrypoint:` de una sola línea del ejemplo original no basta en la práctica: la versión del CLI usada necesita un login previo (`infisical login --method=universal-auth`) para obtener un token antes de `infisical run --token=...` — wrapper de dos pasos, detalle en `docs/26`.
5. **El problema del arranque no desaparece del todo**: confirmado en vivo, no solo en teoría — con `apikey-service` migrado, se probó apagar Infisical (el servicio ya en marcha sigue funcionando sin problema) y forzar después un reinicio de `apikey-service` con Infisical aún caído (se queda reintentando en bucle hasta que Infisical vuelve, `restart: unless-stopped` lo recupera solo, sin intervención manual). La diferencia real frente a hoy no es "cero secretos en `.env`", es pasar de **N secretos fijos por servicio** a **una identidad de alcance mínimo, rotable de forma independiente**.
6. **Migración incremental**: `apikey-service` migrado y verificado en producción (piloto) — con esto, el patrón queda validado y esta mejora se cierra aquí. El alcance real es TODO servicio con secretos en `.env` del clúster, propio o de terceros — no solo los microservicios propios; auditoría completa ya hecha (candidatos limpios, bloqueados por falta de shell, bloqueados por comportamiento "solo al primer arranque" como `postgres-main`/`grafana`, y casos con secreto en fichero como `registry`) en `docs/26-infisical-secretos.md`, sección "Inventario completo". Migrar el resto: **mejora 28**.
7. Vaultwarden no desaparece: sigue siendo el sitio correcto para credenciales que usa una persona desde un navegador (paneles de administración, cuentas de terceros). Infisical cubre el consumo entre máquinas, no sustituye a Vaultwarden. **Vigente sin cambios.**

### Esfuerzo estimado
Medio — confirmado en la implementación real: el despliegue del servidor (Postgres dedicado + Valkey reutilizado + nginx/DNS/CA) fue la parte más mecánica; el grueso real del esfuerzo fue depurar el mecanismo de inyección en vivo (wrapper de dos pasos, confianza en la CA interna desde el CLI) y decidir la arquitectura (Postgres dedicado, ADR 0002) — no la integración por servicio en sí, que una vez resuelto el patrón es repetible. Migrar el resto de servicios queda como mejora 28, debería ser más rápido por servicio al reutilizar el patrón ya validado aquí.

---

## 17. ~~Open Terminal en modo MCP, conectado desde Open WebUI y n8n~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

Desplegado en `retaco` (no `ryzen`/`mole`, descartado a petición expresa por no estar siempre encendido) — carga verificada en vivo antes de desplegar (~10 GiB libres de 13 GiB). Detalle completo: `docs/24-open-terminal-mcp.md`.

Resumen de lo implementado:
- Imagen propia `registry.home.arpa/open-terminal-mcp` (`services/open-terminal-mcp/`) — ninguna variante oficial de `ghcr.io/open-webui/open-terminal` trae el extra `[mcp]` (`fastmcp`) instalado; se añade encima del tag `slim`.
- **Hallazgo de seguridad real, encontrado antes de exponer nada a la red**: `OPEN_TERMINAL_API_KEY` protege solo la API REST propia — el transporte MCP (`streamable-http`) se instancia sin ningún proveedor de autenticación (confirmado leyendo `open_terminal/mcp_server.py`), así que cualquiera que alcance el puerto tendría shell y ficheros completos sin credencial. Confirmado en vivo: `initialize` sin ninguna cabecera → HTTP 200. Por eso va detrás de `apikey-service` en nginx (`pi-dns`) — no como capa opcional, sino como el único mecanismo de auth real de cara al exterior. `open-terminal.home.arpa` desplegado con `proxy_buffering off` y timeouts largos (streaming SSE + conexiones potencialmente ociosas), y añadido al SAN del certificado interno.
- Sin montajes del host ni acceso a `docker.sock` — mismo criterio de superficie de riesgo que Floci (mejora 14): el LLM solo ve el volumen propio del contenedor.
- Probado de extremo a extremo (`curl` con y sin `X-Api-Key`, 401/200) desde `ryzen`/`mole`.
- Documentado cómo conectarlo desde Open WebUI (`Admin Settings → External Tools`, MCP nativo desde 0.6.31, confirmado 0.11.0 en `retaco`) y desde n8n (nodo `MCP Client Tool`, nativo desde n8n 2.31.6, sin instalar nada aparte).

### Qué hay hoy (histórico, previo a la implementación)

Open WebUI y n8n solo razonan sobre texto — ningún agente de IA del clúster puede ejecutar comandos, tocar archivos o correr código por sí mismo. No existe ningún entorno de ejecución expuesto a los LLM.

### Qué haría falta

1. Desplegar [`open-webui/open-terminal`](https://github.com/open-webui/open-terminal) (mismo equipo que Open WebUI) vía Docker: `ghcr.io/open-webui/open-terminal`, con variantes de imagen `latest` (~4 GB, Node.js/gcc/ffmpeg/Docker CLI, pensada para sandboxes completos), `slim` (~430 MB, git/curl/jq) y `alpine` (~230 MB) — para este clúster, `slim` o `alpine` probablemente bastan salvo que se necesiten herramientas pesadas de desarrollo dentro del propio terminal.
2. Nodo: contenedor con volumen dedicado (`open-terminal:/home/user`) y `OPEN_TERMINAL_API_KEY` como secreto — mejor en `retaco` o `ryzen` que en una Pi si se usa la imagen `latest`.
3. Activar el modo MCP: no viene en la instalación base, requiere el extra `open-terminal[mcp]` (añade `fastmcp>=2.0.0`) y se levanta con el subcomando `open-terminal mcp`. Dos transportes disponibles: `stdio` (el cliente lanza el proceso localmente, pensado para uso de escritorio tipo Claude Desktop) y `streamable-http` (el servidor escucha en un puerto TCP, pensado para despliegue remoto) — en este clúster interesa `streamable-http`, ya que Open WebUI y n8n corren en contenedores separados del de open-terminal.
4. Internamente usa `FastMCP.from_fastapi`: introspecciona el esquema OpenAPI de la propia app y genera automáticamente una herramienta MCP por endpoint (File System API, Command Execution API, terminales interactivas, gestión de puertos, ejecución de notebooks), sin duplicar lógica. La autenticación por `OPEN_TERMINAL_API_KEY` se mantiene — el servidor MCP inyecta el header `Authorization` en las llamadas internas.
5. Conectar desde **n8n**: nodo MCP Client Tool (`n8n-nodes-langchain.toolMcp`, o el nodo comunitario `n8n-nodes-mcp` si la versión desplegada no lo trae de serie) apuntando a la URL `streamable-http` del contenedor, autenticación Bearer con la API key — las herramientas se auto-descubren desde el propio servidor MCP.
6. Conectar desde **Open WebUI**: dos caminos posibles, no hace falta elegir solo uno:
   - Integración nativa dedicada "Open Terminal" (`Admin Settings → Integrations → Open Terminal`) — habla el API REST propio del proyecto, no MCP; más simple si solo hace falta terminal dentro del chat.
   - MCP genérico (`Admin Settings → External Tools`), soportado de forma nativa desde Open WebUI v0.6.31 (solo `streamable HTTP`, sin `stdio`, por ser un entorno multiusuario) — apuntando a la misma URL que consume n8n, con el mismo token; evita duplicar la integración si ya se monta el servidor MCP para n8n.
7. Decisión de superficie de riesgo: dar a un LLM acceso a shell/archivos equivale a darle acceso a todo lo que vea ese contenedor — mismo tipo de decisión ya señalada para `docker.sock` en Floci (mejora 14) y `portainer-agent`. Empezar sin montajes del host reales y sin acceso a `docker.sock`, solo con el volumen propio del contenedor.
8. Modo multiusuario (`OPEN_TERMINAL_MULTI_USER=true`) solo si de verdad hace falta más de una terminal aislada por usuario — de lo contrario, dejarlo desactivado.

### Esfuerzo estimado
Bajo-medio — el contenedor en sí es un `docker run`; lo que requiere cuidado es decidir el nivel de acceso al sistema que se le concede y probar bien la integración MCP con ambos clientes.

---

## 18. OpenClaw — asistente personal de IA autoalojado

**Prioridad: media**

### Qué hay hoy

Ollama + Open WebUI cubren el caso de "chat con modelos locales" cuando una persona abre la interfaz y pregunta algo — no hay ningún agente proactivo (cron jobs, recordatorios, tareas en segundo plano) ni integración con canales de mensajería o servicios externos (correo, calendario, GitHub...) conectado al clúster.

### Qué haría falta

1. Instalación self-hosted (recomendada por el propio proyecto, [openclaw.ai](https://openclaw.ai/)):
   ```bash
   curl -fsSL https://openclaw.ai/install.sh | bash
   npm i -g openclaw
   openclaw onboard
   ```
El instalador trae Node.js y dependencias; compatible Linux/macOS/Windows. Alternativa desde fuente: clonar `github.com/openclaw/openclaw`, `corepack enable && pnpm install`, `pnpm openclaw onboard`.
2. Nodo: al tener estado local persistente (memoria entre conversaciones) y tareas en segundo plano 24/7, encaja mejor en un nodo siempre encendido y con margen de recursos (`retaco` o `ryzen`) que en una Raspberry Pi.
3. Modelo: soporta Claude (Anthropic), GPT (OpenAI) y modelos locales — para mantener el criterio "todo local" del resto del clúster, evaluar apuntarlo a Ollama con los modelos ya desplegados (`qwen2.5:14b`/`32b`) en vez de a una API en la nube; probar antes de comprometerse a un flujo de trabajo real, ya que el uso de herramientas/razonamiento agente de un modelo de 14-32B puede quedarse corto frente a Claude o GPT en tareas complejas.
4. Integraciones: 29 canales de chat disponibles (WhatsApp, Telegram, Discord, Slack, Signal, iMessage) y herramientas (Gmail, GitHub, Obsidian, Notion, Todoist, Philips Hue, 1Password, Spotify, WHOOP...) — no activar todo de golpe; empezar por una única integración de bajo riesgo (p. ej. Telegram o Discord solo para consulta) antes de dar acceso a correo o gestores de contraseñas.
5. Nivel de acceso al sistema: puede leer/escribir archivos, ejecutar comandos shell y controlar un navegador directamente — mismo tipo de decisión de superficie de riesgo que la mejora 17 (Open Terminal) y que Floci (mejora 14, `docker.sock`). El proyecto ofrece un modo sandbox frente a acceso completo al sistema — empezar por sandbox.
6. Actualizaciones: canal estable por defecto, o `openclaw update --channel dev` para probar features nuevas; existen releases LTS para cargas consideradas críticas — para uso personal en este clúster, canal estable es lo razonable.
7. Backup: decidir si el estado local de OpenClaw (memoria, configuración, credenciales de integraciones) entra en las copias de seguridad ya existentes o futuras (mejora 1) — al tener memoria persistente entre conversaciones, perderla en un fallo de disco no es solo perder una imagen Docker reconstruible.

### Pequeño manual de operación

- **Arranque/parada**: si acaba desplegado como contenedor, mismo patrón que el resto de servicios (`docs/11-operacion-diaria.md`); si es instalación nativa (npm), gestión mediante su propio CLI (`openclaw` sin argumentos entra en el estado del proceso, comprobar en `openclaw --help` una vez instalado).
- **Altas de integración**: canal o herramienta nueva se añaden desde la propia conversación con el asistente o su configuración — no requiere redeploy si es solo config.
- **Ejecución remota con aprobación**: soporta lanzar tareas y aprobarlas desde el móvil — útil para tareas que tocan sistemas sensibles (correo, calendario) sin dejarlas en piloto automático total.
- **Habilidades personalizadas**: puede escribir sus propias extensiones a partir de una petición en lenguaje natural — revisar el código generado antes de dejar que una habilidad nueva se ejecute sin supervisión, mismo criterio que con cualquier código generado por IA que toque el sistema.
- **Documentación oficial**: [docs.openclaw.ai](https://docs.openclaw.ai/) — consultar ahí antes de tocar configuración avanzada; este apunte es solo el resumen necesario para decidir si vale la pena montarlo.

### Esfuerzo estimado
Medio — la instalación en sí es rápida (script + onboarding); lo que lleva tiempo es decidir con criterio qué integraciones activar y qué nivel de acceso al sistema concederle, dado que por diseño es la pieza con más capacidad de "hacer cosas reales" de todo el clúster.

---

## 19. Opencode — agente de código open source para terminal

**Prioridad: media**

### Qué hay hoy

Claude Code (esta misma herramienta) es hoy el único agente de codificación en uso sobre los repositorios del clúster — sin alternativa evaluada que permita elegir proveedor de modelo libremente, incluidos los modelos locales que ya sirve el propio Ollama del clúster.

### Qué haría falta

1. Instalación — mantenido por Anomaly en [`github.com/anomalyco/opencode`](https://github.com/anomalyco/opencode):
   ```bash
   curl -fsSL https://opencode.ai/install | bash    # script universal
   npm install -g opencode-ai                        # vía npm
   brew install anomalyco/tap/opencode                # Homebrew (macOS/Linux)
   docker run -it --rm ghcr.io/anomalyco/opencode     # sin instalar nada
   ```
También disponible como extensión para VS Code, Cursor, Zed, Windsurf y VSCodium, y como app de escritorio (beta) para quien prefiera GUI en vez de terminal.
2. Configuración de proveedor: acepta cualquier proveedor de modelos vía API key (OpenAI, Anthropic Claude, Google Gemini, AWS Bedrock, Groq, Azure OpenAI, OpenRouter...) y ofrece "OpenCode Zen" como lista curada de modelos ya probados — para este clúster, el interés real está en apuntarlo a Ollama para tener un agente de código 100% local, o a Claude para comparar calidad de generación frente a Claude Code en tareas reales.
3. Caso de uso dentro de este clúster: banco de pruebas directo frente a Claude Code sobre las mismas tareas de mantenimiento del repo — "¿qué tan bien razona sobre este código un modelo local (`qwen2.5:32b` vía Ollama) frente a un modelo en la nube?" — en línea con el motivo original del clúster (aprendizaje y comparativas en hardware controlado, mismo criterio que la mejora 14, Floci).
4. Sin necesidad de nodo dedicado: es una CLI que se ejecuta bajo demanda en la máquina de quien la use (como Claude Code), no un servicio persistente — no requiere entrada en ningún `docker-compose.yml` ni excepción de firewall, salvo que se apunte a Ollama, que ya está expuesto en la red interna del clúster.

### Esfuerzo estimado
Bajo — instalar y probar es rápido; el esfuerzo real es la comparativa cualitativa frente a Claude Code si se quiere sacar una conclusión útil de la evaluación.

---

## 20. LiteLLM — proxy unificado de LLM, configurado para AWS Bedrock y Open WebUI

**Prioridad: media**

### Qué hay hoy

Ollama sirve los modelos locales con una API OpenAI-compatible que ya consumen Open WebUI y n8n, pero no existe ninguna vía equivalente hacia modelos en la nube (p. ej. Claude vía AWS Bedrock) — cada integración con un proveedor cloud tendría que montarse por separado, sin capa común de *virtual keys*, presupuestos, tracking de coste ni fallback automático entre modelos.

### Qué haría falta

1. Desplegar [LiteLLM Proxy](https://docs.litellm.ai/) (MIT, self-hosted) — imagen `ghcr.io/berriai/litellm`, fijando una versión concreta en el `docker-compose.yml` (p. ej. `:v1.90.0-stable` o la estable vigente en el momento del despliegue) en vez de `latest`, mismo criterio ya aplicado al resto del clúster. Postgres para persistencia (config, virtual keys, logs de coste) — mismo patrón `create-postgres-db.sh` ya usado para n8n/SonarQube/apikeys/Forgejo.
2. Nodo: `retaco` — ya aloja `postgres-main`, sigue el mismo patrón multi-tenant que Forgejo/SonarQube.
3. Configuración para AWS Bedrock: requiere `boto3` (incluido en la imagen Docker oficial). En `config.yaml`, un `model_list` con `litellm_params` usando el prefijo `bedrock/` (p. ej. `bedrock/converse/anthropic.claude-...`), credenciales vía variables de entorno `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` / `AWS_REGION_NAME` — o `aws_profile_name` / `aws_role_name` (asumir un rol) si se prefiere evitar credenciales de larga duración, más seguro y a evaluar antes de comprometerse a *access keys* fijas.
4. Credenciales AWS: crear un usuario o rol IAM dedicado con permiso mínimo (`bedrock:InvokeModel` / `InvokeModelWithResponseStream` solo sobre los modelos concretos que se vayan a usar, nada más) — no reutilizar credenciales de administrador. Guardar en Vaultwarden (o en el futuro sistema de secretos programático, mejora 16) y nunca en el repo.
5. Arranque: `litellm --config config.yaml`, expone API OpenAI-compatible en `:4000` por defecto, con UI de administración propia incluida (virtual keys, presupuestos por equipo/usuario, tracking de coste, *fallback* automático entre modelos).
6. Conectar desde Open WebUI: `Admin Settings → Connections` → añadir conexión "OpenAI API" apuntando a `http://litellm:4000/v1` (hostname interno del clúster) usando una *virtual key* generada desde LiteLLM en vez de la credencial AWS real — así Open WebUI nunca ve la credencial de AWS directamente, y el uso queda medido y limitado por LiteLLM.
7. Coste: a diferencia del resto del clúster (100 % local, sin gasto variable), Bedrock factura por token consumido — usar los presupuestos y alertas de LiteLLM para evitar sorpresas, y decidir conscientemente qué tareas justifican pagar por un modelo cloud frente a usar `qwen2.5` local sin coste.

Ver también mejora 21 (Bifrost) — resuelve el mismo problema con otra implementación; evaluar ambas antes de quedarse con una en producción.

### Esfuerzo estimado
Medio — el despliegue en sí es rápido; lo que requiere cuidado es el IAM de permiso mínimo y decidir la política de presupuesto/coste antes de dejarlo accesible desde Open WebUI.

---

## 21. ~~Bifrost — gateway de alto rendimiento para LLM, configurado para AWS Bedrock y Open WebUI~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

Desplegado en `pi-sonar` (no `retaco`, cambio de criterio decidido en conversación — RAM real disponible verificada con `free -h` en ambos candidatos, y aislamiento de las credenciales de AWS fuera de `pi-dns`, el nodo más expuesto del clúster). Detalle completo: `docs/23-bifrost-gateway-llm.md`.

Resumen de lo implementado:
- `pi-sonar/config/bifrost/config.json` — provider Bedrock declarativo, sin secretos en claro (todo vía `env.*`).
- Virtual key propia de Bifrost como autenticación (`enforce_auth_on_inference: true`) — no hizo falta `apikey-service`, Bifrost ya trae su propio sistema.
- `bifrost.home.arpa` en nginx (`pi-dns`) y en `shared/dns/dns-records.md` / `load-dns-records.sh`.
- Usuario IAM base (`bifrost-bedrock-base`, sin permiso de Bedrock) que solo puede asumir el rol `bifrost-bedrock-invoke` — ese rol es el único con la policy de permiso mínimo (`bedrock:InvokeModel`/`InvokeModelWithResponseStream` sobre todos los proveedores de modelo, foundation models e inference profiles, más `bedrock:ListFoundationModels` para que Bifrost valide el catálogo en vivo). Sin ninguna policy gestionada de AWS (todas son más amplias de lo necesario) y sin credenciales estáticas de Bedrock en ningún sitio — Bifrost asume el rol solo de forma nativa (`role_arn` en `bedrock_key_config`), sin perfiles AWS montados en el contenedor.

### Qué quedó fuera, por ahora

- **LiteLLM (mejora 20)** sigue sin desplegar — la comparativa quedó resuelta a favor de Bifrost por ser el despliegue más ligero (sin Postgres obligatorio); si en el futuro hace falta algo que Bifrost no cubra bien (presupuestos por equipo más maduros, ecosistema Python), retomar esa mejora.
- Sin `governance.budgets` configurado todavía (límite de gasto automático) — Bifrost lo soporta, pendiente de decidir un umbral razonable con uso real.
- `bifrost/data/` (estado de gobernanza) no entra todavía en ninguna copia de seguridad — ver la nota de la mejora 1.

### Qué hay hoy (histórico, previo a la implementación)

Mismo hueco que la mejora 20: sin gateway unificado hacia proveedores cloud. [Bifrost](https://docs.getbifrost.ai/) (Maxim AI) es la alternativa directa a LiteLLM — mismo problema (API única OpenAI-compatible sobre 20+ proveedores, incluido Bedrock), implementación distinta (Go en vez de Python), con foco explícito en rendimiento (el propio proyecto reclama <100 µs de overhead a 5k RPS) y balanceo de carga adaptativo / modo clúster.

### Qué haría falta

1. Desplegar Bifrost (`maximhq/bifrost`, [github.com/maximhq/bifrost](https://github.com/maximhq/bifrost)): `docker pull maximhq/bifrost` y `docker run -p 8080:8080 -v $(pwd)/data:/app/data maximhq/bifrost` para persistir configuración; fijar versión concreta (p. ej. `:v1.3.9`) en vez de `latest`. Variables de entorno `APP_PORT` / `APP_HOST` / `LOG_LEVEL` si hace falta ajustar el binding por defecto (`8080` / `localhost`).
2. Nodo: mismo criterio que la mejora 20 — `retaco`.
3. Configuración para AWS Bedrock, dos vías no excluyentes:
   - Web UI propia en `http://bifrost:8080` ("visual provider setup") — añadir el provider Bedrock sin tocar ficheros, más simple para un despliegue de un único nodo.
   - `config.json` declarativo si se prefiere dejarlo versionado en el repo (`config_store` en modo solo-lectura, cambios requieren reinicio) — mismo criterio de "todo en git" ya aplicado al resto del clúster (mejora 2).

Credenciales: `access_key`/`secret_key` explícitas, con el mismo IAM de permiso mínimo descrito en la mejora 20 (no crear uno nuevo). Bifrost también soporta detectar automáticamente el rol IAM del host si ambas credenciales quedan vacías — no aplica a este clúster on-prem por ahora, relevante solo si en el futuro algo del pipeline corriera dentro de AWS. Región configurable (p. ej. `eu-west-1`), con enrutamiento ponderado entre regiones si interesara failover a `us-west-2`.
4. Conectar desde Open WebUI: mismo patrón que la mejora 20 — `Admin Settings → Connections` → "OpenAI API" apuntando a `http://bifrost:8080/v1`, con la clave que Bifrost genere para ese acceso.
5. Decidir cuál de las dos (mejora 20 o esta) se queda como gateway definitivo antes de mantener ambas en producción a la vez — mismo tipo de decisión ya planteada entre Vault e Infisical (mejora 16): resuelven el mismo problema; Bifrost destaca en rendimiento/latencia bajo carga alta, LiteLLM en madurez del ecosistema Python y presupuestos por equipo. Evaluar una junto a la otra y quedarse solo con una.
6. Mismo aviso de coste que la mejora 20: Bedrock factura por AWS, a diferencia del resto del clúster.

### Esfuerzo estimado
Bajo-medio — el despliegue es aún más ligero que LiteLLM (un único contenedor, sin base de datos obligatoria); el trabajo real vuelve a ser el IAM y decidir si sustituye o convive con LiteLLM.

---

## 22. Integrar el coste de las llamadas LLM (Bifrost) en Grafana, con vigilancia y alarmas

**Prioridad: media**

### Qué hay hoy

Bifrost (`pi-sonar`, `docs/23-bifrost-gateway-llm.md`) ya calcula coste real por petición y lo expone de dos formas: su propio panel/API (`https://bifrost.home.arpa`, con usuario/contraseña de admin) y un endpoint `/metrics` en formato Prometheus estándar — confirmado en producción, incluye un contador `bifrost_cost_total` ya desglosado por modelo/proveedor/alias:

```
bifrost_cost_total{alias="anthropic.claude-sonnet-4-6", provider="bedrock", model="eu.anthropic.claude-sonnet-4-6", ...}
```

Hoy solo es visible entrando al panel de Bifrost — no aparece junto al resto de la observabilidad del clúster (Grafana en `pi-obs`, donde ya se mira todo lo demás).

### Qué haría falta

1. Añadir un `scrape_config` nuevo en `pi-obs/config/prometheus.yml` apuntando a `https://bifrost.home.arpa/metrics` (o `http://192.168.1.172:8080/metrics` directo, evitando el salto por nginx — mismo criterio que otros exporters cross-host del clúster).
2. El endpoint `/metrics` exige las credenciales de admin de Bifrost (`governance.auth_config`, ver `docs/23`) — configurar `basic_auth` en el propio `scrape_config` de Prometheus con `BIFROST_ADMIN_USERNAME`/`BIFROST_ADMIN_PASSWORD`.
3. Confirmar si Prometheus necesita alcanzar `bifrost.home.arpa` por DNS interno (Pi-hole, ya resuelto para el resto del clúster) o si hace falta la IP directa — probar ambas antes de decidir.
4. Panel nuevo en Grafana: gasto acumulado por modelo/proveedor (`bifrost_cost_total`), y si el resto de métricas expuestas lo permiten, latencia y volumen de peticiones — buscar primero un dashboard oficial de Bifrost en Grafana.com antes de construir uno desde cero, mismo criterio que el resto de dashboards importados del clúster (`docs/08-instalacion-pi2-observabilidad.md`).

**Vigilancia y alarmas sobre el coste** (antes solo apuntado como posibilidad en el punto 5, ahora parte explícita del alcance de esta mejora):

5. Regla de alerta en Grafana sobre `bifrost_cost_total` (incremento acumulado en una ventana diaria/mensual, no el contador crudo desde el arranque) por encima de un umbral a decidir — mismo patrón ya usado para la alerta de disco (mejora 3) y la de parcheo de nodos (mejora 36).
6. Conectar esa alerta al canal de notificación proactivo — `ntfy` (mejora 4, ya implementado, `docs/34-ntfy-notificaciones.md`) puede reutilizarse tal cual como *contact point*, añadiendo el matcher que corresponda a `pi-obs/config/grafana/alerting/notification-policies.yml`; hasta que esta alerta se implemente, el mecanismo ya existe y está probado (undervoltage + SAI).
7. **Evaluar también el mecanismo nativo de presupuestos de Bifrost** (`governance.budgets`, `docs/23-bifrost-gateway-llm.md`, sección "Seguimiento de coste") como alternativa o complemento a la alerta de Grafana — Bifrost ya soporta presupuestos con umbral por *virtual key* y puede avisar/bloquear directamente en el propio gateway, sin depender de que Prometheus/Grafana estén sanos en ese momento. Decidir la fuente de verdad: solo uno de los dos mecanismos, o ambos con roles distintos (Bifrost bloquea en el gateway antes de que la petición cueste dinero, Grafana avisa para visibilidad humana centralizada junto al resto de alertas del clúster). Esto sustituye la idea descartada de un aviso manual por n8n que se apuntaba en `docs/23`.
8. **"U otros"**: hoy Bifrost es el único gateway de coste LLM del clúster — si en el futuro se añaden más proveedores/gateways o interesa una herramienta de FinOps dedicada, generalizar este mismo panel/alerta en vez de duplicar el mecanismo; no es necesario hoy, se deja anotado para no perder el contexto si surge.

### Esfuerzo estimado
Bajo-medio — la parte de métricas reutiliza infraestructura ya montada (Prometheus, Grafana, patrón de `scrape_config` con auth); el trabajo real añadido es decidir umbrales de coste razonables y si la alerta vive en Grafana, en el propio Bifrost, o en ambos.

---

## 23. ~~Mover `logs.db`/`config.db` de Bifrost a Postgres centralizado~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

Base `bifrost` creada en `postgres-main` (retaco) con `create-postgres-db.sh`, `config_store` y `logs_store` de `pi-sonar/config/bifrost/config.json` cambiados de `sqlite` a `postgres` (misma base para ambos, credenciales vía `env.BIFROST_DB_PASSWORD`, host/usuario/db_name hardcodeados por no ser secretos). Empezado de cero, sin migrar el `config.db`/`logs.db` previos (presupuesto y logs sin valor real que preservar, mismo criterio que la migración de Open WebUI). Detalle completo: `docs/23-bifrost-gateway-llm.md`, sección "Postgres centralizado".

Verificado end-to-end tras el redespliegue: 58 tablas creadas en la base `bifrost` por las migraciones propias de Bifrost, panel de gobernanza (`/api/governance/budgets`) sirviendo desde Postgres, una petición de inferencia real (Bedrock) quedó registrada en la tabla `logs`. `bifrost/data/config.db`/`logs.db` (SQLite) quedan en el disco de `pi-sonar` sin usarse, sin borrar — mismo criterio de dejar backups en vez de eliminar que el resto del repo.

Con esto, `bifrost/data/` en Postgres queda cubierto automáticamente por `shared/scripts/backup-postgres.sh` (mejora 1) — cierra el punto pendiente en `docs/23` sección "Operación".

### Qué hay hoy (histórico, previo a la implementación)

Bifrost (`pi-sonar`) guarda su estado en dos SQLite locales dentro del volumen montado (`docs/23-bifrost-gateway-llm.md`, sección "Dónde se almacena todo lo que se ve en el panel"): `logs.db` (historial de peticiones — modelo, coste, latencia, resumen del contenido) y `config.db` (gobernanza — virtual keys, presupuestos y su gasto acumulado). Confirmado que Bifrost ya aplica retención automática (365 días, purga periódica en segundo plano), así que no es un crecimiento *sin ningún control* — pero sigue siendo SQLite local en una Raspberry Pi, sin el mismo tratamiento (backups, consulta con SQL normal, robustez ante escritura concurrente) que el resto de datos de aplicación del clúster, que ya viven en `postgres-main` (n8n, sonarqube, apikeys, openwebui).

### Qué haría falta

1. Confirmado en el schema real de Bifrost (`https://www.getbifrost.ai/schema`): **tanto `config_store` como `logs_store` soportan `type: "postgres"`** de forma independiente (además `logs_store` admite `clickhouse`, pensado para volúmenes muy grandes — no hace falta aquí). Ambos con la misma forma de conexión: `host`, `port`, `user`, `password` (o `password_command`, para credenciales rotadas dinámicamente), `db_name`, `ssl_mode`, más ajustes opcionales de pool (`max_idle_conns`, `max_open_conns`, `conn_max_lifetime`).
2. Crear la base con el patrón ya establecido: `bash create-postgres-db.sh postgres-main dbadmin bifrost bifrost` (mismo script que `n8n`/`sonarqube`/`apikeys`/`openwebui`) — una única base puede alojar las tablas de `config_store` y `logs_store` a la vez (Bifrost las crea con sus propias migraciones, como ya hace hoy con SQLite), o separarlas en dos bases si se prefiere aislar gobernanza de logs.
3. En `pi-sonar/config/bifrost/config.json`, sustituir ambos `"type": "sqlite"` por `"type": "postgres"` con el bloque de conexión correspondiente (credenciales vía `env.*`, nunca en claro, mismo criterio que el resto del fichero).
4. Decidir si se migran los datos existentes de `logs.db`/`config.db` o se empieza de cero (como se hizo con la migración de Open WebUI a Postgres) — dado que el presupuesto ya se reinició una vez por el fallo de ruta corregido en `docs/23`, probablemente no hay nada valioso que preservar todavía.
5. Una vez en Postgres: se cubre automáticamente con `shared/scripts/backup-postgres.sh` (ver mejora 1) sin necesidad de un script de backup dedicado a Bifrost — cierra el punto que quedó pendiente en `docs/23` sección "Operación".

### Esfuerzo estimado
Bajo — cambio de configuración, no de arquitectura; Bifrost ya sabe hablar con Postgres nativamente. El trabajo real es decidir si se empieza de cero o se migran los datos, y confirmar que `pi-sonar` alcanza `postgres-main` en `retaco` (cross-host, mismo patrón ya probado con `sonarqube`).

---

## 24. ~~Servidor Redis/Valkey securizado (key-value + pub/sub)~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

Desplegado en `retaco` como contenedor `valkey` (`valkey/valkey:9.1.1-alpine`) — sin persistencia a propósito (`--save ""`, `--appendonly no`, uso previsto hoy: solo caché, sin consumidor real todavía), límite de memoria 256 MB con política `allkeys-lru`, expuesto como `valkey.home.arpa` (alias DNS directo, mismo patrón que `postgresql.home.arpa`). Seguridad vía ACL (no `requirepass` a secas: usuario `default` desactivado, un usuario `valkey-admin` de gestión) **y TLS** — certificado propio firmado por la CA interna del clúster (`pi-dns/config/nginx/generate-valkey-cert.sh`), `--port 0` desactiva el puerto en claro por completo. Verificado en vivo, tanto local como cross-host desde `ryzen`/`mole` vía DNS real: sin `--tls` → `Connection reset by peer`; con TLS sin autenticar → `NOAUTH`; con TLS + credenciales → `PONG`. Detalle completo, incluido el aviso de que el `aclfile` de esta versión no admite comentarios (causó un crash-loop real en el primer intento): `docs/25-valkey-cache.md`.

### Qué hay hoy (histórico, previo a la implementación)

No existe ningún almacén key-value ni sistema de pub/sub de propósito general en el clúster. El estado de aplicación vive en `postgres-main` (n8n, SonarQube, apikeys, Open WebUI, y Bifrost tras la mejora 23), y no hay ningún mecanismo de caché o mensajería ligera compartido. La propia mejora 16 (Infisical) ya identificó que necesitaría Redis como dependencia si se despliega en solitario — sería el primer consumidor natural de este servicio en vez de duplicar la pieza.

### Redis o Valkey — no son dos servicios complementarios, es la misma elección

Aclaración antes de diseñar nada: Valkey es un *fork* de Redis (mismo protocolo RESP, mismos comandos, mismas librerías cliente), nacido cuando Redis Inc. cambió la licencia de las versiones ≥ 7.4 a SSPLv1/RSALv2 — licencias no reconocidas por la OSI que restringen ofrecer Redis como servicio a terceros. No tiene sentido operar los dos productos a la vez para la misma carga: un cliente no puede distinguir uno de otro por el protocolo. La recomendación es desplegar **Valkey** como única implementación — licencia BSD-3 real, mantenido por la Linux Foundation con AWS/Google/Oracle detrás, 100 % compatible con cualquier librería cliente de Redis ya existente — mismo criterio de "FOSS de verdad, no source-available" ya aplicado en este documento a otras decisiones (Infisical sobre HashiCorp Vault por motivos distintos, Forgejo autoalojado con GitHub como espejo).

### Qué haría falta

1. **Nodo**: `retaco` — nodo de datos, siempre encendido, ya aloja `postgres-main`, Qdrant y el registry.
2. **Seguridad**:
   - ACL de Valkey (no solo `requirepass`) — un usuario por servicio consumidor, con permisos restringidos por comando y por prefijo de key/canal, mismo principio que las Machine Identities de Infisical o un usuario de Postgres por servicio.
   - TLS con el CA interno del clúster (`docs/15-ca-interna.md`) para conexiones cross-host (p. ej. desde `pi-sonar` si Bifrost llegara a usarlo); en localhost/misma red de `docker-compose`, TLS es opcional.
   - No se publica vía `nginx` (no es HTTP) — acceso limitado a la red interna de cada `docker-compose` y, si hace falta cross-host, restringido por IP a nivel de firewall, mismo patrón que `docs/17-firewall-acceso-directo.md`. El puerto no se expone a `0.0.0.0`, solo a la interfaz privada del clúster.
3. **Persistencia**: activar AOF (o RDB + AOF) solo si se le da uso real de almacén key-value y no de caché efímera — la necesidad de persistencia depende de cada consumidor, ya que pub/sub en sí no la necesita.
4. **Primer consumidor real**: la mejora 16 (Infisical) reutilizaría esta instancia en vez de desplegar su propio Redis dedicado — evita tener el mismo tipo de servicio duplicado en el clúster. Candidatos futuros: colas/rate-limiting en microservicios propios, sesiones o pub/sub de servicios que lo necesiten.
5. **Backup**: si se activa persistencia AOF/RDB, incorporarlo a `shared/scripts/backup-postgres.sh` o un script hermano — mismo criterio que el resto de datos con estado del clúster (mejora 1).

### Esfuerzo estimado
Bajo-medio — desplegar el contenedor y fijar ACL/TLS es sencillo; el trabajo real es decidir qué consumidores lo usan primero y si necesitan persistencia real o solo caché.

---

## 25. ~~Authentik — autenticación centralizada para personas, piloto en Prometheus~~ — hecho

**Prioridad: media** — **completado (alcance: infraestructura + Prometheus)**

### Qué se implementó (2026-08-10)

Authentik desplegado en `retaco`, en producción, protegiendo `prometheus.home.arpa` (hoy sin ninguna autenticación, ni propia ni de `apikey-service` — el hueco de seguridad real que motivó esta mejora) vía forward-auth con el outpost embebido. Detalle completo: `docs/27-authentik-sso.md`.

Dos decisiones que se apartan de lo previsto originalmente en el punto 2 de abajo:
- **Postgres compartido con `postgres-main`**, no dedicado — decisión consciente, distinta de la que se tomó para Infisical (ADR 0002): Authentik solo gatea login de personas, no arranque de servicios máquina, así que el radio de fallo de compartir es mucho menor aquí.
- **Sin Redis/Valkey** — versiones recientes de Authentik (confirmado con la `2026.5.6` desplegada) ya no lo necesitan, caché y tareas de fondo van sobre Postgres. La previsión original de reutilizar Valkey no hizo falta.

Secretos (contraseña de Postgres, `AUTHENTIK_SECRET_KEY`) vía Infisical desde el primer despliegue, mismo mecanismo que `apikey-service` — no estaba en el plan original de este documento, se añadió porque para entonces Infisical ya estaba en producción (mejora 16).

Esta mejora se da por completada con Prometheus protegido y el patrón de integración forward-auth validado — no con todos los servicios/paneles del clúster ya cubiertos. Grafana/Portainer vía OIDC nativo y evaluar SonarQube/Pi-hole pasan a la mejora 29, mismo criterio que se usó para separar Infisical (mejora 16) del resto de servicios pendientes (mejora 28).

### Qué hay hoy (histórico, previo a la implementación)

`apikey-service` resuelve la autenticación **máquina a máquina** (n8n, Open WebUI, curl) contra servicios sin auth propia, vía `X-Api-Key` — ver `docs/06-instalacion-pi1-dns.md`. Pero no existía nada equivalente para **personas**: cada panel de administración del clúster tenía su propia cuenta, separada e independiente — Grafana, Portainer, SonarQube, Pi-hole, Vaultwarden, Open WebUI, n8n, cada uno con su propio usuario/contraseña, sin ningún inicio de sesión único entre ellos.

Peor todavía: **`prometheus.home.arpa` no tenía ninguna autenticación, ni propia ni de `apikey-service`** — cualquiera en la LAN podía consultar todas las métricas del clúster sin credencial alguna. No era una elección deliberada documentada en ningún sitio, era simplemente un hueco — Prometheus no trae login propio y nunca se le puso `apikey-service` delante, a diferencia de `ollama.home.arpa`/`epub2pdf.home.arpa`/etc.

### Qué se planteó originalmente (referencia histórica)

1. **Qué es y qué resuelve**: [Authentik](https://goauthentik.io/) (self-hosted, MIT) es un proveedor de identidad — SSO real vía OIDC/SAML para las apps que lo soportan nativamente, más un modo *forward-auth* (proxy provider + `outpost`) para las que no, con el mismo mecanismo de fondo que ya usa `apikey-service` (`auth_request` de nginx), pero para personas con sesión de navegador en vez de una cabecera `X-Api-Key` estática. **Implementado tal cual.**
2. ~~**Nodo y dependencias**: `retaco`... Postgres (reutilizar `postgres-main`)... y Redis (reutilizar el Valkey de la mejora 24...)~~ **Redis superado por la implementación real** — ver "Qué se implementó" arriba, no hizo falta.
3. **Dos mecanismos de integración, elegir por servicio, no uno solo para todos**: OIDC nativo donde exista (Grafana, Portainer), forward-auth donde no (Prometheus). **El caso de Prometheus, implementado y verificado; OIDC nativo pasa a la mejora 29.**
4. **Qué queda fuera a propósito**: `apikey-service` no desaparece, Vaultwarden tampoco se pone detrás de Authentik. **Vigente sin cambios.**
5. **Migración incremental, empezando por el hueco real**: primero `prometheus.home.arpa`. **Hecho — el resto pasa a la mejora 29.**
6. **Publicación**: `authentik.home.arpa` en nginx (`pi-dns`), mismo patrón de siempre. **Implementado tal cual**, más un detalle no previsto: el snippet `authentik-auth.conf` es un fichero nuevo que hay que montar explícitamente en `pi-dns/docker-compose.yml` (nginx monta cada fichero de config individual, no el directorio) — un `nginx -s reload` no basta, hace falta recrear el contenedor.

### Esfuerzo estimado
Alto — confirmado: el despliegue del servidor en sí fue rápido (menos superficie de la esperada al no hacer falta Redis), el esfuerzo real estuvo en la integración forward-auth completa (Proxy Provider, outpost embebido — que no se asignó solo, hubo que añadirlo a mano —, snippet de nginx, verificación end-to-end). OIDC nativo por app (mejora 29) es un tipo de integración distinto, no directamente reutilizable de esto.

---

## 26. Investigar tool-calling fiable: modelos locales de Ollama y modelos Bedrock/Claude vía Bifrost

**Prioridad: media**

### Qué hay hoy

Al probar la mejora 17 (Open Terminal en modo MCP, `docs/24-open-terminal-mcp.md`) con distintos modelos desde Open WebUI, ninguno completó una llamada de herramienta de extremo a extremo:

- **Modelos locales de Ollama** (`qwen2.5:14b`, `qwen2.5:32b`, `qwen3.5:9b`, `qwen3.5:27b`, todos probados) — ninguno hace tool-calling real: en vez de invocar la herramienta, el modelo escribe texto que imita la sintaxis de una llamada de función (`</function_calls>`, `<parameter=...>`) y se inventa una salida falsa. Sorprendente porque los benchmarks públicos de 2026 dan a la familia Qwen como de las más fiables en tool-calling — apunta a un problema de plantilla de chat en Ollama para estas etiquetas concretas, no del modelo en sí, pero no se ha confirmado.
- **Claude Sonnet 4.6 vía Bifrost (Bedrock)** — sí genera la llamada de función correctamente, pero el turno siguiente (con el resultado de la herramienta) falla con `messages.N.content.0.thinking.signature: Field required`. Bug conocido en pasarelas que traducen entre el formato OpenAI-compatible (el que habla Open WebUI) y la Converse API de Bedrock: el bloque `thinking` de *extended thinking* pierde su firma criptográfica al reconstruirse para el turno siguiente. Mismo patrón reportado en otras pasarelas ([spring-ai#6413](https://github.com/spring-projects/spring-ai/issues/6413), [opencode#6176](https://github.com/anomalyco/opencode/issues/6176)) — no es un fallo exclusivo de este clúster, pero tampoco hay confirmación de que Bifrost lo tenga resuelto en la versión desplegada (`v1.6.8`).

Con esto, la mejora 17 queda con el camino de red/autenticación verificado de extremo a extremo (MCP↔nginx↔apikey-service, `curl` con y sin `X-Api-Key`), pero sin ningún modelo confirmado usando la herramienta de verdad desde un chat real todavía.

### Qué haría falta

1. **Modelos locales**: inspeccionar la plantilla de chat real que usa Ollama para cada etiqueta (`ollama show <modelo> --template`) y confirmar si referencia `.Tools`/`.ToolCalls` correctamente — comparar entre `qwen2.5`/`qwen3.5` y un modelo con soporte de tool-calling históricamente muy probado en Ollama (p. ej. Llama 3.1/3.3, o una variante explícitamente etiquetada para herramientas) para aislar si el problema es de plantilla/etiqueta concreta o algo más general en cómo Open WebUI habla con Ollama.
2. **Bedrock/Claude**: comprobar si Open WebUI expone algún control de *reasoning effort*/*extended thinking* por modelo y si desactivarlo evita el error (dado que la firma solo hace falta cuando se usa thinking). Revisar el changelog/issues de Bifrost (`v1.6.8` en `pi-sonar`) por si ya hay una corrección conocida antes de investigar más a fondo. Si hace falta profundizar, aislar con una petición `curl` directa contra Bifrost reproduciendo un turno de tool-use con thinking, para saber si el fallo está en la traducción de Bifrost o en cómo Open WebUI reconstruye el historial.
3. **Documentar el resultado** en `docs/24-open-terminal-mcp.md` (tabla de troubleshooting, ya con ambos síntomas apuntados como pendientes) en cuanto haya un modelo confirmado funcionando de extremo a extremo con Open Terminal.

### Esfuerzo estimado
Medio — no es un despliegue nuevo, es investigación dirigida sobre dos sistemas ya desplegados (Ollama, Bifrost); el tiempo real depende de si el fallo de Ollama resulta ser una plantilla mal etiquetada (rápido de confirmar) o algo más profundo, y de si Bifrost ya trae corregido el problema de la firma de `thinking` en alguna versión posterior a la desplegada.

---

## 27. Activar TLS en `postgres-main`

**Prioridad: media**

### Qué hay hoy

`postgres-main` (retaco) no usa TLS — protegido solo por contraseña, mismo criterio que tenía Valkey antes de la mejora 24 (`docs/25-valkey-cache.md`). A diferencia de Valkey, que se activó sin ningún consumidor real que migrar, `postgres-main` ya lo usan n8n, SonarQube, apikey-service, Open WebUI y `postgres-exporter` (pi-obs) — cualquier cambio aquí tiene que convivir con clientes ya en producción, no es un lienzo en blanco.

### Qué haría falta

1. Certificado propio de Postgres, firmado por la CA interna del clúster (`docs/15-ca-interna.md`) — mismo patrón que se acaba de usar para Valkey (`pi-dns/config/nginx/generate-valkey-cert.sh` como plantilla directa para un `generate-postgres-cert.sh` equivalente, CN `postgresql.home.arpa`).
2. Activar `ssl = on` en `postgres-main` (imagen oficial `postgres:16-alpine` lo soporta de fábrica vía `ssl_cert_file`/`ssl_key_file`, sin parches) — probar primero con `ssl = on` sin forzar (`hostssl` opcional en `pg_hba.conf`), para no cortar a ningún cliente existente de golpe.
3. Migrar cada consumidor a `sslmode=require` (o `verify-ca`/`verify-full` para validar contra la CA interna) en su cadena de conexión, uno a uno: n8n (`DB_POSTGRESDB_*`), SonarQube, apikey-service, Open WebUI (`DATABASE_URL`), y el DSN de `postgres-exporter` en pi-obs — confirmando cada uno antes de pasar al siguiente, no todos a la vez.
4. Solo cuando todos los consumidores confirmen `sslmode=require`, endurecer `pg_hba.conf` a `hostssl` exclusivamente (rechaza conexiones sin TLS) — hasta entonces, dejar `host` y `hostssl` coexistiendo.
5. Documentar en `docs/05-instalacion-retaco.md` (o un `docs/27-*` propio si el cambio es lo bastante grande — `docs/26` ya ocupado por Infisical) siguiendo el mismo criterio de honestidad que el resto de mejoras completadas — probar de verdad cada consumidor, no dar por hecho que "debería funcionar".

### Esfuerzo estimado
Medio-alto — no por la parte técnica de Postgres en sí (activar TLS es sencillo con la CA ya existente), sino por el número de consumidores reales a migrar sin cortar nada que ya funciona; hacerlo bien implica probar uno a uno, no un cambio atómico.

---

## 28. ~~Migrar el resto de servicios del clúster a Infisical~~ — hecho

**Prioridad: media** — **completado (parcial: 9 de los "candidatos limpios")**

### Qué se implementó (2026-08-19)

Migrados y verificados en producción: `n8n-main`, `qdrant`, `open-webui`, `open-terminal-mcp` (retaco), `n8n-aux`, `rsshub`, `vaultwarden` (pi-utils), `sonarqube`, `bifrost` (pi-sonar) — detalle completo, incluidos tres hallazgos no anticipados por la mejora 16, en `docs/26-infisical-secretos.md` (sección "Estado actual — mejora 28 completada") y `docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md`:

1. **El nombre de la clave en Infisical debe coincidir con el que la app consume de verdad**, no con el nombre de variable que usaba el `.env` de este repo — el volcado masivo de la mejora 16 importó los nombres "tal cual", que en 6 de los 9 servicios no coincidían (p. ej. `N8N_DB_PASSWORD` → en realidad hace falta `DB_POSTGRESDB_PASSWORD`). Hubo que renombrar claves en Infisical antes de conectar cada wrapper. `open-webui` fue el caso especial: `DATABASE_URL` pasó a ser un secreto con la cadena de conexión completa, no una contraseña suelta.
2. **Un healthcheck que referencie un secreto migrado directamente deja de funcionar** — `docker exec` (así ejecuta Compose el healthcheck) no ve el entorno dinámico del proceso sustituido por `infisical run`, solo el estático del contenedor. Corregido en `rsshub` aceptando 200 o 403 como "sano" (mismo criterio que `registry`).
3. **Un secreto migrado puede seguir haciendo falta en claro en el `.env`** si otro servicio sin migrar lo consume — `postgres-main` usa `N8N_DB_PASSWORD` en su propio script de init; se retiró por rutina al migrar `n8n-main` y hubo que restaurarlo.

Quedó sin resolver la duda de si `BIFROST_ADMIN_USERNAME`/`_PASSWORD` se releen en cada arranque o solo la primera vez (como Grafana) — están migrados igualmente (mismo valor, sin romper nada), pero la comprobación en vivo quedó pendiente.

Fuera de esta ronda a propósito: `registry` (bajo valor), `postgres-exporter`/`whisper-service`/`vllm` (sin secretos migrables hoy) y los cuatro bloqueados por "solo primer arranque" (`postgres-main`, `postgres-infisical`, `grafana`, `tailscale`) — ver inventario completo en `docs/26`.

### Qué hay hoy (histórico, previo a la implementación)

La mejora 16 dejó Infisical desplegado en producción y el mecanismo de inyección de secretos validado con un único servicio real, `apikey-service` — detalle completo en `docs/26-infisical-secretos.md`. El resto de servicios del clúster con secretos en su `.env` siguen exactamente igual que antes de la mejora 16: valores en claro, copiados a mano desde Vaultwarden, sin identidad de máquina propia ni rotación independiente.

`docs/26-infisical-secretos.md` ya tiene la auditoría completa de los 27 servicios del clúster, servicio por servicio, clasificados en cuatro categorías — no hace falta repetirla aquí, solo enlazarla:

- **Candidatos limpios**, mismo patrón que `apikey-service` sin obstáculos conocidos: `markitdown-service`, `epub2pdf-service`, `pdf2chunks-service`, `crawl4ai-scraper-service`, `open-terminal-mcp`, `n8n-main`, `n8n-aux`, `qdrant`, `vaultwarden`, `rsshub`, `sonarqube`, la mayoría de variables de `bifrost`, `open-webui` (con la particularidad de su entrypoint ya sobreescrito), `postgres-exporter`, `whisper-service`, `vllm`. De estos, **10 ya tienen sus secretos reales pre-cargados en Infisical** (importación masiva hecha el 2026-08-10, ver `docs/26` sección "Secretos pre-cargados") — falta solo conectar el `docker-compose.yml` de cada uno, no volver a copiar valores a mano.
- **Bloqueados por falta de shell en la imagen**: `portainer`, `otel-collector` (este último sin secretos reales de todas formas).
- **Bloqueados por comportamiento "solo al primer arranque"** (cambiar la variable de entorno no cambia la credencial real una vez inicializado el servicio): `postgres-main`, `postgres-infisical`, `grafana`, `tailscale` — necesitan un mecanismo distinto (aplicar el secreto vía la API propia de cada servicio tras leerlo de Infisical), no el wrapper genérico.
- **Secreto real en fichero, no en variable de entorno**: `registry` (el credential de `docker login` vive en `htpasswd`).

### Qué haría falta

1. Completar la identidad de máquina + acceso al proyecto (Viewer, restringido a su carpeta) para cada uno de los "candidatos limpios" — algunos ya tienen el secreto importado, otros necesitan también el volcado inicial (ver "Importación masiva de secretos" en `docs/26`).
2. Por cada uno: bind-mount del binario CLI en el nodo (`shared/scripts/deploy-infisical-cli.sh <nodo>`, si no está ya desplegado ahí), averiguar `ENTRYPOINT`/`CMD` real si es de terceros, editar el `docker-compose.yml` con el wrapper de dos pasos, desplegar y verificar de extremo a extremo — mismo procedimiento ya validado con `apikey-service`, repetible.
3. Prestar atención particular a `open-webui` (combinar el wrapper con su entrypoint ya existente, que combina el bundle de `certifi` con la CA interna) y a `bifrost` (confirmar antes si `BIFROST_ADMIN_USERNAME`/`_PASSWORD` son "cada arranque" o "solo primera vez", pendiente desde la auditoría de la mejora 16).
4. Decidir un mecanismo para los bloqueados por "solo al primer arranque" (`postgres-main`, `postgres-infisical`, `grafana`, `tailscale`) — o aceptarlos como excepción permanente, documentada, si el esfuerzo no compensa frente a lo poco que rotan hoy.
5. Decidir un mecanismo para `registry` (renderizar `htpasswd` a partir de un secreto de Infisical al arrancar) o aceptarlo también como excepción documentada.
6. Reorganizar los secretos ya importados en sus carpetas correspondientes si hiciera falta ajustar el reparto original.
7. Mantener viva la identidad `bulk-import` (rol Editor, creada durante la mejora 16) para este trabajo — decisión consciente de no revocarla todavía, dado que se va a seguir usando para más importaciones masivas durante esta mejora. Revisar si conviene revocarla una vez migrado el último servicio de la lista de candidatos limpios.

### Esfuerzo estimado
Medio — el patrón ya está validado y documentado paso a paso (`docs/26`); el trabajo es mecánico y repetible por servicio, salvo los casos bloqueados (postgres/grafana/tailscale/registry), que si se abordan necesitan diseño propio, no solo repetición.

---

## 29. Integrar Authentik en el resto de paneles del clúster (OIDC nativo)

**Prioridad: media**

### Qué hay hoy

La mejora 25 dejó Authentik desplegado en producción, con `prometheus.home.arpa` protegido vía forward-auth como piloto — detalle completo en `docs/27-authentik-sso.md`. El resto de paneles de administración del clúster (Grafana, Portainer, SonarQube, Pi-hole, n8n) siguen exactamente igual que antes: cuentas propias, separadas, sin sesión única entre ellas.

Auditoría adicional (2026-08-10): de todos los servicios protegidos hoy con `apikey-service` (pensado para consumidores máquina, `X-Api-Key`), se revisó cuáles tienen además una GUI real para personas — candidato a migrar de `X-Api-Key` a Authentik, no solo los que ya carecían de protección como Prometheus. Solo uno la tiene:

- **`comfyui.home.arpa`** — interfaz web de edición de nodos (generación de imágenes), uso interactivo real por una persona. Protegerla hoy con `X-Api-Key` es incómodo de verdad (un navegador normal no manda esa cabecera al cargar la página) — candidata clara a forward-auth.
- El resto de servicios tras `apikey-auth.conf` (`ollama`, `vllm`, `epub2pdf`, `pdf2chunks`, `markitdown`, `crawl4ai.scraper`, `open-terminal`) son APIs puras sin GUI propia (confirmado revisando `services/*/src` — como mucho Swagger `/docs` autogenerado) o un transporte MCP sin interfaz (`open-terminal`, en modo `streamable-http` en este despliegue) — consumidores máquina de verdad, `apikey-service` sigue siendo el mecanismo correcto para ellos, no hay nada que migrar.

### Qué haría falta

1. **Grafana y Portainer, vía OIDC nativo** — ambos lo traen de serie (Community Edition incluida), preferible a forward-auth siempre que exista: da identidad real dentro de la propia app (usuario, grupos, roles), no solo un "sí/no" en la puerta. Por cada uno: crear un OAuth2/OIDC Provider + Application en Authentik, configurar el cliente OIDC correspondiente en la app (`GF_AUTH_GENERIC_OAUTH_*` en Grafana; variables equivalentes en Portainer), probar sin cortar el acceso con la cuenta local existente hasta confirmar que el login SSO funciona.
2. **ComfyUI, vía forward-auth** — mismo patrón que Prometheus (`authentik-auth.conf`, modo single-application obligatorio — ver `docs/27-authentik-sso.md` sección de la Public Suffix List). A diferencia de Prometheus, esto SÍ sustituye un mecanismo de auth ya existente (`X-Api-Key`) — coordinar el cambio para no dejar la GUI sin ninguna protección durante la transición (desplegar Authentik delante primero, confirmar que funciona, solo entonces quitar `apikey-auth.conf` del bloque).
3. **Evaluar SonarQube y Pi-hole** — login propio ya débil/único en ambos hoy; decidir si compensa forward-auth (mismo patrón que Prometheus, `authentik-auth.conf` ya reutilizable) o dejarlos como están.
4. **n8n** — Community Edition no trae SSO propio (solo Enterprise); candidato a forward-auth si se hace, menor prioridad que los anteriores (n8n ya tiene su propio basic auth activo, no es un hueco abierto como era Prometheus).
4. **Cookie domain compartido**: el Proxy Provider de Prometheus ya se configuró en modo *domain-level* con `Cookie domain=home.arpa` — cualquier servicio nuevo protegido con forward-auth bajo ese mismo Provider comparte sesión automáticamente, sin volver a iniciar sesión. Para los servicios con OIDC nativo (Grafana/Portainer) esto no aplica igual — cada uno gestiona su propia sesión tras el login inicial vía Authentik, aunque el propio login pase por la misma pantalla de Authentik.
5. Decidir grupos/políticas de autorización si hace falta distinguir accesos (p. ej. no todos los que entran a Grafana deberían poder administrar Portainer) — hasta ahora solo existe el usuario admin único, sin necesidad real de grupos todavía.

### Esfuerzo estimado
Medio — el patrón forward-auth ya está resuelto y documentado (`docs/27`); lo nuevo aquí es la integración OIDC nativa por app, que es un mecanismo distinto (configuración dentro de cada aplicación, no solo en nginx) y hay que probarlo una app a la vez sin cortar el acceso existente mientras se confirma.

---

## 30. Entorno de notebooks en el clúster (JupyterLab / code-server) para estudios de datos

**Prioridad: baja-media**

### Qué hay hoy

No existe ningún entorno de notebooks en el clúster. Las pruebas de análisis de datos se hacen hoy con el editor de notebooks de **Visual Studio Code** en la máquina de trabajo (normalmente `ryzen`/`mole`), con el kernel corriendo en local.

Eso ya cubre bastante: editor, depurador, panel de variables, git integrado y asistente de IA delante, sobre la mejor máquina disponible del conjunto (62 GiB de RAM, 24 núcleos, dos GPUs) — muy por encima de cualquier nodo donde se instalaría el servicio. No hay mantenimiento, ni superficie de ataque nueva, ni copia de seguridad nueva que gestionar.

Sus límites reales, que son exactamente los que justificarían montar el servicio:

- **El kernel muere con la sesión de escritorio.** Si se cierra el portátil o se apaga `mole` (que está pensado precisamente para apagarse cuando no se usa, `docs/19-wake-on-lan.md`), el trabajo en curso se pierde. Un proceso de *embeddings* de decenas de miles de documentos contra Qdrant no sobrevive a eso.
- **El entorno no es reproducible ni está versionado.** Vive en el `~` de la máquina de trabajo; al volver al notebook meses después, el entorno que lo hacía funcionar ya no existe.
- **Los ficheros de entrada/salida acaban en disco local**, no en el NAS, y las credenciales de Postgres/Qdrant terminan en `.env` sueltos por el `$HOME` en vez de en Infisical (mejoras 16/28).

### Punto de partida: no es una decisión excluyente

VS Code se conecta a un servidor Jupyter remoto ya existente (`Select Kernel → Existing Jupyter Server → URL + token`). Es decir, el planteamiento correcto no es "JupyterLab **o** VS Code", sino el mismo criterio que ya se aplicó a Postgres: **el motor vive en el clúster, el cliente es el que apetezca en cada momento**. Se instala el servidor como kernel remoto siempre encendido y se sigue usando la interfaz de VS Code cuando se trabaja desde el escritorio.

Con ese matiz, el servicio solo compensa cuando aparece alguna de estas tres necesidades — antes de eso, VS Code en local es la mejor opción y no hay nada que instalar:

1. Trabajos que duren más que la sesión de escritorio.
2. Querer abrir el notebook desde otro dispositivo (tablet, otro PC, remoto vía Tailscale).
3. Querer un entorno de dependencias reproducible y compartible con otros consumidores (n8n, por ejemplo).

### Ventajas de tenerlo en el clúster

1. **Ejecución que sobrevive a la sesión.** Es la ventaja fuerte y la única que VS Code en local no puede replicar de ninguna manera: notebook lanzado, portátil cerrado, resultado al día siguiente.
2. **Está al lado de los datos.** En `retaco` conviven `postgres-main`, `qdrant` y el registry: consultas y volcados a velocidad de red local del contenedor, sin sacar conjuntos de datos grandes a la LAN.
3. **Entorno único y versionado.** Una imagen propia en `services/` (`pandas`/`polars`/`duckdb`/`psycopg`/`qdrant-client` fijados), construida y publicada como los otros seis servicios (`make build` → `registry.home.arpa`), multi-arch si alguna vez tuviera que correr en una Pi.
4. **Encaja limpio en los patrones ya existentes**: bloque en nginx sobre TLS interno, registro DNS, fila en el `README.md`, y protección con Authentik (mejora 25, forward-auth) por ser una GUI de persona — no con `apikey-service`, que es para consumidores máquina; mismo criterio ya razonado para ComfyUI en la mejora 29. Acceso desde fuera vía Tailscale sin abrir nada nuevo al exterior.
5. **NFS del NAS** para entradas y salidas: montar `ketekasko:/volume1/nfs-data` en el host y hacer *bind mount* al contenedor. Ojo — en la práctica es **NFSv3** (`-o vers=3`), el v4 quedó pendiente por el pseudo-root que UGOS Pro no expone (`docs/21-configuracion-nas-ugreen.md` y mejora 10 de este documento).
6. **Secretos vía Infisical** en lugar de `.env` dispersos por el `$HOME`, que es además el camino en el que ya está el clúster.

### Inconvenientes, con los números reales del clúster (medidos 2026-08-12)

| Inconveniente | Concreción |
|---|---|
| **Contención de memoria** | `retaco` tiene 13 GiB totales y 8,3 GiB disponibles, compartidos con `postgres-main`, `qdrant`, `n8n-main`, `registry`, `open-terminal`, Infisical y Authentik. Un `read_csv` descuidado puede invocar al OOM killer **en el nodo de las bases de datos**. `mem_limit: 4g` no es opcional aquí, es requisito de entrada — y con la sintaxis de Compose v2 (`mem_limit`, no `deploy.resources.limits`, que es sintaxis de Swarm; ver el comentario en `pi-utils/docker-compose.yml`). |
| **Es ejecución de código arbitrario con la red del nodo** | Exactamente el mismo tipo de decisión ya documentada para `open-terminal` (mejora 17) y Floci (mejora 14). Desde ese contenedor se alcanza `postgres-main`, que está publicado a la LAN a propósito. Mitigación: rol dedicado por proyecto vía `shared/scripts/create-postgres-db.sh`, de solo lectura donde se pueda, **nunca** el rol admin. |
| **Estado nuevo que respaldar** | Los notebooks son datos. Otro directorio en la rotación de copias de seguridad, y excluido de watchtower por convención (es un servicio con estado, `docs/16-mantenimiento-actualizaciones.md`). |
| **Higiene con git** | Los `.ipynb` versionan las salidas dentro del JSON: diffs ilegibles, y SonarQube no analiza notebooks. Se corrige con `jupytext` (pareja `.py` sincronizada) o eligiendo Marimo (ver alternativas). |
| **Nodo equivocado = ventaja perdida** | En `ryzen` habría GPU y RAM de sobra, pero es el nodo que se apaga cuando no se usa: se pierde justo el "sobrevive a la sesión", que era el motivo de instalarlo. Mismo razonamiento por el que `open-terminal` acabó en `retaco` y no en `mole` (mejora 17). |
| **Las Pi no dan el perfil** | `pi-utils`: 7,7 GiB de RAM, disco al 56% de 117 GB, arm64. El trabajo con datos irá mal y algunas ruedas pesadas dan guerra en ARM. |
| **Otro entorno de dependencias que mantener** | Un séptimo `pyproject.toml` que puede divergir del resto. |

### Dónde ponerlo

**`retaco`, con `mem_limit: 4g` y `cpus` acotados.** Es donde están los datos y es un nodo siempre encendido — los dos criterios que importan. Verificar la carga en vivo antes de desplegar, igual que se hizo con `open-terminal` (mejora 17).

Si en algún momento hiciera falta GPU (embeddings locales, entrenamientos de juguete), eso **no** es un caso de "notebook siempre encendido": ahí se lanza un kernel puntual en `mole` desde el propio VS Code, respetando las reglas de alternancia de GPU (`ryzen/switch-llm-backend.sh` / `switch-gpu1-backend.sh`, `docs/07-instalacion-ryzen.md`).

### Alternativas evaluadas

- **`code-server` / `openvscode-server`** — VS Code completo en el navegador: el mismo editor de notebooks que ya se usa, más terminal, git y extensiones, en un único servicio. **Es la opción preferida si el objetivo es "lo mismo que ahora, pero en el clúster"**, porque conserva íntegra la experiencia actual en vez de obligar a aprender otra interfaz.
- **JupyterLab** — la opción clásica; mejor si lo que se quiere es específicamente el ecosistema Jupyter (widgets, extensiones propias) o servir el kernel a varios clientes distintos.
- **Marimo** — notebooks reactivos guardados como `.py` puros: diffs limpios en git, sin estado oculto por orden de ejecución, y cualquier notebook se puede servir como aplicación web. Encaja muy bien con un repositorio que se toma en serio el versionado, pero supone un cambio de mentalidad respecto a Jupyter.
- **JupyterHub** — descartado: es multiusuario, puro coste operativo para un solo usuario.
- **No instalar nada** — `open-terminal-mcp` (mejora 17, ya desplegado en `retaco`) expone ejecución de notebooks en su API, pero está pensado para que lo consuman los LLM desde Open WebUI y n8n, no para trabajo interactivo de una persona. No cuenta como sustituto.

### Qué haría falta

1. Elegir producto según el criterio de arriba (por defecto `code-server`; JupyterLab si se quiere el ecosistema Jupyter; Marimo si prima la higiene en git).
2. Desplegar en `retaco` con `mem_limit: 4g`, `cpus` acotados y volumen dedicado para los notebooks — comprobando la memoria libre real del nodo justo antes.
3. Imagen propia en `services/<nombre>/` con las dependencias fijadas (`pandas`/`polars`/`duckdb`/`psycopg`/`qdrant-client`), publicada en `registry.home.arpa` con `make build` — no construida por el `docker-compose.yml` del nodo.
4. Montar el NFS del NAS en el host (`-o vers=3`, ruta real del export confirmada con `showmount -e`) y hacer *bind mount* al contenedor para ficheros de entrada/salida.
5. Rol de Postgres dedicado con `shared/scripts/create-postgres-db.sh`, de solo lectura donde sea posible; nunca reutilizar el rol admin ni el de otro proyecto.
6. Secretos en Infisical siguiendo el patrón de `apikey-service` (`docs/26-infisical-secretos.md`), no en un `.env` en claro.
7. Exponer como `<nombre>.home.arpa`: bloque en nginx (recordar la ruta real del *bind mount* en `pi-dns`, `/srv/homelab/pi-dns/nginx/conf/`), añadir al SAN del certificado interno, registro DNS en Pi-hole + `shared/dns/dns-records.md`, fila en el `README.md` y tarjeta en `index.home.arpa`.
8. Protegerlo con **Authentik** (forward-auth, `authentik-auth.conf`, `docs/27-authentik-sso.md`) — es una GUI de persona, no una API de máquina.
9. Incluir el volumen de notebooks en la rotación de copias de seguridad y **no** ponerle la etiqueta de watchtower.
10. Decidir la estrategia de versionado de notebooks (`jupytext` si se elige Jupyter/code-server) antes de acumular `.ipynb` con salidas en el repositorio.

### Esfuerzo estimado

Bajo-medio — el contenedor en sí es sencillo y todos los patrones que necesita (nginx + TLS interno, Authentik, Infisical, registry propio, límites de memoria) están ya resueltos y documentados. El trabajo real está en fijar el entorno de dependencias y en no desestabilizar `retaco`.

---

## 31. Nexus (u alternativa) como repositorio centralizado de paquetes, integrado con Forgejo

**Prioridad: baja — experimento deliberado, no cubre ninguna carencia operativa hoy**

### Qué hay hoy

`registry.home.arpa` (`registry:2.8.3`, mejora 8) solo hace Docker/OCI, sin proxy/cache de upstreams ni control de qué versiones de terceros entran al clúster. Forgejo (mejora 7) todavía no está desplegado; una vez lo esté, su Package Registry integrado cubrirá varios formatos (npm, PyPI, Maven, generic, container...) pero sin capacidad madura de proxy/cache de registries públicos (`docs/22`, sección 7.4, punto 1, ya apuntaba esto como pendiente de evaluar). Ningún paquete pip/npm de terceros pasa hoy por ningún punto de control: cada build tira directo contra `pypi.org`/`registry.npmjs.org`, sin capacidad de fijar versiones permitidas ni de seguir funcionando si el upstream cae.

Motivación explícita de esta mejora, más allá de la necesidad técnica: usar un repositorio centralizado de paquetes al estilo de un proyecto de empresa real es en sí mismo uno de los objetivos declarados de este clúster (aprendizaje/comparativa en hardware controlado), no solo una solución a un problema concreto — igual que Floci (mejora 14) o `open-terminal` (mejora 17).

### Qué haría falta

#### 31.1 Instalación de Nexus (si se elige esa opción)

1. Nodo: `retaco` es el candidato natural (siempre encendido, ya multi-tenant) — pero ver el aviso de memoria en "Alternativas evaluadas" antes de decidirlo sin más.
2. Almacenamiento: blob store de tipo `File` contra un punto de montaje NFS del NAS (`ketekasko:/volume1/nfs-data`, NFSv3 — `docs/21-configuracion-nas-ugreen.md`), *bind mount* al contenedor, mismo patrón que se plantea en la mejora 30. Un blob store S3 real (contra MinIO o similar) queda fuera de alcance de esta mejora — no aporta nada sobre NFS para un solo nodo sin alta disponibilidad, y añadiría otro servicio con estado que mantener.
3. `nexus.home.arpa` vía nginx en `pi-dns`, TLS con la CA interna, registro DNS (`shared/dns/dns-records.md` + Pi-hole), fila en el `README.md` raíz y tarjeta en `index.home.arpa`.
4. Credenciales admin y tokens de los repos proxy en Infisical, siguiendo el patrón de `apikey-service`/mejora 16, no en un `.env` en claro.
5. Protegerlo con Authentik (forward-auth, mejora 25/29) — es una consola de administración de persona, no una API de máquina.

#### 31.2 Integración con Forgejo

1. Cuando exista Forgejo Actions (mejora 7.3), sus builds npm/pip/Maven deben apuntar al proxy de Nexus en vez de directo a internet — reduce tráfico repetido y da un punto único de control.
2. Decidir la relación entre ambos, no es excluyente: Forgejo Package Registry para artefactos propios versionados junto al código (equivalente al repo `raw` que se planteó para `capataz-frontend`), Nexus como proxy/cache de dependencias de terceros (pip, npm, y opcionalmente Maven Central/Docker Hub). Evitar duplicar el mismo rol en los dos sitios.

#### 31.3 Proxy/cache de paquetes públicos (pip, npm, otros)

1. Repos tipo `proxy` en Nexus contra `pypi.org` y `registry.npmjs.org` (y opcionalmente Maven Central) — cachea lo ya descargado, mantiene disponibilidad si el upstream cae, y da un punto donde bloquear versiones concretas si se detecta un problema.
2. Cada proyecto consumidor apunta su `pip.conf`/`.npmrc` al proxy en vez de al índice público.
3. **Aviso realista sobre "controlar la seguridad"**: Nexus Repository **OSS** no incluye escaneo de vulnerabilidades — eso es Nexus IQ Server, de pago. El control real que da la edición gratuita es curaduría manual (qué se cachea, qué se bloquea a mano), no análisis automático de CVEs. Si el objetivo prioritario fuera específicamente el escaneo de vulnerabilidades, Harbor (ver alternativas) lo resuelve gratis y Nexus OSS no.

### Alternativas evaluadas (todas open source, sin producto comercial)

- **Nexus Repository OSS** — licencia EPL-2.0. Java/JVM: el heap recomendado empieza en 4 GiB incluso con poco uso real. Dato concreto de este mismo clúster (mejora 30, medido 2026-08-12): `retaco` tiene 8,3 GiB disponibles compartidos con `postgres-main`, `qdrant`, `n8n-main`, `registry`, Infisical, Authentik y `open-terminal` — Nexus ahí sería, con diferencia, el consumidor más pesado del nodo. A cambio, es la opción con más cobertura de formatos (Docker, npm, PyPI, Maven, generic, apt, yum...) y la única con repos `group` (agregar varios repos bajo una sola URL) — nada de lo de abajo lo replica.
- **Package Registry de Forgejo** (mejora 7) — llega "gratis" en cuanto se despliegue Forgejo, MIT, sin proceso nuevo que mantener. Cubre generic/npm/PyPI/Maven/container, pero sin proxy/cache maduro de upstreams públicos — no resuelve por sí solo el objetivo de control sobre paquetes de terceros que motiva esta mejora.
- **Combinación de proxies ligeros, uno por ecosistema**, en vez de un todo-en-uno:
  - [devpi](https://github.com/devpi/devpi) (Python) — proxy/cache de PyPI + índice privado.
  - [Verdaccio](https://github.com/verdaccio/verdaccio) (Node.js, MIT) — proxy/cache de npm + registry privado, muy ligero.
  - [Zot](https://github.com/project-zot/zot) (Go, Apache-2.0, sandbox de CNCF) — registry OCI/Docker moderno, binario único, huella mínima; candidato a sustituir `registry:2` (mejora 8) si se revisita esa pieza más adelante. Cada componente consume una fracción del heap mínimo de Nexus y se actualiza/reinicia de forma independiente — más "filosofía Unix", pero más piezas sueltas que mantener (el trade-off inverso a Nexus).
- **Harbor** — Apache-2.0, proyecto graduado de la CNCF. Solo OCI/Docker de forma nativa (no npm/pip). Trae de serie escaneo de vulnerabilidades con Trivy, RBAC granular y replicación entre registries — si el objetivo prioritario fuera específicamente "controlar la seguridad" vía escaneo automático, Harbor lo cubre gratis y Nexus OSS no. Más pesado que Zot (varios componentes: core, base de datos, Redis, Trivy) pero más moderno y ligero que Nexus.

Para el objetivo declarado — repositorio centralizado + proxy pip/npm + experimento fiel a cómo se haría en un proyecto real con presupuesto de infraestructura — **Nexus OSS sigue siendo razonablemente la opción más representativa**, pero conviene comprobar la memoria libre real de `retaco` en el momento de desplegarlo (mismo ejercicio que en la mejora 30) antes de comprometerse, y no descartar devpi+Verdaccio si el consumo de Nexus resulta problemático en la práctica.

### Esfuerzo estimado

Medio — la instalación en sí es un contenedor con almacenamiento NFS, y encaja en patrones ya resueltos (nginx + TLS interno, Infisical, Authentik). El trabajo real está en configurar los repos proxy de pip/npm y en decidir la relación con el Package Registry de Forgejo una vez este exista (mejora 7).

---

## 32. Dominio real con certificados Let's Encrypt, en vez de CA interna propia

**Prioridad: media**

### Qué hay hoy

Todo el TLS del clúster cuelga de una CA interna autofirmada (`pi-dns/config/nginx/generate-ca.sh`/`generate-cert.sh`, validez 10 años, `docs/15-ca-interna.md`) — cada hostname es `*.home.arpa`, resoluble solo dentro de la LAN (Pi-hole/Unbound) o vía el Split DNS de Tailscale (`docs/18-tailscale.md`). Cualquier dispositivo cliente (navegador, `dockerd`, el propio `buildx`) necesita instalar esa CA a mano antes de confiar en el clúster — ya ha causado fricción real y documentada más de una vez (el gotcha del builder de `buildx` sin las CAs del host, sección "Build/push" de este mismo `CLAUDE.md`; los nodos que no tenían la CA a nivel de sistema para `docker pull` contra `registry.home.arpa`).

### Qué haría falta

1. Registrar (o reutilizar, si ya existe) un dominio real bajo control propio — necesario para que Let's Encrypt pueda emitir, ya que solo firma para nombres de dominio público, nunca para `.home.arpa` ni para IPs privadas.
2. **Reto DNS-01, no HTTP-01** — el clúster no está expuesto a internet a propósito (solo accesible vía LAN o Tailscale, `docs/18`) y no tiene sentido abrir el puerto 80 al público solo para validar un certificado. DNS-01 exige que el proveedor DNS del dominio tenga API (Cloudflare, Route53, etc.) para que el cliente ACME pueda crear el registro TXT del reto de forma automática.
3. Cliente ACME: `certbot`/`acme.sh` con el plugin del proveedor DNS elegido — ver el punto siguiente, la decisión de arquitectura ya tomada es que corre **desacoplado de Traefik**, no integrado en él.
4. **Renovación automática obligatoria** — a diferencia de la CA interna (10 años, prácticamente "y olvídate"), los certificados de Let's Encrypt caducan a los 90 días. Sin cron/hook de renovación, el clúster completo quedaría con TLS caducado en menos de tres meses.
5. Decidir el alcance: ¿sustituye del todo a la CA interna, o conviven? Los hostnames `*.home.arpa` seguirían resolviendo a IPs internas vía Pi-hole igual que hoy — lo que cambia es el certificado servido, que pasaría a tener SAN del dominio real en vez de (o además de) `*.home.arpa`. Servicios pensados para quedarse siempre puramente internos podrían mantenerse en la CA propia si no compensa el cambio.
6. Revisar el impacto en todo lo que hoy confía en la CA interna a nivel de sistema (`docs/15-ca-interna.md`, sección Linux/Docker) — con Let's Encrypt, un certificado válido públicamente ya no necesita que cada nodo/dispositivo instale nada a mano, lo cual elimina de raíz la clase de problema que motivó varios de los gotchas ya documentados en este repo.
7. Confirmar que el Split DNS de Tailscale (`docs/18-tailscale.md`) sigue funcionando igual una vez el hostname resuelto por dentro del tailnet difiera del hostname real del certificado, si se elige no usar el dominio real también ahí.

### Piloto realizado y proveedor DNS: migrar la gestión de 404labo.net a Route53

Piloto ejecutado (2026-08-22) para un único hostname (`home.404labo.net`, mismo frontend que `index.home.arpa`) antes de decidir migrar el resto: dominio real `404labo.net`, certificado wildcard (`*.404labo.net` + apex `404labo.net` explícito — el wildcard solo no cubre el apex) emitido con `acme.sh` en modo DNS-01 manual (`--issue --dns ... --yes-i-know-dns-manual-mode-enough-go-ahead-please`, dos fases: `--issue` genera el reto TXT, `--renew` valida tras confirmar propagación), primero contra el servidor `staging` de Let's Encrypt y después contra `production`. Certificado desplegado en `pi-dns/config/nginx/nginx.conf` (bloques `home.404labo.net`/`capataz-api.404labo.net`, selección por SNI junto al certificado de la CA interna).

**Hallazgo real**: el proveedor DNS actual del dominio es Dinahosting, que **no tiene API pública** ni plugin `dnsapi` en `acme.sh` (solo un hilo de GitHub sin integrar, issue #6232) — el piloto se hizo a mano, creando el registro TXT del reto por la consola web de Dinahosting en cada fase. Válido para un piloto de un solo hostname, pero inviable para la **renovación automática obligatoria** exigida en el punto 4 de esta mejora (90 días de validez, sin intervención humana) una vez se generalice a todos los hostnames del clúster.

**Decisión tomada**: migrar la gestión DNS de `404labo.net` a una **hosted zone completa en AWS Route53** (no solo delegar el subdominio `_acme-challenge`, que habría bastado para el reto DNS-01 con menor radio de cambio — se descartó a favor de la zona completa por dar más control sobre el dominio en su conjunto). Provisionado con **Terraform** (infraestructura como código), no consola/CLI manual — coherente con el resto de este repo (todo declarativo, versionado). Con la zona en Route53, `acme.sh` puede usar su plugin `dns_aws` (soporte SigV4 completo, ya maduro) para crear/borrar el TXT del reto automáticamente en cada renovación, sin intervención humana — desbloquea también el cliente ACME desacoplado descrito en la siguiente sección.

**Ejecutado (2026-08-26)**:
1. ~~Terraform: hosted zone Route53...~~ Hosted zone y usuario IAM creados por el usuario directamente en AWS (consola/CLI, no Terraform) — desviación del plan original de "todo declarativo"; pendiente valorar si merece la pena importarlo a Terraform más adelante, sin bloquear el resto. Policy IAM confirmada de alcance mínimo (`route53:ChangeResourceRecordSets`/`GetChange`/`ListResourceRecordSets` sobre la hosted zone de `404labo.net`, nada más).
2. NS del dominio movidos a Route53 y propagados — confirmado en vivo (`dig NS 404labo.net` devuelve los 4 `awsdns-*` de la hosted zone, `home.404labo.net`/`capataz-api.404labo.net` resuelven igual que antes).
3. `acme.sh` (v3.1.4, instalado en `pi-dns` desde el tarball oficial — el script suelto no basta, faltan los plugins `dnsapi/`) reconfigurado con `dns_aws`. **Hallazgo real**: desde acme.sh v3.x el CA por defecto es ZeroSSL, no Let's Encrypt — hace falta `--server letsencrypt` explícito o se emite (y registra una cuenta) contra el CA equivocado sin avisar. Certificado real emitido en producción (`404labo.net` + `*.404labo.net`), instalado con `acme.sh --install-cert` para registrar de forma permanente el CA y el `--reloadcmd` de despliegue.
4. `shared/scripts/renew-letsencrypt.sh` construido y desplegado (cron diario `03:30` en `pi-dns`, mismo patrón que `check-image-updates.sh`). Credenciales AWS del usuario IAM leídas de **Infisical** (Machine Identity `acme-dns-renewer`, Universal Auth, carpeta `/acme-dns-renewer/` del proyecto "Homelab Cluster") en vez de un fichero plano propio — mismo wrapper de dos pasos que el resto de servicios migrados (`docs/26-infisical-secretos.md`); solo las credenciales bootstrap de esa Machine Identity viven en `pi-dns/.env` (real, gitignored). `--reloadcmd` copia el cert emitido al path real de nginx (`sudo cp` + `nginx -s reload`, permisos root en `/srv/homelab/pi-dns/nginx/certs/`) — verificado en vivo, nginx sirve el cert nuevo sin downtime. Se queda en `pi-dns` de forma permanente (no es una ubicación "inicial a mover" — coincide con ser también el nodo fuera del swarm de la mejora 39, ver más abajo).

### Decisión de arquitectura tomada: renovación desacoplada de Traefik, un único escritor

Con Traefik desplegado en modo `global` dentro del swarm (mejora 35/39), **ninguna réplica de Traefik gestiona su propio `certificatesResolver` ACME**. El motivo es concreto, no una preferencia de estilo:

1. Traefik v2/v3 (a diferencia de v1) no trae ya un backend de KV distribuido para el estado ACME — si cada réplica `global` intentara renovar por su cuenta, se generarían condiciones de carrera entre ellas.
2. **Solución real implementada (2026-08-26, distinta del NFS previsto originalmente aquí)**: un único proceso "renovador" (`acme.sh` con `dns_aws`, por cron) corre en `pi-dns` — fuera de Traefik y fuera del swarm por completo (coincide con que `pi-dns` ya está excluido del swarm por la mejora 37/39), no Swarm-aware, sin tráfico entrante, porque el reto es DNS-01. El certificado NO se comparte vía NFS del NAS — en vez de eso viaja a Traefik como **Docker secret nativo de Swarm** (`docker secret create`, mismo mecanismo ya usado para el certificado de `*.home.arpa`, `docs/31-docker-swarm.md` fase 3b), distribuido de forma nativa y cifrada a los 5 nodos sin depender del NAS/NFSv3 en absoluto.
3. Todas las réplicas `global` de Traefik solo **leen** ese secret vía su proveedor de fichero dinámico (`tls.certificates`) — nunca configuran un `certificatesResolver` propio.
4. ~~**Hueco pendiente de automatizar**~~ — **Cerrado** (2026-08-28, cierre mejora 41): `shared/scripts/deploy-traefik-cert.sh`, registrado como `--reloadcmd` de `acme.sh` (sustituye al `--reloadcmd` de `nginx`, decomisionado en el mismo cierre), sube de versión el secret (`docker secret create` + `docker service update` sobre `traefik_traefik` por SSH desde `pi-dns` a un nodo manager, con una clave dedicada de un solo propósito) y lo hace sin `docker stack deploy` completo. Probado en vivo rotando el secret dos veces seguidas (v1→v2→v3) sin downtime.
5. La CA interna, reducida ya a un único consumidor (Valkey, ver mejora 41), sigue el mismo patrón trivial: un certificado que casi nunca se reescribe, sin necesidad de esta automatización.

### Esfuerzo estimado
Medio-alto — depende sobre todo del proveedor DNS elegido (facilidad de su API para el reto DNS-01); combinarlo con Traefik (mejoras 35/39) no simplifica el mecanismo de renovación en sí (que queda deliberadamente fuera de Traefik), pero sí resuelve dónde y cómo se sirve el resultado.

### Cierre (2026-08-28)

Completada junto con el cierre de la mejora 41 (`docs/31-docker-swarm.md`, Fase 5) — todos los puntos de "Qué haría falta" resueltos: dominio real (`404labo.net`), DNS-01 vía Route53/`dns_aws` con renovación automática por cron, cliente ACME desacoplado de Traefik (un único escritor en `pi-dns`), rotación del secret de Traefik ya automatizada (ver arriba), y Split DNS de Tailscale confirmado funcionando con el dominio real. Única desviación respecto al plan original: la hosted zone de Route53 y el usuario IAM se crearon a mano (consola/CLI), no vía Terraform — se deja apuntado como posible limpieza futura, no bloqueante, no forma parte del backlog activo.

---

## 33. Migrar el clúster a Docker Swarm, progresivamente

**Prioridad: baja-media**

### Qué hay hoy

Este mismo `CLAUDE.md` fija como decisión de arquitectura explícita: *"Docker Engine + Docker Compose v2 only (explicitly no Kubernetes, no Docker Swarm)"*. Hoy son 6 stacks de Compose completamente independientes, cada uno con su propia red bridge (`<nodo>-net`), sin red Docker compartida entre nodos — el tráfico entre nodos va por la LAN real vía `*.home.arpa` (`docs/01-topologia.md`). Adoptar Swarm sería revertir esa decisión de forma consciente, no una continuación natural de lo que hay — conviene evaluarlo con calma antes de tocar nada, empezando por un piloto de bajo riesgo, no un cambio de golpe en los 6 nodos.

### Qué haría falta

1. **Decidir el alcance real primero**: como máximo, un swarm con los 4 nodos que sí entran (`retaco`, `pi-obs`, `pi-sonar`, `pi-utils` — `ryzen` y `pi-dns` quedan fuera por diseño, mejoras 37 y 39), o empezar con un subconjunto menor todavía como piloto. Swarm no exige arquitectura homogénea entre nodos (arm64 y amd64 conviven en el mismo clúster sin problema), pero cada *servicio* concreto sigue necesitando su propia imagen multi-arch si va a poder programarse en cualquier nodo — ya resuelto para `apikey-service`/`markitdown-service` (`docker buildx build --platform linux/amd64,linux/arm64`), no para `whisper-service` (amd64-only a propósito, necesita CUDA, y de todos modos vive en `ryzen`, fuera del swarm).
2. **Quórum de managers, y dos nodos fuera del propio Swarm**: Raft necesita mayoría de managers vivos para aceptar escrituras. Dos nodos quedan **decididos fuera del clúster Swarm por completo, ni siquiera como worker**: `ryzen`/`mole` (se apaga habitualmente, `docs/19-wake-on-lan.md`, y aloja servicios con alternancia manual de GPU que no encajan con que el scheduler decida dónde correr algo — detalle en la mejora 37) y `pi-dns` (el nodo más crítico del clúster, DNS de toda la LAN — se mantiene con la superficie mínima posible en vez de sumarle el rol de manager/worker; además Tailscale, que sigue viviendo ahí, ni siquiera podría desplegarse dentro de un stack Swarm — `network_mode: host` y `devices:` están en la lista de claves que `docker stack deploy` ignora, sin equivalente a `--device` en `docker service create` — detalle completo en la mejora 39). Los candidatos a manager quedan acotados a los 4 nodos restantes: `retaco`, `pi-obs`, `pi-sonar`, `pi-utils` — un esquema típico serían 3 de esos 4 como managers (impar, tolera 1 caída) y el cuarto como worker.
3. **Red overlay**: Swarm sustituye las redes bridge por nodo por una red overlay cifrada entre nodos vía VXLAN — revisar qué puertos hace falta abrir en el firewall gestionado hoy por `shared/scripts/setup-firewall.sh`/`toggle-direct-access.sh` (`docs/17-firewall-acceso-directo.md`), y si el tráfico VXLAN puede ir sin fricción por la LAN interna ya existente.
4. **Migración incremental sugerida**: empezar por un servicio sin estado y de bajo riesgo (un microservicio propio, p. ej.) desplegado como `docker stack deploy` en paralelo al `docker-compose.yml` actual, verificar equivalencia funcional, y solo entonces plantear servicios con estado. Éstos son el caso realmente delicado: Swarm no resuelve por sí solo la persistencia multi-nodo — sigue haciendo falta bind-mount local, y el scheduler podría reprogramar el contenedor en otro nodo perdiendo acceso a sus propios datos si no se fija explícitamente con `constraints` (`node.hostname==retaco`, por ejemplo, para `postgres-main`).
5. **`docker-compose.yml` no se traduce 1:1 a `docker stack deploy`** — Swarm ignora `build:` (haría falta ya tener las imágenes publicadas en `registry.home.arpa`, lo cual este repo ya cumple para los servicios propios) y trata algunas claves de forma distinta. Revisar cada `docker-compose.yml` del repo antes de asumir que basta con `docker stack deploy -c docker-compose.yml <nombre>`.
6. **Relación con las mejoras 35 y 39 (Traefik)**: Traefik es el proxy natural de un clúster Swarm (descubre servicios vía labels, igual que ya hace hoy sobre Docker standalone) — decisión ya tomada: Traefik se despliega dentro del propio swarm (en uno de los 4 nodos candidatos de este punto, nunca en `pi-dns`), en modo `global`, dejando `pi-dns` únicamente con DNS y Tailscale. Detalle completo en la mejora 39.
7. **Qué pasa con los 5 servicios comunes (`node-exporter`, `cadvisor`, `portainer-agent`, `watchtower`, `promtail`) en los 4 nodos que sí entran al swarm** — hoy están copiados a mano en cada `docker-compose.yml` (`docs/04-servicios-comunes.md`), sin `network_mode: host` en ninguno de los dos primeros (confirmado en el compose real: bind mounts de `/proc`/`/sys`/`/` + puerto publicado, no chocan con las claves que Swarm ignora):
   - **`node-exporter`, `cadvisor`, `promtail`**: mapean limpio a `deploy: mode: global` — el propio Swarm ofrece de serie el patrón "una réplica por nodo" que hoy se mantiene a mano en 4-6 ficheros distintos, resolviendo de raíz para estos tres la duplicación de inventario que ya señala la mejora 6 (Ansible), sin depender de que esa migración llegue a implementarse.
   - **`portainer-agent`**: cambia de patrón, no solo de sintaxis — el `agent-stack.yml` oficial de Portainer para Swarm despliega el agente en modo `global` sobre una red overlay dedicada (`agent_network`); los agentes se comunican entre sí y **Portainer pasa a gestionar todo el swarm como un único entorno**, no como 4 entornos separados (uno por nodo) como hoy.
   - **`watchtower`**: no tiene sentido dejarlo tal cual dentro de Swarm — recrea contenedores sueltos, y si actúa sobre uno gestionado por Swarm pelea contra el propio reconciliador del orquestador (Swarm nota la tarea "desaparecida" y la reprograma, con resultado poco predecible). El reemplazo real es `docker service update --image ...` (rolling update nativo) o una herramienta pensada específicamente para Swarm (p. ej. Shepherd), no Watchtower — mismo punto ya apuntado en la mejora 36 (punto 5), que es donde vive el detalle completo del mecanismo de vigilancia/actualización de imagen en Swarm; aquí solo se deja constancia de que aplica también a este bloque de servicios comunes, no solo a los servicios de aplicación.
   - **Detalle transversal**: los cinco fijan `container_name:` hoy — esa clave también la ignora `docker stack deploy` (Swarm nombra sus propias tareas, `<stack>_<servicio>.<slot>.<id>`), así que cualquier comando/script que referencia el nombre fijo (`docker logs watchtower`, `docs/16-mantenimiento-actualizaciones.md`) pasaría a `docker service logs <stack>_<servicio>`.
   - `ryzen` y `pi-dns`, al quedar fuera del swarm (mejoras 37/39), siguen ejecutando los cinco exactamente como hoy — sin ningún cambio.
8. **`shared/scripts/update-stack.sh` actual asume Compose standalone** — revisar el equivalente nativo de Swarm (`docker service update --image ...`, con rolling update incorporado), que sería una mejora real sobre el `--force-recreate` que se usa hoy. Mantener actualizados los contenedores ya desplegados en Swarm (vigilancia + aplicación del rolling update) es justo la continuación natural del mecanismo ya existente hoy para Compose (`watchtower` + `check-image-updates.sh`, `docs/16-mantenimiento-actualizaciones.md`) — no es un problema nuevo que diseñar desde cero, ver mejora 36.
9. **Justificar el cambio con honestidad, no solo "porque se puede"**: en un clúster de un solo operador, el argumento fuerte de Swarm no es alta disponibilidad real (nadie necesita failover automático 24/7 en un homelab) — es rolling updates nativos, red overlay gestionada y `docker secret`/`docker config` propios. Documentar explícitamente qué se gana frente al coste de complejidad añadida antes de comprometerse, mismo criterio que se aplicó a la comparativa Vault-vs-Infisical (mejora 16).

### Esfuerzo estimado
Alto — no por dificultad técnica puntual, sino por ser un cambio de paradigma que toca los 4 nodos candidatos (`ryzen`/`pi-dns` quedan fuera, mejoras 37/39) y su `docker-compose.yml`; abordar por fases, nunca de golpe, empezando por un piloto sin estado.

---

## 34. GitOps para las aplicaciones del clúster (se buscan propuestas)

**Prioridad: media**

### Qué hay hoy

El despliegue es enteramente manual: editar el `docker-compose.yml` en este repo, `rsync` a `/srv/homelab/<nodo>/`, `ssh` y `docker compose up -d` (ver "Connecting to cluster nodes" en este mismo `CLAUDE.md`). No hay reconciliación automática entre lo que dice el repo y lo que corre de verdad en cada nodo — de hecho este `CLAUDE.md` avisa explícitamente de que ambos pueden divergir en silencio (el gotcha de `pi-dns`, donde la ruta real de despliegue de `nginx` no coincide con la carpeta versionada en el repo, y ha causado 404 confusos más de una vez). Ese mismo hueco es justo el tipo de problema que GitOps resuelve por diseño: el estado deseado vive en git, y algo lo aplica y lo mantiene sincronizado sin depender de que nadie se acuerde de desplegar a mano.

Este clúster **no usa Kubernetes** (decisión de arquitectura explícita de este repo) — las herramientas de GitOps más conocidas (ArgoCD, Flux) son nativas de Kubernetes y no aplican tal cual aquí. Cualquier propuesta tiene que partir de eso.

### Propuestas a evaluar (sin decisión tomada todavía)

1. **[Komodo](https://komo.do)** — proyecto open source pensado específicamente para gestionar múltiples nodos con Docker Compose (no Kubernetes): concepto de "stacks" enlazados a un repo git, sync automático al hacer push, UI propia de gestión multi-nodo. Encaja directamente con la forma real de este clúster (varios nodos, cada uno con su propio stack) sin forzar una migración a Kubernetes. Candidato más "producto ya hecho" de la lista.
2. **Dockge** — UI de gestión de stacks Compose con stacks respaldados por git, más ligero que Komodo pero con menos automatización real de "sync en push" — más cercano a un Portainer con git integrado que a GitOps real con reconciliación continua.
3. **Cron + `git pull` + `update-stack.sh`** — la opción más simple, sin producto nuevo que mantener: cada nodo, por cron, hace `git pull` sobre una copia del repo en el propio nodo y aplica los ficheros relevantes a sus rutas reales de despliegue. El coste está en el scripting propio, no en una pieza nueva — pero exige resolver primero la discrepancia de rutas ya conocida (el mismo gotcha de `pi-dns`: el repo no siempre mapea 1:1 con la ruta real desplegada), o el sync fallaría en silencio exactamente igual que hoy.
4. **Si se combina con la mejora 33 (Swarm)**: `docker stack deploy` es idempotente y declarativo por diseño — GitOps encaja de forma más natural ahí (el propio Swarm ya reconcilia el estado declarado contra el real). Komodo también soporta Swarm nativamente, no solo Compose standalone.
5. **`watchtower` ya cubre una parte, pero no todo**: hoy actualiza la imagen (`:latest` nuevo) automáticamente, pero no reacciona a cambios del propio `docker-compose.yml` (nuevas variables de entorno, nuevos bind mounts, nuevos servicios) — cualquier propuesta de GitOps real tiene que cubrir también eso, no solo la imagen.
6. **Secretos**: los `.env` reales nunca están en git, a propósito (este `CLAUDE.md`, sección "Secrets are always `CHANGE_ME`..."). Cualquier propuesta tiene que seguir resolviendo secretos vía Infisical/Vaultwarden directamente en el nodo — nunca meterlos en el repo para que el sync los aplique, ni siquiera cifrados dentro del propio git.
7. **Alcance del piloto**: decidir si se prueba primero sobre un único nodo de bajo riesgo (`pi-utils`, por ejemplo) antes de generalizar a los otros 5, mismo criterio de migración incremental ya seguido en el resto de mejoras grandes de este documento (Infisical, Authentik).

### Esfuerzo estimado
Medio-alto, muy dependiente de la propuesta elegida — desde "cron + `git pull`" (bajo, pero manual de verdad) hasta desplegar un producto nuevo como Komodo (medio) o acoplarlo a una migración completa a Swarm (alto, ver mejora 33).

---

## 35. Sustituir `nginx` por Traefik, integrado con Docker Swarm

**Prioridad: media**

### Qué hay hoy

`nginx` en `pi-dns` es la puerta de entrada de todo el clúster (`pi-dns/config/nginx/`, desplegado en `/srv/homelab/pi-dns/nginx/conf/` — ver el gotcha de rutas ya documentado en este `CLAUDE.md`): un bloque `server` por hostname, escrito y desplegado a mano, TLS con la CA interna (`docs/15-ca-interna.md`), `apikey-auth.conf` como snippet de `auth_request` para proteger servicios sin auth propia. Ningún descubrimiento automático de servicios — cada hostname nuevo exige tocar `nginx.conf`, desplegarlo (con el cuidado ya conocido del bind-mount de fichero único) y recargar.

### Qué haría falta

1. Traefik en modo *Docker Swarm provider* (no standalone) — descubre servicios automáticamente vía labels declaradas en el propio stack (`traefik.http.routers.<servicio>.rule=Host(...)`), sin tocar un fichero de configuración central por cada hostname nuevo. Resuelve directamente la fricción operativa que hoy tiene `nginx`.
2. **Punto crítico de esta mejora, ya resuelto en el diseño**: Traefik solo aporta descubrimiento automático real si corre sobre el mismo Docker que orquesta los servicios a exponer — con Docker standalone en un nodo aparte (como `nginx` hoy en `pi-dns`) solo vería los contenedores de ese nodo. **Esta mejora depende en la práctica de la 33** (Swarm) para aportar valor real sobre `nginx`, y la decisión concreta de dónde vive Traefik dentro del swarm (nunca en `pi-dns`, modo `global`, routing mesh) queda detallada en la mejora 39 — no se repite aquí.
3. Certificados: **Traefik no gestiona su propio ACME** en este diseño — decisión explicada en la mejora 32 (renovación desacoplada, un único proceso escritor fuera de Traefik) y en la mejora 39 (almacén NFS compartido, solo lectura desde las réplicas `global`).
4. `auth_request` (`apikey-auth.conf`, protección de `ollama`/`epub2pdf`/etc.) tiene equivalente directo en Traefik vía el middleware `ForwardAuth` — mismo concepto (llamada a `apikey-service` antes de dejar pasar la petición), sintaxis distinta, hay que migrarlo servicio a servicio. La llamada a `apikey-service` funciona igual esté donde esté el servicio (HTTP normal sobre la LAN, sin depender de red Docker compartida) — pero su ubicación final (si se queda en `pi-dns` o se traslada) queda como decisión abierta en la mejora 39, no resuelta todavía.
5. Migración incremental: Traefik y `nginx` pueden convivir temporalmente en puertos distintos mientras se migra servicio a servicio — mismo criterio de evaluar en paralelo ya usado con Bifrost/LiteLLM (mejoras 20/21).
6. Dashboard propio de Traefik: decidir si se expone (protegido con Authentik forward-auth, mejoras 25/29) o se deja solo accesible en local, mismo criterio ya aplicado a otros paneles de administración del clúster.
7. Revisar los snippets especiales que `nginx` ya resuelve hoy (`proxy-common.conf`, `proxy_buffering off` + timeouts largos para el streaming SSE de `open-terminal-mcp`, mejora 17) — cada uno necesita su middleware equivalente en Traefik antes de dar por sustituible la configuración actual.

### Esfuerzo estimado
Alto — depende directamente de la migración a Swarm (mejora 33) y del resto de decisiones ya tomadas en la mejora 39 (dónde vive Traefik, cómo llegan los certificados); sin Swarm no compensa reescribir toda la configuración de `nginx` ya probada en producción.

---

## 36. ~~Vigilancia y alertas del estado de parcheo de los nodos (SO) — y su continuación en Swarm~~ — hecho

**Prioridad: media** — **completado**

### Qué se implementó

`shared/scripts/check-os-updates.sh` (nuevo, punto 1) — a diferencia de `check-image-updates.sh` (centralizado en `pi-obs` vía SSH), corre **localmente por cron en cada uno de los 7 nodos** (los 6 de siempre más `pinchi`), escribiendo `node_apt_security_updates_pending` y `node_reboot_required` en el *textfile collector* de su propio `node-exporter`. **Prerrequisito verificado en vivo, no asumido** (tal como pedía el propio punto 1): el *textfile collector* ya estaba provisionado de fábrica en los 5 nodos del stack Swarm `common` (dejado preparado a propósito para esta mejora), pero faltaba en `ryzen` y `pi-dns` (Compose clásico) — añadido a ambos. Panel nuevo en el dashboard `homelab-actualizaciones-pendientes` (punto 2) y alertas conectadas a ntfy (punto 3) en `pi-obs/config/grafana/alerting/os-patching.yml` — reinicio pendiente sostenido 3 días, y más de 20 actualizaciones de seguridad acumuladas sostenidas 3 días. `pi-dns` (punto 4) tiene su propia regla separada, severidad `critical` en vez de `warning` y ventana de 1 día en vez de 3 — ninguna de las dos reglas reinicia nada. Detalle completo de las tres, verificado con datos reales del clúster (no solo desplegado, comprobado que las cifras y los estados de las reglas eran coherentes con lo que reportaba cada nodo): `docs/16-mantenimiento-actualizaciones.md` sección 1.3.

**Punto 5 (continuación en Swarm) — decisión tomada, no la que proponía la redacción original**: NO se adopta Watchtower en modo Swarm. Habría contradicho la política ya establecida del clúster de auto-actualización solo para imágenes de terceros genuinamente sin estado (`CLAUDE.md`, sección watchtower) — Watchtower-Swarm actualizaría servicios (incluidos los que se auto-actualizan deliberadamente NUNCA, como `postgres-main`/Vaultwarden) sin ese control fino. En su lugar, `check-image-updates.sh` ya vigilaba de facto los contenedores de tareas Swarm (hace `docker ps` por nodo, que ve cualquier contenedor sin importar si lo gestiona Compose o Swarm) — el hueco real era que **`pinchi` no estaba en su mapa de nodos** (se incorporó al clúster después de escribirse el script, mejora 30) y, al no tener `constraints` de nodo fijo, cualquier tarea Swarm que aterrizara ahí (`registry`, `ntfy`...) quedaba invisible. Añadido `pinchi` al script — **pendiente de un paso más**: autorizar la clave SSH de `pi-obs` en `pinchi`, una acción de seguridad dejada fuera a propósito de este cambio, pendiente de confirmación explícita del usuario (mientras tanto el script trata `pinchi` como nodo inalcanzable, `WARN`, sin romper el resto).

**Hallazgo real no buscado, con blast radius mayor que esta mejora**: implementando el punto 1, la nueva métrica (con valores genuinamente distintos por nodo) expuso que `node-exporter`/`cadvisor` en el stack `common` publicaban su puerto en `mode: ingress` (por defecto de Swarm con la sintaxis corta) — la malla de rutado podía reenviar una petición a la IP de un nodo hacia el node-exporter de OTRO nodo cualquiera de los 5, mezclando la atribución de nodo de cualquier métrica de esos dos exporters desde la migración a Swarm, no solo la de esta mejora. Confirmado de forma inequívoca (`docker exec` directo vs. lo que veía Prometheus) y corregido a `mode: host` — detalle completo, incluido un segundo incidente real al aplicar el fix (colisión de puerto por la reserva `ingress` global al swarm, mismo patrón que el incidente de Traefik ya documentado) y una falsa alarma benigna de undervoltage causada por el propio cutover, en `docs/31-docker-swarm.md`.

### Qué hay hoy (histórico, previo a la implementación)

**No era un hueco nuevo — era un punto ciego dentro de algo que ya funcionaba.** `docs/16-mantenimiento-actualizaciones.md` ya resolvía tanto la actualización del sistema operativo (`unattended-upgrades` para parches de seguridad automáticos en los seis nodos, `update-os.sh` para actualización completa bajo demanda) como la de las imágenes Docker (Watchtower para lo sin estado, `check-image-updates.sh` con panel en Grafana para el resto) — ver también la mejora 6, que **no es lo mismo**: esa mejora migra el *tooling* de mantenimiento a Ansible por idempotencia, no añade vigilancia ni alertas nuevas.

El punto ciego real: las actualizaciones de **imagen Docker** sí tenían visibilidad centralizada — pero las de **sistema operativo** no tenían ningún equivalente. Saber si un nodo tenía parches de seguridad pendientes o si necesitaba reinicio tras uno exigía entrar por SSH a cada nodo a mano.

### Esfuerzo estimado
Bajo — reutiliza infraestructura ya montada (*textfile collector*, Grafana, el propio patrón de `check-image-updates.sh`); el trabajo real fue escribir el script y decidir umbrales de alerta razonables. El punto 5 (continuación en Swarm) resultó en una decisión de no adoptar Watchtower-Swarm más que en trabajo de implementación.

---

## 37. `ryzen` (mole) fuera del clúster Swarm — operativa como nodo Compose independiente

**Prioridad: baja-media**

### Qué hay hoy

Decidido explícitamente (ver mejora 33, punto 2): si el resto del clúster migra a Docker Swarm, **`ryzen`/`mole` se queda fuera por completo**, ni siquiera como worker — sigue gestionado con Docker Compose puro, tal cual hoy. Motivo doble: es el único nodo que se apaga habitualmente cuando no se usa (`docs/19-wake-on-lan.md`, GPU de escritorio, no infraestructura siempre encendida) y aloja servicios especializados con alternancia manual de GPU (`ryzen/switch-llm-backend.sh` para GPU 0 ollama/vllm, `ryzen/switch-gpu1-backend.sh` para GPU 1 whisper-service/comfyui, `docs/07-instalacion-ryzen.md`) que dependen de que el operador controle explícitamente qué corre y cuándo — justo lo contrario de dejar que un scheduler decida.

`ryzen` ya tiene hoy dos stacks de Compose completamente independientes (`docker-compose.yml` para GPU/AI, `docker-compose.observability.yml` para node-exporter/cadvisor sin `.env`) — esta pieza **ya existe y no necesita rehacerse** por la migración a Swarm de los demás nodos. Lo que sí falta es dejar explícita la operativa de un clúster mixto Swarm+Compose, para no dar por hecho luego que "todo el clúster" se comporta igual.

### Qué haría falta

1. **Networking**: si los 4 nodos que sí entran al swarm (`retaco`, `pi-obs`, `pi-sonar`, `pi-utils` — `pi-dns` también queda fuera, ver mejora 39) pasan a una red overlay VXLAN (mejora 33, punto 3), `ryzen` se queda fuera de esa red — sigue expuesto solo por la LAN real vía `*.home.arpa`, exactamente como hoy (`docs/01-topologia.md`). No requiere ningún cambio en `ryzen/docker-compose.yml` ni en `docker-compose.observability.yml` por este motivo.
2. **Traefik/nginx (mejora 35) no puede autodescubrir `ryzen`**: si `pi-dns` pasa a Traefik con *provider* de Docker Swarm, ese autodescubrimiento por labels solo ve contenedores dentro del propio Swarm — los servicios de `ryzen` (`ollama`, `vllm`, `open-webui`, `whisper-service`, `comfyui`) seguirán necesitando declararse a mano (vía IP/hostname fijo, como hoy con nginx) en vez de vía labels. Documentar esto como excepción permanente cuando se aborde la mejora 35, no como un pendiente de migrar más adelante.
3. **`apikey-service` sigue protegiendo `ryzen` igual que hoy**: al no depender de redes Docker compartidas entre nodos (el `auth_request` de nginx/Traefik llama por HTTP sobre la LAN), la protección de `ollama` y demás servicios de `ryzen` no cambia con la migración del resto a Swarm.
4. **Mantenimiento del nodo se queda en el mecanismo Compose actual, sin excepción**: `watchtower`, `check-image-updates.sh`, `update-stack.sh`, y los propios `switch-llm-backend.sh`/`switch-gpu1-backend.sh` (`docs/16-mantenimiento-actualizaciones.md`) — `ryzen` **nunca** pasa a los equivalentes nativos de Swarm (`docker service update --image`, mejora 33 punto 8, ni la vigilancia de imagen en modo Swarm de la mejora 36 punto 5), porque nunca entra en el Swarm. Dejarlo dicho explícitamente para que nadie intente aplicarle tooling de Swarm por costumbre una vez el resto del clúster lo use.
5. **Wake-on-LAN no debe convertirse en una dependencia implícita del resto del clúster**: hoy `ryzen` es estrictamente *opt-in* — se despierta a propósito con `shared/scripts/wake-mole.sh` cuando hace falta. Al introducir Swarm/Traefik en el resto, revisar que ningún healthcheck, *service discovery* o regla de proxy asuma que `ryzen` está siempre disponible (p. ej. un `ForwardAuth`/*health check* con timeout corto contra un nodo apagado no debería degradar nada del resto del clúster, que sigue siendo independiente por diseño desde el principio, `docs/01-topologia.md`).
6. **Documentación**: cuando la migración a Swarm de los otros nodos sea real (no solo backlog), actualizar `docs/01-topologia.md` y el propio `CLAUDE.md` para dejar constancia explícita de que `ryzen` es una excepción permanente gestionada con Compose — no un nodo pendiente de migrar en una fase futura.

### Esfuerzo estimado
Bajo — es principalmente una decisión de alcance ya tomada más su documentación; ningún trabajo de infraestructura nuevo, el `docker-compose.yml`/`docker-compose.observability.yml` de `ryzen` ya existen y no cambian por esto. El esfuerzo real está condicionado a que la mejora 33 llegue a implementarse.

---

## 38. Capacity planning basado en datos reales — fijar `mem_limit`/`cpus` por servicio a partir de picos observados en Prometheus

**Prioridad: media**

### Qué hay hoy

El inventario completo de servicios (`docs/01-topologia.md`, sección "Inventario de servicios por nodo") confirma que, de los ~61 contenedores del clúster, solo tres tienen restricción de memoria/CPU fijada: `crawl4ai-scraper-service` (`mem_limit: 2g`), `capataz-api` (`768m`) y `capataz-runner` (`1024m`). El resto corre **sin ningún límite Compose** — cualquier contenedor puede, en teoría, consumir toda la memoria del nodo y provocar que el OOM killer del kernel elija una víctima cualquiera, no necesariamente el propio contenedor problemático. El riesgo no es teórico: la mejora 30 ya midió `retaco` con solo 8,3 GiB disponibles compartidos entre `postgres-main`, `qdrant`, `n8n-main`, `registry`, Infisical, Authentik, `open-terminal-mcp` y ahora `valkey`/`epub2pdf`/`pdf2chunks` — y las Raspberry Pi (`pi-utils`, `pi-obs`, `pi-sonar`, `pi-dns`) tienen 7,7 GiB o menos.

El clúster ya recoge, sin usarlo para esto, exactamente el dato que hace falta: cAdvisor (`docs/04-servicios-comunes.md`, desplegado en los 6 nodos) expone `container_memory_usage_bytes` y `container_cpu_usage_seconds_total` por contenedor a Prometheus (`pi-obs`), con la retención actual de 14 días — suficiente para un primer corte, aunque no para capturar picos estacionales raros.

### Qué haría falta

1. **Consulta PromQL por servicio**, no una estimación teórica por tipo de carga: `max_over_time(container_memory_usage_bytes{name="<servicio>"}[30d])` para memoria, y percentil alto (`quantile_over_time(0.99, rate(container_cpu_usage_seconds_total{name="<servicio>"}[5m])[30d:])`) para CPU, evitando fijar el límite sobre el pico absoluto de CPU (más ruidoso, con picos cortos normales) igual que sobre el máximo bruto de memoria (más estable, sí tiene sentido usar el máximo ahí).
2. **Ventana representativa antes de fijar nada**: la retención actual de Loki/Prometheus en `pi-obs` es de 14 días (`docs/08-instalacion-pi2-observabilidad.md`) — puede no cubrir picos reales poco frecuentes (una ingesta masiva en n8n, un despliegue de SonarQube analizando un repo grande). Documentar explícitamente qué servicios tienen histórico fiable y cuáles no todavía; para estos últimos, cota provisional generosa + revisar pasado un tiempo, no un número inventado sin más.
3. **Margen de seguridad sobre el pico observado** — no fijar el límite exactamente en el máximo histórico (un pico ligeramente mayor mañana mataría el contenedor sin aviso); 1,3–1,5× como punto de partida razonable, a ajustar por servicio según cuán predecible sea su carga.
4. **Aplicar `mem_limit`/`cpus`** (sintaxis Compose v2 — no `deploy.resources.limits`, que es de Swarm y `docker compose up` la ignora en silencio, ver el propio inventario en `docs/01`) al `docker-compose.yml` de cada nodo, sirviéndose del patrón que ya usan `crawl4ai-scraper-service`/`capataz-api`/`capataz-runner` como referencia de estilo (comentario inline explicando de dónde sale el número, mismo criterio de "decisión no obvia documentada junto al código" que ya sigue el resto del repo).
5. **Priorizar por nodo, no por servicio suelto**: empezar por `retaco` (más servicios con estado compartiendo memoria ajustada) y las Raspberry Pi antes que por `ryzen` (RAM de sobra en comparación) — mismo criterio de riesgo real ya aplicado en la mejora 30.
6. **GPU en `ryzen` queda fuera de esta mejora**: `mem_limit`/`cpus` de Compose no acotan VRAM — la contención de GPU ya tiene su propio mecanismo (alternancia manual con `switch-llm-backend.sh`/`switch-gpu1-backend.sh`, `docs/07-instalacion-ryzen.md`), no hace falta ni tiene sentido duplicarlo aquí.
7. **No es un ejercicio de una sola vez**: en cuanto un servicio cambie de patrón de uso real (más tráfico, un flujo de n8n nuevo activado, etc.), el límite fijado puede quedarse corto — revisar periódicamente contra el histórico real, no fijar y olvidar. Candidato a automatizarse más adelante con un script/playbook que recalcule sugerencias (encajaría con la mejora 6, Ansible, si esa migración llega a cubrir esta parte del tooling), pero el primer corte puede y debe hacerse a mano.
8. **Panel en Grafana** con los servicios que siguen "sin límite" frente a los que ya lo tienen, mismo criterio de visibilidad centralizada que el resto de paneles de mantenimiento (mejora 3, mejora 36) — ayuda a no perder de vista cuántos quedan por revisar según se vaya avanzando.

### Esfuerzo estimado
Bajo-medio — las consultas PromQL y aplicar los límites son mecánicos; el trabajo real es decidir el margen de seguridad razonable por servicio y no romper nada en producción al aplicar el primer límite a un contenedor que hoy corre sin ninguno (aplicar de uno en uno, verificando después, no todos de golpe).

---

## 39. `pi-dns` fuera del clúster Swarm — solo DNS y Tailscale; Traefik dentro del swarm, en modo `global`

**Prioridad: media**

### Qué hay hoy

`pi-dns` hoy mezcla dos roles bien distintos en el mismo nodo: **servicios de red** (Unbound, Pi-hole, Tailscale como subnet router) y **puerta de entrada de aplicación** (`nginx` como proxy inverso de todo el clúster, sirviendo además el frontend estático de Capataz en `index.home.arpa`, `docs/28-capataz-consola-automatizacion.md`). Es, a la vez, el nodo más crítico del clúster (único punto de fallo del DNS de toda la LAN, `docs/16-mantenimiento-actualizaciones.md`) y el que más superficie de aplicación carga encima — justo la combinación que conviene evitar en el nodo que menos margen de fallo tiene.

### Decisión de arquitectura tomada

1. **`pi-dns` se queda fuera del clúster Swarm por completo**, igual que `ryzen` (mejora 37) pero por un motivo distinto: no es que se apague, es que es el nodo más crítico y conviene mantenerlo con la superficie mínima posible — sin la complejidad añadida de ser manager/worker de Swarm. Sigue con Docker Compose puro, ejecutando únicamente **Unbound + Pi-hole + Tailscale**. Motivo adicional, no solo de criterio: Tailscale tal y como está montado hoy (`network_mode: host` + `/dev/net/tun` bajo `devices:`, `TS_USERSPACE=false`, `docs/18-tailscale.md`) **no podría desplegarse dentro de un stack Swarm de todos modos** — `network_mode` y `devices` están explícitamente en la lista de claves que `docker stack deploy` ignora, sin equivalente a `--device` en `docker service create`.
2. **Traefik se despliega dentro del propio swarm**, en uno de los 4 nodos candidatos de la mejora 33 (`retaco`, `pi-obs`, `pi-sonar`, `pi-utils` — nunca `pi-dns` ni `ryzen`), en modo `deploy: mode: global` (una réplica por nodo del swarm) publicando el puerto en modo `ingress` (el modo por defecto de Swarm), **no** en modo `host`.
3. **Por qué `ingress` y no `host`**: con publicación en modo `ingress`, Swarm expone el puerto en *todos* los nodos del swarm y enruta internamente (IPVS sobre la red overlay) hasta una réplica sana de Traefik, esté donde esté. Esto da dos cosas a la vez: alta disponibilidad real del front-end (si un nodo cae, la malla sigue enrutando a las réplicas sanas de los demás) y **ningún `constraints`/label de ubicación fija necesario** — con modo `host` sí haría falta fijar Traefik a un nodo concreto (`node.hostname==<nodo>`) para que el DNS supiera a qué IP apuntar, perdiendo esa redundancia.
4. **Registros DNS** (`*.home.arpa`, Pi-hole en `pi-dns`) apuntan a la IP de cualquier nodo miembro del swarm en vez de a la IP de `pi-dns` — `pi-dns` sigue resolviendo los nombres, simplemente deja de ser el destino del tráfico HTTP. El Split DNS de Tailscale (`docs/18-tailscale.md`) no se ve afectado: ya depende solo de que `pi-dns` resuelva nombres y anuncie la ruta a toda la subred `192.168.1.0/24`, nunca de que el tráfico pase físicamente por él.
5. **Certificados en almacén NFS compartido** (NAS ya disponible, NFSv3, `docs/21-configuracion-nas-ugreen.md`), montado de **solo lectura** en todas las réplicas `global` de Traefik. Ninguna réplica gestiona su propio ciclo ACME — un único proceso renovador, desacoplado de Traefik, escribe ahí (decisión completa y su razonamiento en la mejora 32). Este mismo almacén sirve también para la CA interna si se mantiene en paralelo, sin conflicto entre ambas.
6. **Capataz se reubica**: el frontend estático que hoy sirve `nginx` en `index.home.arpa` debe salir de `pi-dns`. Candidato natural: `pi-utils`, donde ya viven `capataz-api` y `capataz-runner` (mejora 15) — servido por un contenedor propio (nginx/Caddy estático ligero) en vez de ficheros sueltos dentro de la configuración de un proxy que ya no vive ahí, y descubierto/enrutado por Traefik como cualquier otro servicio en vez de necesitar un caso especial.
7. **Abierto, no decidido todavía**: el destino de `apikey-service`. Funciona igual esté donde esté (llamada `ForwardAuth`/`auth_request` por HTTP normal sobre la LAN, sin depender de red Docker compartida entre nodos) — cabe tanto dejarlo en `pi-dns` junto al DNS como moverlo al nodo donde viva Traefik. Si el criterio es "`pi-dns` solo servicios de red", debería moverse también; decidirlo al abordar esta mejora, no antes.

### Qué haría falta

1. ~~Aplicar el punto 2 de la mejora 33 (quórum)...~~ **Hecho** — los 5 managers, `pi-dns`/`ryzen` excluidos desde el inicio.
2. ~~Desplegar Traefik como stack Swarm en modo `global`...~~ **Hecho y verificado (2026-08-26)** — publicación `ingress` real en 80/443 en los 5 nodos, confirmado libres antes de aplicar.
3. ~~Migrar los registros DNS...~~ **Hecho y verificado (2026-08-26)** — 28 hostnames movidos de `pi-dns` a `pinchi` (192.168.1.175, elegido con el usuario por menor carga que `retaco` y no ser `pi-utils`), `nginx` en `pi-dns` se deja vivo como rollback. Detalle completo del cutover: `docs/31-docker-swarm.md`, sub-fase 3b cierre.
4. ~~Montar el NFS compartido de certificados...~~ **Implementado distinto de lo previsto aquí**: en vez de NFS, el certificado viaja a Traefik como **Docker secret nativo de Swarm** (mismo mecanismo para `*.home.arpa` y `404labo.net`) — más simple, sin depender del NAS/NFSv3. El renovador desacoplado (mejora 32, `shared/scripts/renew-letsencrypt.sh`) sí quedó como estaba previsto: un único proceso, en `pi-dns`, fuera de Traefik y del swarm.
5. ~~Mover el frontend estático de Capataz a `pi-utils`...~~ **Ya hecho de antes** (2026-08-22, independiente de esta migración) — `capataz-frontend` ya corre como contenedor propio en `pi-utils`, confirmado en pie durante la verificación del cutover.
6. ~~Decidir y documentar el destino de `apikey-service`...~~ **Decidido con el usuario (2026-08-25)**: copia nueva dentro del swarm (sin `constraints`), en paralelo a la de `pi-dns` — comparten `postgres-main`, sin riesgo de divergencia. Detalle: `docs/31-docker-swarm.md` sub-fase 3b, segundo incremento.
7. **Pendiente**: actualizar `docs/01-topologia.md` — `pi-dns` deja de describirse como "puerta de entrada HTTPS del clúster", pasa a ser únicamente DNS interno + acceso remoto (Tailscale); el diagrama de arquitectura de servicios cambia su nodo de entrada. Se deja para el cierre general de la mejora 33 (Fase 5), junto con `CLAUDE.md`, para no tocar la documentación de topología dos veces mientras aún quedan servicios con estado por migrar (Fase 4).

### Esfuerzo estimado
Medio-alto — no es tanto trabajo nuevo en sí como una condición de diseño a aplicar cuando se implementen las mejoras 32, 33 y 35; el grueso del esfuerzo real vive en esas tres, esta mejora fija cómo encajan entre sí y qué le pasa a `pi-dns`.

---

## 40. DNS secundario del clúster — resolución de `*.home.arpa` sin depender solo de `pi-dns`

**Prioridad: media**

### Qué hay hoy

`pi-dns` (Unbound + Pi-hole) es el único resolutor interno del dominio `home.arpa` de todo el clúster (`docs/06-instalacion-pi1-dns.md`) — confirmado en producción que, de vez en cuando, algunos nodos pierden la conexión con él y caen al DNS secundario configurado (router/DNS público). Ese secundario resuelve internet con normalidad, pero **no tiene ningún conocimiento de `home.arpa`** — el resultado no es "sin DNS", es "sin resolución interna" hasta que el nodo vuelve a elegir a `pi-dns` como primario. El problema de fondo no es la ausencia de un secundario, es que el secundario que ya existe no sirve para lo único que aquí importa.

### Qué haría falta

1. **Segundo Unbound + Pi-hole en otro nodo siempre encendido** — nunca `ryzen` (se apaga habitualmente, mismo motivo por el que queda excluido del resto de roles críticos, mejoras 33/37/39); candidatos naturales: `pi-utils` o `pi-obs`, a decidir por carga disponible en el momento de implementarlo.
2. **Decisión abierta, no resuelta todavía**: alcance de la sincronización entre ambas instancias.
   - **Pi-hole completo** (bloqueo de anuncios + registros locales replicados) — más completo, pero Pi-hole no trae sincronización nativa entre instancias lista para usar sin más (según versión, `Teleporter`/exportación manual o un script propio contra su API); duplica en la práctica el mantenimiento manual que ya existe hoy para los registros de `home.arpa` (`shared/dns/dns-records.md` + alta manual en Pi-hole, según el propio `CLAUDE.md`).
   - **Solo Unbound** (sin Pi-hole en el secundario, sin bloqueo de anuncios ahí) — bastaría con mantener sincronizado un único fichero de zona/registros locales entre los dos nodos (la config de Unbound ya vive versionada en el repo, se replica sin más); reduce la superficie de sincronización al mínimo imprescindible: que ambos resuelvan `*.home.arpa` igual, sacrificando el bloqueo de anuncios en el camino secundario.
3. **DHCP del router**: añadir la IP del nuevo nodo como servidor DNS secundario en vez de (o antes que) el DNS del router/público — `docs/02-plan-ip-y-dns.md` es donde vive hoy la asignación de IP/DNS del clúster.
4. **Split DNS de Tailscale** (`docs/18-tailscale.md`): hoy apunta a una única IP (`192.168.1.170`) para resolver `home.arpa` dentro del tailnet — añadir la IP del secundario ahí también, o los clientes remotos seguirían teniendo el mismo punto único de fallo aunque la LAN local ya no lo tuviera.
5. **Mantener los registros sincronizados de cara al futuro**: si se combina con la mejora 34 (GitOps) o con Ansible (mejora 6), la sincronización de zona/registros entre ambas instancias es candidata natural a automatizarse ahí en vez de quedarse como proceso manual duplicado para siempre.

### Esfuerzo estimado
Bajo-medio — el despliegue en sí reutiliza la config de Unbound/Pi-hole ya existente y versionada; el trabajo real está en decidir el alcance de la sincronización (punto 2) y no es bloqueante, el clúster funciona hoy sin esto, solo con el punto ciego ya descrito cuando `pi-dns` tiene un problema puntual.

---

## 41. Retirar `*.home.arpa` por completo — todos los servicios bajo `404labo.net`

**Prioridad: media — a ejecutar cuando la mejora 33 (Swarm) esté cerrada del todo**

### Qué hay hoy

Tras el cutover de DNS de la mejora 33 (`docs/31-docker-swarm.md`, sub-fase 3b), **solo 2 de ~28 hostnames** usan el dominio público `404labo.net` (`home.404labo.net`/`capataz-api.404labo.net`, ambos del mismo servicio Capataz) — el resto sigue en `*.home.arpa`, resuelto solo en la LAN vía Pi-hole y servido con la CA interna propia (`docs/15-ca-interna.md`), que hay que instalar a mano en cada dispositivo cliente nuevo. El mecanismo para el dominio público ya está completamente resuelto y probado en producción (mejora 32): certificado **wildcard** `*.404labo.net` + apex, emitido y renovado sin intervención humana (`shared/scripts/renew-letsencrypt.sh`, cron en `pi-dns`, reto DNS-01 vía `dns_aws`/Route53). Al ser wildcard, cubre cualquier hostname nuevo bajo `404labo.net` sin reemitir nada — la parte cara de esta mejora ya está hecha, lo que queda es trabajo de enrutado y limpieza de referencias, no de PKI.

**Nota de seguridad ya discutida y resuelta**: con certificado wildcard (no uno por hostname), los nombres reales de los servicios (`vaultwarden.404labo.net`, `authentik.404labo.net`...) **no quedan expuestos en los logs de Certificate Transparency** — solo se ve que existe un wildcard válido para el dominio, no qué subdominios hay detrás. Tampoco existe ningún registro A público para estos hostnames (solo resuelven vía Pi-hole en la LAN) — mantener este mismo patrón (wildcard + sin registros A públicos) es condición para que esta mejora no aumente la superficie de ataque real.

### Qué haría falta

1. **Para cada hostname hoy en `*.home.arpa` servido por Traefik** (los ~26 de `docker-swarm/stacks/traefik/dynamic/routes.yml`, ver tabla completa en `shared/dns/dns-records.md`): añadir un router equivalente con `Host(<nombre>.404labo.net)`, reutilizando el mismo `service:` y el certificado wildcard ya cargado (`tls: {}` — Traefik ya elige el cert correcto por SNI, sin config adicional; mismo patrón que `home.404labo.net`/`capataz-api.404labo.net` ya usan hoy).
2. **Registrar los nuevos hostnames en Pi-hole** (`shared/dns/dns-records.md` + `shared/scripts/load-dns-records.sh`) — mismo mecanismo ya usado en el cutover de la mejora 33, sin registro A público en ningún caso (mantener la nota de seguridad de arriba).
3. **Periodo de coexistencia recomendado, no cutover directo**: dejar ambos dominios resolviendo al mismo servicio durante un tiempo prudencial (routers `Host(...)` en Traefik no son excluyentes, pueden convivir) antes de retirar `*.home.arpa` de Pi-hole — permite detectar referencias rotas sin presión.
4. **Barrido de referencias cruzadas hardcodeadas a `*.home.arpa`** — el trabajo real de esta mejora, no la PKI. Al menos ya identificado: `CAPATAZ_FRONTEND_OIDC_ISSUER`/Redirect URIs en Authentik (`docs/28`, ya tiene el patrón de añadir un Redirect URI nuevo por dominio, hecho una vez para `home.404labo.net`), cualquier `allowed origins`/CORS de las APIs propias, y cualquier `.env`/`docker-compose.yml` de nodo que referencie un hostname `.home.arpa` de OTRO servicio (no genérico, hay que revisar servicio a servicio — no se puede hacer con un solo `grep` de forma segura porque hay que confirmar cuáles son referencias reales y cuáles son solo documentación/comentarios).
5. **Decidir el destino de los 3 hostnames excluidos del cutover de la mejora 33** (`apikey.home.arpa`, `pihole.home.arpa`, `old.index.home.arpa`):
   - `pihole.home.arpa` — candidato natural a quedarse permanentemente en `home.arpa`: es la propia infraestructura de resolución DNS, resolverlo vía un dominio público añadiría una dependencia circular rara (necesitar DNS público para llegar al panel que gestiona el DNS interno).
   - `apikey.home.arpa`/`old.index.home.arpa` — mismo motivo que en la mejora 33 (sin puerto LAN publicado / sin backend de fichero-servidor en Traefik); resolver esto es tangencial a esta mejora, no bloqueante.
6. **Retirar la CA interna de los dispositivos cliente** una vez todo lo demás esté migrado y estable — el objetivo final que justifica la mejora: dejar de tener que instalar `docs/15-ca-interna.md` en cada dispositivo nuevo. Gradual, no de golpe.
7. Decidir si conviene un subdominio propio (p. ej. `cluster.404labo.net`) en vez de usar `404labo.net`/`*.404labo.net` a secas, por si el dominio se usa alguna vez para algo público no relacionado con el clúster — decisión abierta, hoy el dominio parece dedicado solo a esto.
8. Una vez migrado y estable: retomar la decisión, ya apuntada en la mejora 33, de decomisionar `nginx` en `pi-dns` de verdad (hoy se mantiene desplegado como vía de rollback).

### Esfuerzo estimado
Medio — el mecanismo de certificados y el enrutado en Traefik ya están resueltos y probados en producción (mejoras 32/33); el grueso real es el barrido manual de referencias cruzadas (punto 4) y decidir con calma, sin prisa, el destino de los 3 hostnames excluidos (punto 5).

### Cierre (2026-08-28)

Completada de punta a punta, sin excepciones. Los ~26 hostnames de Traefik pasaron por un periodo de coexistencia (ambos dominios en paralelo, verificados uno a uno) antes del corte final; ver `docs/31-docker-swarm.md` para el detalle completo del cierre y los dos incidentes reales encontrados en el proceso (carrera de arranque en Swarm con puertos publicados, y falta de almacén de CAs de sistema en varias imágenes base). Resumen de las decisiones tomadas en los 3 hostnames excluidos (punto 5) y el resto de puntos abiertos:

- **`pihole.home.arpa`** — sin sustituto de hostname, tal y como se apuntaba como candidato natural: panel publicado directo en la LAN por IP:puerto (`http://192.168.1.170:8053`), sin proxy delante.
- **`apikey.home.arpa`** — retirado; acceso administrativo directo por IP:puerto a la instancia canónica del propio Swarm (`http://192.168.1.175:8091`). La copia de `apikey-service` que vivía en `pi-dns` para servir a `nginx` se retiró también (mejora 39 quedó cerrada de paso).
- **`old.index.home.arpa`** — retirado sin sustituto, superseded por Capataz (mejora 15) desde antes.
- **CA interna** (punto 6) — NO retirada de los dispositivos cliente: Valkey (mejora 24) sigue firmando su certificado TLS con ella (un bug real de Swarm con bind-mounts `:ro` y claves TLS obligó a revertir el plan de reutilizar el wildcard real ahí, ver `docs/31`) — es el único consumidor que queda. `generate-ca.sh` se conserva activo; `generate-cert.sh` (el cert de `*.home.arpa`) sí quedó retirado, junto con el resto de `nginx`.
- **Subdominio propio** (punto 7) — no se adoptó; `404labo.net`/`*.404labo.net` a secas, sigue pareciendo dedicado solo a este clúster.
- **Decomisión de `nginx`** (punto 8) — hecha en este mismo cierre, junto con el resto.

---

## 42. Alertas de disponibilidad de nodos y servicios — nadie avisa hoy si algo se cae

**Prioridad: media**

### Qué hay hoy

Prometheus ya scrapea `node-exporter`/`cadvisor` de los 7 nodos (`pi-obs/config/prometheus.yml`, un `job_name` por nodo — `node-exporter-ryzen`, `node-exporter-retaco`, `node-exporter-pi-dns`, `node-exporter-pi-obs`, `node-exporter-pi-sonar`, `node-exporter-pi-utils`, `node-exporter-pinchi`, y el equivalente `cadvisor-*`) — la métrica estándar `up` (1 si el scrape responde, 0 si no) ya existe para cada uno, sin que haga falta añadir nada nuevo para tener la señal. El único consumidor activo de esa clase de dato hoy es la alerta de undervoltage (`pi-obs/config/grafana/alerting/undervoltage.yml`, `docs/14-monitorizacion-completa-cluster.md`) — no existe ninguna regla equivalente sobre `up`, así que un nodo caído (`pi-utils` se cayó unos días antes de escribir esto, sin que nadie se enterara hasta comprobarlo a mano) no genera ningún aviso, solo un hueco silencioso en los paneles de Grafana para quien entre a mirarlos.

**Decisión ya tomada, no evaluar de nuevo**: no se adopta Uptime Kuma ni herramienta equivalente. El dato que haría falta vigilar (¿responde este nodo?) ya lo tiene Prometheus por el simple hecho de scrapear — una herramienta aparte duplicaría esa vigilancia y añadiría una pieza más de la que depender (incluida la pregunta recursiva de quién avisa si la propia herramienta de vigilancia se cae). Grafana Alerting (nativo desde v8, ya en uso para undervoltage) es la vía natural: reutiliza infraestructura ya desplegada y el mismo patrón de fichero de aprovisionamiento ya probado.

### Qué haría falta

1. Regla de alerta nueva, mismo patrón que `undervoltage.yml`: `pi-obs/config/grafana/alerting/node-down.yml`, condición `up{job=~"node-exporter-.*"} == 0` sostenida un par de minutos (evitar falsos positivos por un reinicio rápido o una ventana de mantenimiento) — una alerta por nodo, usando `{{ $labels.job }}` en el mensaje para identificar cuál.
2. Decidir el alcance real: ¿solo "¿responde el nodo?" (`node-exporter-*`), o también "¿responde el contenedor de métricas?" (`cadvisor-*`, sería redundante con lo anterior en la práctica ya que ambos corren en el mismo host) y/o alertas específicas por servicio HTTP (necesitaría `blackbox_exporter`, no desplegado hoy — mucho más granular pero una pieza nueva de verdad, a diferencia de la regla de `up` que no necesita nada nuevo). Empezar por nodo es lo mínimo que resuelve el incidente real que motiva esta mejora.
3. Canal de notificación — ya disponible desde que se implementó la mejora 4 (ntfy, `docs/34-ntfy-notificaciones.md`): añadir la label `category` que corresponda a esta alerta nueva y un matcher en `pi-obs/config/grafana/alerting/notification-policies.yml`, mismo mecanismo ya probado con undervoltage/SAI.
4. Montar el fichero nuevo como bind-mount adicional en `docker-swarm/stacks/pi-obs/docker-compose.yml` (junto a `undervoltage.yml`, mismo `volumes:` de `grafana`), `docker service update --force pi-obs_grafana` (o redeploy del stack) para que lo recoja.
5. Probarlo de verdad, no solo confirmar que la regla carga en la UI: parar `node-exporter` de un nodo a propósito (o apagarlo con cuidado) y confirmar que la alerta dispara y notifica de verdad por el canal elegido.

### Esfuerzo estimado
Bajo — reutiliza infraestructura y patrón exactamente iguales a los de la alerta de undervoltage ya provisionada (punto 1 es casi mecánico); el canal de notificación (punto 3) ya no es una dependencia externa, es solo añadir un matcher.

---

## 43. ~~Auditoría de bind-mounts en Docker Swarm — evaluar alternativas a la fijación por nodo (y a los puertos en `mode: host` que provoca)~~ — hecho

**Prioridad: media**

### Qué hay hoy

**Hallazgo de partida**: el 100 % del estado real de este clúster en Docker Swarm se sirve hoy con
bind-mounts de host (`/srv/homelab/<nodo>/...` o, en dos casos, `/mnt/nfs-data/...` del NAS) — no
hay ni un solo volumen Docker nombrado (`driver: local` o cualquier otro) en ninguno de los 25
stacks de `docker-swarm/stacks/` (confirmado por barrido, `grep` de referencias a volumen que no
empiecen por `/`). Un bind-mount solo contiene datos reales en el nodo físico donde vive ese
directorio, así que **cualquier servicio con bind-mount de estado real necesita
`deploy.placement.constraints: node.hostname==X`** para que Swarm lo reprograme siempre en el mismo
nodo — sin eso, una tarea reprogramada en otro nodo arrancaría con un directorio vacío (o fallaría
al arrancar, según el servicio) en vez de recuperar los datos existentes.

Esto es la razón estructural de por qué la inmensa mayoría de los stacks de este clúster llevan un
`constraints: node.hostname==X` fijo — no es una limitación elegida a propósito, es la consecuencia
directa de no usar ningún mecanismo de volumen portable. Vale la pena revisarlo servicio a servicio:
para muchos (una base de datos con un único escritor, por ejemplo) fijar el nodo es correcto y no
hay alternativa real sin asumir latencia de red en cada escritura; para otros, puede que no haga
falta ningún estado real en disco, o que el estado sea prescindible, o que ya se haya resuelto sin
necesidad de bind-mount — y en esos casos merece la pena preguntarse si el constraint sigue
justificado.

#### Inventario completo — bind-mounts por stack/servicio (2026-08-29)

**Con bind-mount de estado real + `constraints: node.hostname==X`** (la mayoría — el nodo está
fijado y, hoy, con razón: cada uno es el único sitio donde vive el dato):

| Stack | Servicio(s) | Nodo | Bind-mount(s) | Naturaleza del dato |
|---|---|---|---|---|
| `postgres-main` | `postgres-main` | `retaco` | `/srv/homelab/retaco/postgres/{data,init}` | Real — BD multi-tenant compartida por casi todo el clúster |
| `infisical` | `postgres-infisical` | `retaco` | `/srv/homelab/retaco/postgres-infisical/data` | Real — BD dedicada, instancia separada de `postgres-main` a propósito (ADR 0002) |
| `infisical` | `infisical` | `retaco` | CA interna (`ca/homelab-ca.crt`, solo lectura) | Config — pinnado por compartir stack/red con `postgres-infisical`, no por datos propios |
| `n8n-main` | `n8n-main` | `retaco` | `/srv/homelab/retaco/n8n/data` | Real — workflows y credenciales |
| `n8n-aux` | `n8n-aux` | `pi-utils` | `/srv/homelab/pi-utils/n8n-aux/data` | Real — SQLite propio |
| `qdrant` | `qdrant` | `retaco` | `/srv/homelab/retaco/qdrant/{storage,snapshots}` | Real — vectores de RAG |
| `registry` | `registry` | `retaco` | `/srv/homelab/retaco/registry/{data,auth}` | Real — blobs de imágenes + htpasswd |
| `open-webui` | `open-webui` | `retaco` | `/srv/homelab/retaco/open-webui/data` | Real — usuarios, chats, config (Postgres desde la migración, este directorio ya es solo residual/CA) |
| `open-terminal-mcp` | `open-terminal-mcp` | `retaco` | `/srv/homelab/retaco/open-terminal-mcp/home` | Real — workspace del terminal |
| `valkey` | `valkey` | `retaco` | `/srv/homelab/retaco/valkey/{users.acl,tls}` | Config (ACL/TLS) — Valkey en sí no persiste datos en disco aquí, es solo caché en memoria |
| `authentik` | `authentik-server`, `authentik-worker` | `retaco` | `/srv/homelab/retaco/authentik/data` (+ `certs` en el worker) | Real — compartido entre ambos servicios, deben coincidir de nodo por eso además del bind-mount |
| `vaultwarden` | `vaultwarden` | `pi-utils` | `/srv/homelab/pi-utils/vaultwarden/data` | Real — vault SQLite del gestor de contraseñas |
| `rsshub` | `rsshub` | `pi-utils` | `/srv/homelab/pi-utils/rsshub/data` | Real/caché de feeds |
| `portainer-server` | `portainer` | `pi-utils` | `/srv/homelab/pi-utils/portainer/data` | Real — BoltDB de Portainer |
| `capataz` | `capataz-api`, `capataz-runner`, `capataz-frontend` | `pi-utils` | `catalog/`, `api/alembic*`, `certs/`, `config/capataz-frontend/default.conf` | Config — el estado real de Capataz vive en `postgres-main`/Valkey, no en estos bind-mounts |
| `bifrost` | `bifrost` | `pi-sonar` | `/srv/homelab/pi-sonar/bifrost/data` | Mixto — `config.json` + SQLite legado sin usar; el estado real ya vive en `postgres-main` (`docs/23`) |
| `sonarqube` | `sonarqube` | `pi-sonar` | `/srv/homelab/pi-sonar/sonarqube/{data,extensions,logs,temp}` | Real |
| `pi-obs` | `loki`, `tempo`, `prometheus`, `grafana` | `pi-obs` | `/srv/homelab/pi-obs/{loki,tempo,prometheus,grafana}/...` | Real, pero regenerable a propósito (sin backup salvo Grafana) |
| `pi-obs` | `otel-collector`, `postgres-exporter` | `pi-obs` | Solo config de solo lectura (`otel-collector`) o ninguno (`postgres-exporter`) | Config/ninguno — comparten el constraint del stack (mismo `deploy:` con ancla YAML) sin necesitarlo por datos propios |
| `epub2pdf-service` | `epub2pdf-service` | `retaco` | `/mnt/nfs-data/epub2pdf/{input,output}` (NFS del NAS `ketekasko`) | Externo — confirmado que solo `retaco` tiene ese montaje NFS entre los 5 nodos |
| `pdf2chunks-service` | `pdf2chunks-service` | `retaco` | `/mnt/nfs-data/pdf2chunks/input` (mismo NAS) | Externo — mismo motivo que `epub2pdf-service` |

**Con bind-mount pero SIN `constraints` de nodo** (casos límite — a revisar con prioridad, ver
"Qué haría falta"):

| Stack | Servicio | Nodo | Bind-mount(s) | Por qué no está pinnado hoy |
|---|---|---|---|---|
| `apikey-service` | `apikey-service` | Ninguno — Swarm elige entre los 5 | `infisical-cli/infisical` (binario) + `ca/homelab-ca.crt` | Ficheros idénticos replicados a mano en `/srv/homelab/apikey-service/` de los 5 nodos — decisión deliberada, documentada en el propio compose, pero depende de que ese `rsync` manual nunca quede desincronizado en algún nodo (mismo tipo de fallo ya visto con Bifrost, ver `docs/23`) |
| `markitdown` | `markitdown-service` | Ninguno — Swarm elige entre los 5 | `/srv/homelab/markitdown-cache` | Caché scratch, pérdida asumida a propósito si Swarm reprograma a otro nodo — decisión deliberada, sin riesgo real |

**`mode: global` con bind-mount idéntico en cada nodo** (patrón correcto por diseño, sin acción
necesaria — cada réplica lee el propio host donde corre, no datos compartidos):

| Stack | Servicio | Bind-mount(s) |
|---|---|---|
| `common` | `node-exporter` | `/proc`, `/sys`, `/`, `/srv/homelab/node-exporter-textfile` |
| `common` | `cadvisor` | `/`, `/var/run`, `/sys`, `/var/lib/docker`, `/dev/disk` |
| `portainer` (agent) | `agent` | `/var/run/docker.sock`, `/var/lib/docker/volumes` |
| `traefik` | `traefik` | `/var/run/docker.sock` |

**Sin ningún volumen** (totalmente portable, sin acción posible ni necesaria): `crawl4ai-scraper-service`.

#### Efecto colateral del pin: puertos en `mode: host` en vez de `mode: ingress`

Publicar un puerto en Swarm sin decir nada usa `mode: ingress` por defecto — la routing mesh, que
reserva ese puerto en **los 5 nodos**, no solo en el que ejecuta la tarea. Ocho servicios de este
clúster publican su puerto en `mode: host` en su lugar (reserva solo en el nodo real), y en la
mayoría de los casos el motivo documentado es exactamente el mismo tipo de problema que motiva esta
mejora: al estar pinnados a un nodo por su bind-mount, dos servicios pinnados a nodos *distintos*
pueden compartir el mismo número de puerto sin chocar — pero solo si ninguno usa `mode: ingress`,
porque ese modo sí reservaría el puerto en el swarm entero y chocaría igualmente aunque estén en
nodos físicos diferentes:

| Stack/servicio | Puerto | Motivo documentado en el propio compose | ¿Colisión de puerto confirmada en vivo? |
|---|---|---|---|
| `bifrost` | 8080 | Mismo puerto que `open-webui` (nodo distinto) | Sí — encontrada al desplegar |
| `open-webui` | 8080 | Mismo puerto que `bifrost` | Sí — encontrada al desplegar |
| `authentik-server` | 9000 | Histórico: compartía puerto con `sonarqube`/`portainer-server`. **Ambos liberados y `constraints`/`mode: host` retirados del todo (2026-08-31)** — junto con `/data`/`/certs` en NFS y el binario de `infisical` en ruta multi-arquitectura compartida, `authentik-server`/`authentik-worker` quedan sin pin de nodo, en `mode: ingress`. Confirmado en vivo: tras forzar el redespliegue, Swarm reprogramó ambas tareas a `pi-sonar` (no `retaco`) sin intervención manual, todo verificado sano desde el nodo nuevo | Histórico, ya no aplica |
| `sonarqube` | ~~9000~~ **19000** | ~~Mismo puerto que `authentik-server`~~ **Resuelto (2026-08-31)**: republicado en 19000 | Histórico, ya no aplica |
| `portainer-server` | ~~9000~~ **19001** | ~~Mismo puerto que `authentik-server`~~ **Resuelto (2026-08-31)**: republicado en 19001 (el `constraints: node.hostname==pi-utils` se queda igual — lo exige la BoltDB real, no el puerto) | Histórico, ya no aplica |
| `capataz-api` | 8000 | Sin comentario que documente una colisión real | **No** — ningún otro stack publica el 8000 |
| `capataz-frontend` | 8090 | Sin comentario que documente una colisión real | **No** — ningún otro stack publica el 8090 |
| `infisical` | 8006 | Sin comentario que documente el motivo | **No** — ningún otro stack publica el 8006 |

Los cinco primeros tienen una colisión real y documentada — `mode: host` ahí es la corrección
correcta mientras sigan pinnados, no algo a revisar. Los tres últimos (`capataz-api`,
`capataz-frontend`, `infisical`) no tienen ninguna colisión real detrás — todo apunta a que se puso
`mode: host` por coherencia con el resto del stack (ya pinnado de todas formas por el bind-mount),
no porque hiciera falta. Si el pin de esos servicios se revisa (ver `docker config` más abajo) y
deja de ser necesario, `mode: host` también debería revisarse — mantenerlo sin necesidad renuncia a
la routing mesh (balanceo entre réplicas, tolerancia a que Swarm reprograme la tarea) sin ganar nada
a cambio.

### Qué haría falta

1. **Revisar los dos casos "sin constraints" primero** (`apikey-service`, `markitdown-service`) — son los que peor encajan hoy: o se documenta explícitamente por qué es seguro dejarlos así (ya hecho parcialmente en comentarios), o se sustituye el `rsync` manual a los 5 nodos del binario de Infisical/CA de `apikey-service` por el mecanismo de `docker config` descrito en el punto siguiente.
2. **Sustituir por `docker config` los bind-mounts que en realidad son un único fichero de texto de solo lectura, sin secretos** — mecanismo ya probado en este mismo clúster (`traefik-dynamic-routes-v5`, `docker-swarm/stacks/traefik/`), y **la alternativa correcta para el caso de Bifrost**, no una NFS ni mantener el bind-mount:
   - **`bifrost` es el caso más claro de todo el inventario**: `config.json` es exactamente la forma que un `docker config` está pensado para resolver (fichero pequeño, de solo lectura, sin ningún secreto en claro — todos los campos sensibles ya usan el prefijo `env.`, resuelto en tiempo de arranque vía Infisical, no desde el propio fichero). Además, **el propio comentario del stack ya admite que `/app/data` "solo aloja ficheros de trabajo internos" y que no hay estado real ahí desde la migración a Postgres** (`docker-swarm/stacks/bifrost/docker-compose.yml`, cabecera) — así que convertir `config.json` en un `docker config` no sería solo un cambio de mecanismo de despliegue, sino la vía real para **cuestionar si `bifrost` necesita seguir pinnado a `pi-sonar` en absoluto** (verificar primero que ningún otro fichero de `/app/data` se sigue escribiendo de verdad antes de retirar el bind-mount entero, no asumirlo). De paso, habría evitado por completo el incidente real del 2026-08-29 (`docs/23-bifrost-gateway-llm.md`, "`config.json` desincronizado tras retirar `home.arpa`") — con un `docker config`, `docker stack deploy` reparte el contenido nuevo solo, sin depender de un `rsync` manual que alguien puede olvidar.
   - **Otros candidatos claros vistos en el inventario de arriba**, misma forma (fichero único, de solo lectura, sin secretos): `config/capataz-frontend/default.conf` (`capataz`); `loki.yaml`/`tempo.yaml`/`prometheus.yml`/`otel-collector.yaml`/`datasources.yml`/`alerting/undervoltage.yml`/`dashboards.yml` (`pi-obs` — varios de estos, no solo `undervoltage.yml`, ya podrían ir por este camino).
   - **Límites reales del mecanismo, a tener en cuenta antes de aplicarlo**: un `docker config` es un fichero único, no un directorio (descarta de raíz `catalog/`/`alembic/` de `capataz` y `dashboards/json/` de `pi-obs` tal cual, habría que trocearlos en un config por fichero, no siempre compensa); tiene un límite de 500 KB (ninguno de los candidatos de arriba se acerca); y **nunca debe llevar secretos** — el `users.acl` de `valkey`, por ejemplo, hoy lleva una contraseña en claro dentro del propio fichero (`user capataz on >{contraseña} ...`), así que ese caso concreto necesitaría separar la contraseña a un `docker secret` aparte antes de poder convertir el resto del ACL en `docker config`, no vale con moverlo tal cual.
   - Sigue siendo **inmutable como los `docker secret`** (mismo patrón `-vN` ya usado en todo el repo) — cualquier cambio de contenido exige bump de versión + `docker stack deploy`, no un `docker config update` en sitio.
3. **Para cada servicio de la primera tabla (bind-mount + constraint) que NO sea un candidato a `docker config`, confirmar que el pin sigue siendo la decisión correcta y que está documentado como tal** — la mayoría de los `docker-compose.yml` ya llevan un comentario explicando el motivo (patrón exigido por `CLAUDE.md`), pero conviene verificar que ninguno se quedó sin esa justificación tras ediciones posteriores.
4. **Revisar los tres servicios en `mode: host` sin colisión de puerto documentada** (`capataz-api`, `capataz-frontend`, `infisical`, ver tabla de arriba) — comprobar primero si de verdad no hay colisión (no solo confiar en que no hay comentario) y, si el pin que los fuerza a `mode: host` se resuelve con `docker config`, volver a `mode: ingress` a la vez. **`capataz-api` es el caso trabajado**, con los datos reales del bind-mount comprobados en `pi-utils` (2026-08-29):
   - `catalog/services.example.yaml` — fichero único, 43 KB → candidato directo a `docker config`.
   - `api/alembic.ini` — fichero único, 568 bytes → candidato directo a `docker config`.
   - `certs/` (`ca-bundle.pem` 186 KB + `homelab-ca.crt` 1,8 KB, usado también por `capataz-runner`) — dos ficheros, ambos por debajo del límite de 500 KB → dos `docker config` separados, uno por fichero.
   - `api/alembic/` (`env.py` + `versions/`, un directorio con varios ficheros que crece con cada migración nueva) — **no** encaja en `docker config` (solo admite un fichero, no un directorio) — este es el único de los cuatro bind-mounts de `capataz-api` que de verdad seguiría necesitando algo distinto de `docker config`; valorar aparte si tiene sentido hornear las migraciones dentro de la imagen (van versionadas con el propio código de Capataz) en vez de seguir pasándolas por bind-mount — cuestión del repo externo de Capataz, no de este, así que no forzarla dentro de esta tarea.
   - Si `alembic/` se resuelve aparte (o se acepta como el único motivo real de pin restante), `capataz-runner` y `capataz-frontend` quedarían con **cero** bind-mounts propios (`certs/` y `default.conf` respectivamente, ambos ya cubiertos por `docker config`) — candidatos a perder el `constraints: node.hostname==pi-utils` heredado del stack y volver a `mode: ingress` en su puerto.
5. **Evaluar un volumen NFS-backed contra el NAS `ketekasko`** (ya probado NFSv3, `docs/21-configuracion-nas-ugreen.md`) como alternativa real al bind-mount local para los candidatos con menos escritura/latencia crítica que sí tengan estado real (p. ej. `registry`, `grafana`, `vaultwarden`) — **no** para bases de datos con escritura frecuente real (`postgres-main`, `qdrant`, `loki`, `prometheus`) sin medir antes: NFS añade latencia por escritura que puede degradar justo el tipo de servicio que más se beneficiaría de dejar de estar pinnado. El resultado esperado para la mayoría de estos es probablemente "mantener el bind-mount + constraint tal cual", pero que sea una decisión explícita y medida, no un valor por defecto sin examinar.
6. **Para los dos servicios atados al NFS solo-en-`retaco`** (`epub2pdf-service`, `pdf2chunks-service`): valorar montar `ketekasko:/volume1/nfs-data` también en los otros 4 managers (técnicamente ya viable, mismo patrón NFSv3) para poder retirar el `constraints` — sopesando el coste real (4 puntos de montaje NFS más que mantener) frente al beneficio (servicios de conversión de bajo tráfico, el pin apenas cuesta algo hoy).
7. **Actualizar esta misma tabla** en este documento (o moverla a `docs/31-docker-swarm.md`, que ya es el documento de referencia operativo de Swarm) una vez revisado cada servicio, marcando la decisión tomada — para que no vuelva a quedar como un inventario "de un momento dado" sin mantener.

### Esfuerzo estimado
Medio — el barrido en sí ya está hecho (tablas de arriba, incluida la de `mode: host`); el trabajo real está en medir antes de tocar cualquier servicio con escritura frecuente (punto 5) y en decidir, servicio a servicio, si el pin actual es la opción correcta o solo la que salió por defecto. Los casos de Bifrost y Capataz (puntos 2 y 4) son los más baratos de resolver de todo el inventario — mecanismo ya probado en el propio clúster (`docker config`), sin necesidad de medir latencia, y con el beneficio añadido de poder volver a `mode: ingress` en Capataz. Ningún cambio de este punto es urgente: todos los pins actuales funcionan correctamente hoy.

### Cierre (2026-08-31)

Ejecutados los puntos 1-4 y 7; los puntos 5 y 6 se evalúan y se decide explícitamente no ejecutarlos por ahora (razón al final).

- **Punto 1 (`apikey-service`/`markitdown-service`)**: revisado, sin cambio de código. El binario de `infisical` pesa 123 MB en vivo (confirmado en `pi-utils`) — muy por encima del límite de 500 KB de `docker config`, así que el bind-mount + réplica por nodo sigue siendo la única opción real. Ya estaba formalmente decidido (`docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md`) y automatizado (`shared/scripts/deploy-infisical-cli.sh`, no un `rsync` ad-hoc) — se anota en el propio compose y se cierra el punto sin tocar nada más. `markitdown-service` seguía ya correcto (caché scratch, sin constraint).
- **Punto 2 (`docker config` para bind-mounts de solo lectura)**:
  - **Bifrost**: `config.json` pasa a `docker config` (`bifrost-config-v1`, `file:` versionado en `docker-swarm/stacks/bifrost/config.json`, movido desde `pi-sonar/config/bifrost/`). Verificado en vivo antes de tocar nada: `config.db`/`logs.db` (SQLite legado de la mejora 23) y `logs/` llevan sin escribirse desde antes del 2026-08-07 — sin estado real en `/app/data` hoy, solo `config.json`. **Pero el bind-mount de `/app/data` NO se retira** (a diferencia de lo que este mismo documento sugería) — la imagen exige que ese directorio exista y sea escribible por UID:GID 1000:0 al arrancar, o falla (`docs/23`, incidente real del primer despliegue); el `docker config` se superpone solo sobre `config.json` dentro del bind-mount existente. El `constraints: node.hostname==pi-sonar` tampoco se retira: no lo sostienen los datos (ya sin estado real) sino el puerto 8080 en `mode: host`, que choca con `open-webui` (`retaco`, mismo puerto) si Swarm lo reprogramase ahí — hallazgo nuevo, no estaba en el inventario original, anotado en la cabecera del compose. Redesplegado y verificado (`docker service ps`, arranque limpio sin errores de `/app/data`, `curl` real a `https://bifrost.404labo.net/v1/models` responde `401` como se espera sin virtual key).
  - **Capataz**: `catalog/services.example.yaml`, `api/alembic.ini`, `certs/ca-bundle.pem`, `certs/homelab-ca.crt` pasan a `docker config ... external: true` (creados a mano desde los ficheros reales en `pi-utils` — vienen del checkout parcial del repo *externo* de Capataz, no están versionados en este repo, así que no usan `file:`). `capataz-frontend-default.conf` sí estaba versionado aquí (movido desde `pi-utils/config/capataz-frontend/`) — pasa a `docker config` con `file:`, igual que Bifrost. `api/alembic/` (directorio, crece con cada migración) se queda como bind-mount — no cabe en `docker config`, hornear las migraciones en la imagen es decisión del repo externo de Capataz, fuera de alcance. Redesplegado y verificado: los tres servicios sanos, login OIDC real y health-check reales por hostname (`https://capataz-api.404labo.net/health/live` → 200, `https://home.404labo.net/` → 200), `capataz-runner` conecta por TLS a Valkey (`rediss://...`, confirma que `certs/` sigue resoluble desde el `docker config`).
  - **pi-obs** (`loki.yaml`/`tempo.yaml`/`prometheus.yml`/etc.): evaluado, **no ejecutado en esta pasada** — no desbloquea ningún des-pin (pi-obs sigue fijado por datos reales de Loki/Tempo/Prometheus/Grafana), sería solo un mecanismo de despliegue más limpio (evita el `rsync` manual). Queda como mejora futura de bajo riesgo, sin urgencia.
  - **`valkey` (`users.acl`)**: evaluado, **no ejecutado** — lleva una contraseña en claro dentro del propio fichero, necesitaría separarla a un `docker secret` antes de poder convertir el resto del ACL a `docker config`. Fuera de alcance de esta pasada.
- **Punto 3 (verificar comentarios de justificación)**: repasados los 16 stacks restantes con `constraints` (`postgres-main`, `n8n-main`, `n8n-aux`, `qdrant`, `registry`, `open-webui`, `open-terminal-mcp`, `valkey`, `authentik`, `vaultwarden`, `rsshub`, `portainer-server`, `sonarqube`, `pi-obs`, `epub2pdf-service`, `pdf2chunks-service`) — todos ya explican el motivo del pin junto al `constraints:`, sin huecos. Sin cambios.
- **Punto 4 (`mode: host` sin colisión documentada)**: confirmado por `grep` en los 25 stacks que ningún otro servicio publica 8000/8090/8006 — `capataz-api` (8000) y `capataz-frontend` (8090) vuelven a `mode: ingress`; `infisical` (8006) también, aunque su `constraints: node.hostname==retaco` se queda igual (lo exige compartir stack/red con `postgres-infisical`, estado real, no el puerto). `capataz-runner` y `capataz-frontend` pierden además `constraints: node.hostname==pi-utils` al quedarse sin bind-mounts propios — confirmado en vivo que Swarm los reprogramó de hecho (aterrizaron primero en `pinchi`, antes de volver a `pi-utils` tras un problema de DNS no relacionado en ese nodo, ver más abajo). `capataz-api` mantiene el constraint por `api/alembic/`.
- **Puntos 5 y 6 (NFS-backed volumes)**: evaluados el 2026-08-29, **decisión inicial: mantener el bind-mount + constraint tal cual para todos los candidatos** (`registry`, `grafana`, `vaultwarden`, `epub2pdf-service`, `pdf2chunks-service`) — sin medir latencia NFS real, sin síntoma en ese momento de que alguno estuviera sufriendo por estar fijado.
  - ⚠️ **Revisado en la práctica el 2026-08-31**, en la revisión completa de `constraints` que siguió al cierre de esta mejora (ver `docs/01-topologia.md`, sección "Estado actual: servicios en Docker Swarm"): `registry` (32G, blobs por hash de contenido, sin BD embebida), `epub2pdf-service` y `pdf2chunks-service` (ya usaban ese mismo NFS, el pin solo existía porque antes únicamente `retaco` tenía el punto de montaje) **sí se movieron a NFS**, sin problema — el resultado esperado de este documento no se cumplió para estos tres. `vaultwarden`, en cambio, sí se dejó fuera de NFS a propósito (SQLite activo + clave privada RSA — se movió a disco local en `pinchi` en su lugar, no a NFS). `grafana`/`pi-obs` no se tocaron en esa revisión, siguen pendientes tal cual se decidió aquí.
- **Hallazgo colateral, no parte del alcance de esta mejora**: al des-pinnar `capataz-runner`/`capataz-frontend`, Swarm los programó por primera vez en `pinchi` — que resultó tener el mismo bug de DNS ya documentado en `docs/13-troubleshooting.md` (`systemd-resolved` colgado en el servidor secundario, `1.1.1.1`, en vez de `pi-dns`), nunca detectado antes porque `pinchi` no había alojado ningún servicio hasta ahora. Corregido en vivo (`sudo systemctl restart systemd-resolved`), Swarm reintentó solo y las tareas acabaron sanas.

---

## 44. Pendiente de revisión — `sonarqube` se cuelga arrancando `infisical run` en `pinchi` (funciona en `pi-sonar` y en el resto de servicios ya movidos a `pinchi`)

**Prioridad: media** (bloquea mover `sonarqube` a un disco más fiable que la microSD de `pi-sonar`, pero el servicio funciona con normalidad mientras se quede donde está)

### Qué se intentó (2026-08-31)

Mover `sonarqube` de `pi-sonar` (Raspberry Pi 5, microSD) a `pinchi` (PC x86_64, NVMe SSD) — mismo motivo y mismo patrón ya aplicado con éxito a `portainer-server` ese mismo día (fiabilidad de escritura para una base de datos embebida real, en este caso el índice de Elasticsearch de SonarQube, `data/es8`/`es9`). Migración de datos hecha con el servicio parado + `tar` en pipe directo nodo a nodo + verificación de tamaño — sin incidentes en esa parte.

Al desplegar en `pinchi`, el contenedor arranca pero se queda colgado **indefinidamente** (probado más de 10 minutos sin ningún avance) en el paso `infisical run --token=... -- /opt/sonarqube/docker/entrypoint.sh` del `entrypoint:` — el proceso `infisical run` queda como PID 1, 0% CPU, estado `Ssl` (dormido), sin ningún proceso hijo (`/opt/sonarqube/docker/entrypoint.sh` nunca llega a ejecutarse), sin ninguna línea nueva en los logs (Loki).

### Lo que se descartó como causa, con evidencia real

- **Red/DNS/TLS**: descartado con `curl` directo desde un contenedor suelto en la misma red overlay (`sonarqube-net`) hacia `https://infisical.404labo.net/api/status` (`200`, 52 ms) y hacia `https://app.infisical.com` (`200`, 394 ms) — ambos instantáneos.
- **CA interna**: `homelab-ca-bundle-v1` montado correctamente (185.872 bytes, igual que en el resto de servicios).
- **IP allowlisting de la identidad de Infisical**: hipótesis considerada y **descartada** — `docs/26-infisical-secretos.md` documenta explícitamente que esa función es de pago (Pro/Enterprise) y no existe en la edición Community autoalojada de este clúster.
- **Petición ni siquiera llega a Infisical**: confirmado consultando los logs del propio `infisical_infisical` vía Loki — cero líneas mencionando "sonarqube" en los 10 minutos del intento, pese a que el resto de servicios sí dejan rastro claro de la petición de secretos.

### Lo que NO se pudo terminar de diagnosticar

Reproducir el mismo comando `infisical run` a mano (con el token real ya emitido, capturado de `ps aux`) para ver el punto exacto del cuelgue — bloqueado por el clasificador de seguridad de Claude Code al detectar un token de autenticación real en la línea de comandos de prueba (comportamiento correcto del clasificador, no un fallo — no se intentó rodearlo).

**Dato relevante para la próxima vez**: `authentik`, `bifrost` y `open-webui` ya arrancaron sin problema en `pinchi` ese mismo día, con el mismo mecanismo exacto de `infisical login` + `infisical run` (mismo binario, misma ruta compartida `/srv/homelab/infisical/infisical-cli/infisical`, mismo `homelab-ca-bundle-v1`). Algo específico de la identidad/proyecto/secretos de `sonarqube`, o de su imagen concreta, causa esto — no es un problema genérico de Infisical en `pinchi`.

### Qué haría falta para retomarlo

1. Reproducir el cuelgue con margen para depurar con calma (no en producción) — idealmente en un contenedor de prueba, con el token pasado por variable de entorno o fichero en vez de en la línea de comandos (evita el bloqueo del clasificador de seguridad y es más seguro de todas formas).
2. Si el CLI de Infisical soporta algún flag de verbosidad/debug, usarlo para ver en qué llamada exacta se queda esperando.
3. Comparar la configuración de la Machine Identity de `sonarqube` en el panel de Infisical contra la de `authentik`/`bifrost`/`open-webui` (rol, método de auth, cualquier diferencia real) — por si hay algo específico de esa identidad, no de la red.
4. Solo entonces reintentar el traslado a `pinchi`.

### Estado actual (revertido, sin pérdida de datos)

`sonarqube` vuelve a `pi-sonar` (`constraints: node.hostname==pi-sonar`), mismo `data/` (índice de Elasticsearch) de siempre, sin tocar — verificado que el `id` de instancia de la API (`5EFBA1AB-AZ-EVE3dG4vWQuGQw0S_`) coincide exactamente con el de antes del intento. Lo demás del intento SÍ se mantiene, porque no depende de en qué nodo esté el servicio y quedó verificado funcionando antes del cuelgue: `extensions/` en NFS, `logs/`/`temp/` en `tmpfs`, binario de `infisical` en la ruta compartida multi-arquitectura, puerto en `mode: ingress`.

### Esfuerzo estimado
Bajo-medio — el barrido de descarte ya está hecho (red, DNS, TLS, CA, allowlisting), lo que falta es una sesión de depuración específica con margen para reproducir el cuelgue de forma segura.

---

## 45. ~~Dashboards de Grafana por servicio — hoy casi todo el clúster no tiene ninguno propio~~ — hecho

**Prioridad: media** — **completado (2026-09-03)**, con un paso manual pendiente sin bloquear el cierre (ver abajo)

### Qué se implementó

Plantilla genérica parametrizable, `pi-obs/config/grafana/dashboards/json/servicio-generico.json` (uid `homelab-servicio-generico`, carpeta `Homelab`), en vez de un JSON por servicio (punto 5 de la redacción original, ya decidido a favor de la plantilla) — una variable `$servicio` cubre los ~38 servicios reales del clúster (26 stacks de Swarm + 12 servicios de Compose clásico, incluido `ryzen`) con 9 paneles: contenedores activos, reinicios en la ventana visible (`resets(container_start_time_seconds[...])`, funciona igual para una tarea reprogramada por Swarm que para un contenedor de Compose reiniciado a mano), uptime del contenedor más reciente, CPU/memoria/red (RX/TX) por cAdvisor, y volumen + panel de logs en crudo (Loki).

**Decisión real, no la de la redacción original**: Swarm y Compose clásico etiquetan sus contenedores con esquemas distintos (`container_label_com_docker_stack_namespace`/`swarm_stack` en Swarm frente a `container_label_com_docker_compose_service`/`compose_service` en clásico) — unificarlos de raíz habría exigido tocar la configuración de ~30 stacks más el pipeline de logging, un cambio de infraestructura real. En su lugar, cada panel combina ambos esquemas con el operador `or` de PromQL/dos filas de query en Loki, de forma que **una sola variable `$servicio` sirve para los dos mundos sin que quien la usa tenga que saber cuál es** — ej. `container_last_seen{...stack_namespace="$servicio"} or container_last_seen{...compose_service="$servicio"}`. Motivo: el usuario quiere embeber estos dashboards por iframe en otras páginas y necesita una única convención de URL, sin distinguir Swarm/clásico en la query string.

**Embebible por URL** (el caso de uso real que motivó la decisión de arriba): `https://grafana.404labo.net/d/homelab-servicio-generico/servicio-generico?orgId=1&var-servicio=<nombre>&kiosk` — cambiar `var-servicio` selecciona el servicio, `&kiosk` oculta el chrome de Grafana para el embebido. Ver `docs/grafana/03-dashboards-existentes.md`.

**Verificado en vivo, no solo desplegado**: las queries reales (CPU/reinicios/logs) probadas contra Prometheus/Loki con un valor de Swarm (`infisical`, 2 contenedores, datos coherentes) y uno de Compose clásico (`watchtower`, 2 instancias en nodos distintos) antes de dar el panel por bueno; confirmado el aprovisionamiento en el propio Grafana vía su métrica interna `grafana_stat_totals_dashboard` (6→7 tras el despliegue, sin necesitar credenciales para comprobarlo).

**Lista de servicios de la variable, mantenimiento manual**: al ser una variable `custom` con lista fija (no derivada en vivo de una única fuente, precisamente porque no existe un único label que las una), un servicio nuevo no aparece solo — hay que añadirlo a mano en el JSON. Aceptado a propósito por ser el coste más bajo de las alternativas evaluadas (ver decisión de arriba); revisar esta lista la próxima vez que se añada un stack de Swarm o un servicio de Compose clásico nuevo.

### Segunda pasada (2026-09-03) — `qdrant` y `apikey-service`

**`pi-obs/config/grafana/dashboards/json/apikey-service.json`** (uid `homelab-apikey-service`) — construido íntegramente con datos reales verificados en vivo: la auditoría OTLP de validaciones fallidas (Loki, `service_name="apikey-service"`, cuerpo JSON estructurado con `body`/`attributes.source_ip`/`code.file.path`...) da paneles de tasa de fallos, motivo del fallo y top de IPs de origen, más CPU/memoria del contenedor. **Hallazgo real, corrige la documentación previa**: `docs/01-topologia.md` decía que `apikey-service` manda "trazas y registros" por OTLP — comprobado en vivo que Tempo no tiene ningún trace almacenado (`/api/search/tags` devuelve `{}` vacío) pese a la variable de entorno/config existir; el dashboard se queda con lo que sí hay (logs), sin un panel de trazas que estaría vacío. La IP de origen capturada es el peer TCP inmediato (red overlay de Traefik, `10.0.4.x`), no la IP real del cliente externo — anotado como limitación en el propio panel, no una atribución fiable de origen.

**`pi-obs/config/grafana/dashboards/json/qdrant.json`** (uid `homelab-qdrant`) — CPU/memoria/red/logs con datos reales (constraint fijo a `retaco`), más las métricas nativas de Qdrant, completadas tras crear el secret (usuario, 2026-09-03, con la **API key de solo lectura** de Qdrant, no la de escritura — decisión acertada, principio de mínimo privilegio para un scrape de métricas). `job_name: qdrant-retaco` en `pi-obs/config/prometheus.yml` scrapeando `http://192.168.1.174:6333/metrics` con `authorization.credentials_file` contra el secret `qdrant-metrics-token-v1` (Qdrant acepta la key como `Authorization: Bearer <key>`, no solo como su header propietario `api-key`) — confirmado `health: up` en Prometheus tras el redespliegue de `pi-obs`. Nombres de métrica reales verificados en vivo antes de construir ningún panel (36 métricas expuestas en total): `collections_total`, `collection_points`/`collection_vectors` (colecciones reales del clúster: `articles` con 23 puntos, `transcripts` vacía — labels inconsistentes entre sí, ojo: una usa `id`, la otra `collection`, unificadas en el dashboard con una transformación de renombrado antes del `join`), `memory_resident_bytes` (memoria real del proceso, distinta de la del cgroup que ya daba cAdvisor — ambas en el mismo panel a propósito, por si divergen), `collection_update_queue_length`, `app_info` (versión, `1.19.0`). **Esta versión de Qdrant no expone latencia de búsqueda ni contador de peticiones** — no hay métrica de ese tipo en la lista real, así que no hay panel de latencia (no inventado sin dato que lo respalde).

**Verificación de aprovisionamiento, nota metodológica**: la métrica interna `grafana_stat_totals_dashboard` (usada para confirmar la primera pasada) resultó **no fiable en tiempo real** — tras un reinicio limpio de Grafana seguía en `0` pese a que el log de arranque (`logger=provisioning.dashboard msg="finished to provision dashboards"`, sin errores) confirmaba los 4 dashboards cargados correctamente. La verificación real y fiable es ese log de arranque (`docker service update --force pi-obs_grafana` + consultar Loki), no esa métrica — anotado por si se vuelve a necesitar confirmar un aprovisionamiento sin acceso a la UI.

### Cierre

Con `qdrant`/`apikey-service` entregados, métricas nativas de Qdrant incluidas, y sin más candidatos claros con métricas de aplicación propias identificados en esta pasada, la mejora se da por **cerrada** sin pasos pendientes.

### Qué hay hoy (histórico, previo a la implementación)

Grafana (`pi-obs`) está desplegado y funcionando, con datasources reales conectados (Prometheus, Loki, Tempo) — pero el aprovisionamiento de dashboards (`pi-obs/config/grafana/dashboards/json/`) solo tiene **un** dashboard propio: `actualizaciones-pendientes.json` (la alerta de baja tensión/actualizaciones pendientes, `docs/14-monitorizacion-completa-cluster.md`). Para el resto de los ~30 servicios del clúster, la única forma de ver sus métricas es explorar a mano en Grafana (Explore) o mirar directamente Prometheus/Loki — nada guardado, nada compartible, nada que sobreviva a "¿qué le pasaba a X la semana pasada?".

Lo que ya existe como fuente de datos real, sin dashboard que lo aproveche:
- **Infraestructura de nodo** (todos los servicios, indirectamente): `node-exporter` + `cadvisor` en los 6 nodos — CPU/RAM/disco/red por contenedor y por host, ya en Prometheus.
- **Logs** (todos los servicios): todo el `stdout`/`stderr` ya llega a Loki vía el driver `loki` de cada `docker-compose.yml` — consultable, pero sin ningún panel ya armado.
- **Métricas de aplicación real** (más allá de host/contenedor): hoy solo `apikey-service` manda algo por OTLP (`docs/01`, sección de telemetría) — para el resto, un dashboard "por servicio" en la práctica sería sobre todo CPU/RAM/red del contenedor + volumen de logs/errores, no métricas de negocio propias (no hay `/metrics` de Prometheus expuesto por la mayoría de las apps).
- `postgres-exporter` (`pi-obs`) ya expone métricas reales de `postgres-main` sin ningún dashboard que las muestre tampoco.

### Qué haría falta

1. Decidir el criterio de "un dashboard por servicio" — probablemente no 1:1 literal (30 dashboards casi idénticos, solo cambiando el nombre del contenedor, no aportaría mucho) sino por grupos con sentido: uno por **stack** de Swarm (`docker-swarm/stacks/<nombre>/`), con paneles de CPU/RAM/red (cadvisor, filtrado por `com.docker.swarm.service.name`), tasa de reinicios/estado de la tarea, y un panel de logs (Loki) filtrado a ese `swarm_service` — reutilizable como plantilla para los ~25 stacks.
2. Un dashboard aparte, más detallado, para los servicios que ya exponen métricas reales propias: `postgres-main` (vía `postgres-exporter`), y cualquier otro que las tenga o las gane más adelante (revisar si Qdrant/SonarQube/Authentik exponen `/metrics` de Prometheus nativo antes de asumir que no).
3. Uno específico para `apikey-service`, el único que ya manda trazas/logs por OTLP — aprovechar eso en vez de tratarlo igual que el resto.
4. Provisionarlos como código (`pi-obs/config/grafana/dashboards/json/*.json`, igual que `actualizaciones-pendientes.json`), no crearlos a mano en la UI y olvidarlos — mismo criterio que el resto del repo (todo versionado, nada solo-en-producción).
5. Revisar si compensa una plantilla Grafana con variable `$servicio` (un dashboard parametrizable que sirve para cualquier stack eligiendo de un desplegable) en vez de un JSON por servicio — menos ficheros que mantener, aunque algo menos flexible para paneles específicos de un servicio concreto.

### Esfuerzo estimado
Medio — el trabajo mecánico (plantilla + paneles cadvisor/Loki reutilizables) es bajo una vez decidido el criterio del punto 1; el esfuerzo real está en decidir cuántos dashboards de verdad hacen falta y para cuáles servicios merece la pena un dashboard a medida (los que exponen métricas propias) frente a la plantilla genérica.

---

## 46. Verificar si `toggle-direct-access.sh` cierra de verdad el acceso directo en los 5 managers, no solo en el nodo "asignado"

**Prioridad: media** (afecta a un mecanismo de seguridad real, pero nadie ha activado `off` en producción todavía — no es una vulnerabilidad explotada, es una duda sin verificar)

### Qué hay hoy

`shared/scripts/toggle-direct-access.sh` gestiona el acceso directo por IP:puerto agrupando los puertos **por nodo** (`NODE_PORTS`) y aplicando reglas `DOCKER-USER` en ese nodo concreto. Este diseño asumía que un puerto publicado con `mode: host` solo está realmente escuchando en el nodo donde aterriza la tarea — cierto cuando se escribió.

Tras la revisión de `constraints`/`mode: host` → `ingress` del 2026-08-31 (mejora 43 y esta misma sesión), **ya no queda ningún servicio del clúster en `mode: host`** — confirmado por `grep` en los 25 stacks, todos son `mode: ingress`. Con `mode: ingress`, Swarm publica el puerto en la routing mesh de **los 5 managers**, no solo en el nodo real de la tarea — confirmado en vivo el mismo día: `portainer`/`vaultwarden` (movidos a `pinchi`) siguen respondiendo `200` real al consultarlos por la IP de `pi-utils`, donde ya no viven.

Esto es justo lo que hace útil a `mode: ingress` para servicios sin nodo fijo — pero para `toggle-direct-access.sh`, que existe para **cerrar** el acceso directo, es potencialmente el problema contrario: si `DOCKER-USER` en `pi-utils` bloquea el puerto de `vaultwarden`, pero la routing mesh de `pinchi` (o de cualquier otro manager) sigue respondiendo a ese mismo puerto sin la regla de bloqueo, el "cierre" sería parcial — cualquiera en la LAN podría seguir alcanzando el servicio directamente por la IP de un manager sin la regla, saltándose Traefik/`apikey-service` igualmente.

### Qué haría falta

1. Confirmar en vivo (con un servicio de bajo riesgo, no `vaultwarden`) si `docker service update --publish-add`/la routing mesh respeta las reglas `DOCKER-USER` de un nodo que NO ejecuta la tarea real, o si las bypasa a nivel de kernel (IPVS) antes de llegar a esa cadena.
2. Si el bypass es real: decidir si `toggle-direct-access.sh` necesita aplicar la regla de cada puerto en **los 5 managers simultáneamente** en vez de agruparlos por nodo (cambio de diseño real, no cosmético) — probablemente simplifica el script (una sola lista de puertos, sin `NODE_PORTS` por nodo) a la vez que lo hace correcto.
3. Si el bypass NO es real (`DOCKER-USER` sí intercepta el tráfico de la routing mesh en cualquier nodo): documentarlo explícitamente como comprobado, y la agrupación actual por nodo sigue siendo válida tal cual, solo hace falta mantenerla al día conforme los servicios cambien de nodo (ya corregido puntualmente el 2026-08-31 para `pinchi`).
4. Revisar `docs/17-firewall-acceso-directo.md` con el resultado real, sea cual sea.

### Esfuerzo estimado
Bajo para comprobarlo (una prueba controlada con `curl` desde fuera de la LAN de confianza, o simulando con un origen no permitido, contra un servicio de bajo riesgo) — medio si hace falta rediseñar el script para aplicar reglas en los 5 nodos a la vez.

---

## 47. ~~Volúmenes Docker `type: nfs` en vez de montaje NFS manual por nodo~~ — hecho para los tres candidatos iniciales

**Prioridad: baja** — **completado para los tres candidatos** (2026-09-03)

### Qué se implementó

Los tres candidatos identificados (`pdf2chunks-service`, `epub2pdf-service`, `registry`) migrados de bind-mount contra `/mnt/nfs-data/...` (montaje OS-level manual en `/etc/fstab`) a volúmenes Docker nativos (`driver: local`, `driver_opts: {type: nfs, o: "addr=192.168.1.180,rw,vers=3", device: ":/volume1/nfs-data/<servicio>/<subruta>"}`) — **mismo dato real en el NAS, sin mover ni un byte** (los 32G de `registry` incluidos): el cambio es solo en cómo cada nodo monta el export, ya no depende de que alguien haya preparado `/etc/fstab` a mano de antemano. `vers=3` obligatorio en los tres (NFSv4 sigue roto en este NAS, `docs/21-configuracion-nas-ugreen.md`).

**Orden real de ejecución, de menor a mayor riesgo** (decisión del usuario): primero `pdf2chunks-service` como piloto (datos casi vacíos, reconvertibles) para validar el mecanismo, luego `epub2pdf-service` con el mismo patrón ya probado, y solo al final `registry` (32G de imágenes reales, sin sustituto trivial). **Sin backup adicional** antes de la prueba — decisión explícita del usuario, confiando en el RAID 1 + SAI del propio NAS en vez de un `tar` aparte (`shared/scripts/backup-registry.sh` sigue preparado y sin ejecutar, disponible si se quiere retomar más adelante).

**Verificación real de portabilidad, no solo "el servicio arrancó"**: con `pdf2chunks-service` corriendo en `retaco`, se escribió un fichero de prueba real en el volumen de salida, se forzó la reprogramación a `pinchi` (`docker node update --availability drain retaco` + constraint temporal), y se confirmó que el mismo fichero era visible desde el otro nodo sin ninguna preparación previa en él — la prueba de que el mecanismo es de verdad independiente del montaje OS-level. Con `registry`, la prueba llegó sola: Swarm lo programó en `pi-utils` (un nodo ARM) sin que nadie lo pidiera, sirviendo los 31G reales por NFS sin incidentes, más un `docker push` real de una etiqueta de prueba (`mejora47-test`, capas compartidas con una imagen ya existente — sin coste de espacio, pendiente de limpiar con `shared/scripts/registry-garbage-collect.sh` en el próximo mantenimiento).

**Hallazgo real, no relacionado con NFS**: `epub2pdf-service`/`pdf2chunks-service` usan imágenes **solo amd64** (`docker manifest inspect`, un único platform) — sin ninguna constraint de arquitectura, Swarm intentaba programarlas en los 3 nodos Raspberry Pi (arm64) y fallaba en bucle con "no matching manifest for linux/arm64/v8". Esto llevaba oculto desde el 31/08 (el `constraints: node.hostname==retaco` original lo resolvía de casualidad, no a propósito) y solo se hizo visible al forzar la reprogramación durante esta prueba. Añadida `node.platform.arch == x86_64` a ambos — **ojo con el valor exacto**: la imagen se etiqueta "amd64" (convención OCI), pero `docker node inspect` devuelve "x86_64" para ese mismo dato — son dos vocabularios distintos, confirmado en vivo (`docker service update` rechazó los 5 nodos con "scheduling constraints not satisfied" hasta corregir el valor). `registry` no necesitó esta constraint — su imagen oficial (`registry:2.8.3`) sí es multi-arch.

**Efecto colateral real durante la prueba, no causado por este cambio**: al forzar la reprogramación de `pdf2chunks-service`, `retaco` no pudo tirar de la imagen (`docker pull` fallando con "no such host" contra `127.0.0.53`, el stub de `systemd-resolved`) — resultó ser el gotcha ya documentado en `docs/13-troubleshooting.md` ("un cliente Linux no resuelve aunque pi-dns ya está sano de nuevo": `systemd-resolved` se había quedado pegado a `1.1.1.1` en vez de Pi-hole tras algún fallo transitorio anterior, y no reintenta el primario solo). Resuelto con el fix ya documentado (`sudo systemctl restart systemd-resolved`) — sin sorpresas, la documentación existente ya lo cubría exactamente.

El montaje OS-level en `/etc/fstab` de los 5 managers **no se ha retirado** — sigue siendo el mecanismo real para cualquier servicio que no haya migrado todavía a volumen nativo.

### Segunda pasada (2026-09-03) — el resto de servicios sin base de datos "de verdad" en NFS

Ampliada a los 7 servicios restantes que bind-montaban algo bajo `/mnt/nfs-data/` sin ser `postgres-main`/`qdrant`: `authentik` (`data`/`certs`), `capataz` (`api-alembic`, solo lectura), `n8n-main` (`data`), `n8n-aux` (`data`), `open-terminal-mcp` (`home`), `open-webui` (`data`) y `sonarqube` (solo `extensions/` — `data/` de Elasticsearch y su `constraints: node.hostname==pi-sonar` **no se tocan**, siguen fuera de alcance por el mismo motivo que `postgres-main`/`qdrant`, ver mejora 44). Mismo patrón exacto que la primera pasada, mismo `vers=3` obligatorio, sin mover ni un byte de dato real.

**Hallazgo real antes de tocar nada**: dos de los siete (`n8n-aux`, `open-webui`) tienen una base de datos SQLite embebida de verdad bajo ese bind-mount (`database.sqlite`+`-wal`+`-shm` en ambos, más `vector_db/chroma.sqlite3` en `open-webui`) — la misma categoría de riesgo de escritura de un solo proceso que llevó a excluir `postgres-main`/`qdrant` de la primera pasada. Verificado antes de decidir: **`n8n-aux` tiene ese SQLite con escritura activa** (WAL de 8,8M, ya documentado y aceptado explícitamente por el usuario al quitarle el `constraints` el 31/08, "asumiendo el riesgo con conocimiento de causa"); **`open-webui`** tiene los mismos ficheros pero confirmados residuales (sin tocar desde julio/agosto, la BD real vive en `postgres-main`+`qdrant` desde antes). En ambos casos, **el cambio de mecanismo (bind-mount OS-level → volumen Docker nativo) no altera el riesgo ya existente ni lo introduce de nuevo** — el SQLite ya corría sobre este mismo NFS antes del cambio, sigue corriendo sobre el mismo NFS después; lo único que cambia es si el nodo necesita `/etc/fstab` preparado a mano de antemano. Migrados ambos, sin backup adicional (mismo criterio ya aplicado en la primera pasada), verificados con datos reales: tras el redespliegue de `n8n-aux`, el `database.sqlite` (1,9M) y su `-wal` (8,8M reciente) siguen presentes y consistentes, servicio respondiendo con normalidad.

`n8n-main` confirmado vestigial de antes (`DB_TYPE: postgresdb`, el directorio local nunca tuvo el estado real) — sin riesgo. El resto (`authentik`, `capataz`, `open-terminal-mcp`, `sonarqube/extensions`) son ficheros/config sin patrón de escritura concurrente real, mismo criterio que `registry`/`epub2pdf-service`/`pdf2chunks-service` de la primera pasada.

**Detalles técnicos preservados sin cambios de comportamiento**: el `tmpfs` de `open-webui` superpuesto en `/app/backend/data/cache` (encima del volumen NFS, para no persistir el modelo de embeddings de HuggingFace en el NAS) sigue montándose exactamente igual — confirmado con `docker exec ... mount` mostrando `nfs` en `/app/backend/data` y `tmpfs` en `/app/backend/data/cache` por separado. `capataz-api` sigue con `user: "1000:10"` y el volumen montado `:ro` — la ACL de UGOS (solo UID 1000/gid 10 escriben) no depende del mecanismo de montaje, y `alembic upgrade head` corrió sin problema contra el volumen nuevo. `authentik-data` se comparte entre `authentik-server` y `authentik-worker` (dos servicios del mismo stack apuntando al mismo volumen) sin ningún problema.

Verificado en vivo, no solo desplegado: los 10 servicios migrados hasta ahora (3 de la primera pasada + 7 de esta) responden con el código HTTP esperado, `docker node ls` con los 5 managers `Ready` y `docker service ls` sin ninguna réplica incompleta tras el barrido completo.

### Qué hay hoy (histórico, previo a la implementación)

La mejora 43 (cerrada 2026-08-31) auditó todos los bind-mounts del clúster y confirmó que **ningún stack de Swarm usa un volumen Docker gestionado** (`driver: local` o cualquier otro) — el 100% del estado real se sirve con bind-mounts de host. Para los tres servicios que ya usan almacenamiento respaldado por NFS (`registry`, `epub2pdf-service`, `pdf2chunks-service`), el mecanismo real es un montaje NFS a nivel de sistema operativo configurado a mano en el nodo (hoy solo en `retaco`) más un bind-mount de un subdirectorio de ese montaje — no un volumen Docker con `driver_opts: type=nfs`. Es la razón real por la que esos tres siguen con `constraints: node.hostname==retaco`: no por bloqueo de datos (el dato ya vive en el NAS, fuera de cualquier disco local), sino porque solo `retaco` tiene el montaje NFS preparado a mano.

Docker soporta de forma nativa (desde 17.06, sin plugin externo) declarar un volumen con `driver: local` y `driver_opts: type: nfs`, que logra el mismo resultado pero gestionado por el propio daemon de cada nodo: monta el export la primera vez que una tarea con ese volumen aterriza ahí, de forma perezosa y por nodo, sin necesidad de configurar nada a mano de antemano en cada uno de los 5 managers.

### Qué queda abierto

Los tres candidatos claros (`registry`, `epub2pdf-service`, `pdf2chunks-service`) están migrados y verificados — ver "Qué se implementó" arriba, con el patrón real (`driver_opts` exactos, comprobaciones hechas) que sirve de referencia para cualquier candidato adicional que se evalúe en el futuro. **`postgres-main`/`qdrant` siguen explícitamente fuera** de esta mejora, sin cambios: son bases de datos de un solo escritor donde permitir que floten libremente introduce un riesgo que hoy NO existe (al estar pinnadas, es estructuralmente imposible que dos instancias escriban a la vez) — si Swarm reprograma la tarea por un fallo de heartbeat mientras el nodo viejo sigue realmente vivo (una partición de red, no un apagado real), NFS no impide por sí solo que ambas instancias escriban a la vez sobre los mismos ficheros. Sin resolver antes un mecanismo de *fencing*, no se tocan. Evaluar cualquier otro servicio con estado nuevo caso por caso, nunca como una migración automática en bloque.

### Esfuerzo estimado
Bajo, confirmado con los tres candidatos iniciales — el mecanismo funcionó a la primera vez identificado el detalle real del valor de la constraint de arquitectura. Evaluar un servicio adicional en el futuro (fuera de `postgres-main`/`qdrant`) mantiene el esfuerzo bajo — la parte cara sigue siendo decidir si su patrón de escritura lo hace seguro, no la mecánica del volumen en sí.

---

## 48. Cockpit + libvirt en `ryzen` — gestión de máquinas virtuales, arranque/parada por Ansible

**Prioridad: baja-media**

### Qué hay hoy

No existe ninguna infraestructura de máquinas virtuales en el clúster — todo es Docker (Swarm o Compose clásico). `ryzen`/`mole` es el único candidato real como host: es la máquina con más recursos (62 GiB RAM, 24 núcleos, dos GPUs, `docs/07-instalacion-ryzen.md`), la única con arquitectura x86_64 completa, y ya queda deliberadamente fuera del Swarm (mejora 37, cerrada) como nodo Compose independiente. Tiene acceso SSH ya activo, pero con alcance estrecho: `openssh-server` se instaló específicamente para que `pi-obs` pudiera ejecutar `check-image-updates.sh` por SSH con una clave dedicada (`pi-obs-cluster-admin`, `docs/16-mantenimiento-actualizaciones.md`), no como acceso administrativo general. `ryzen` es además el único nodo que se apaga cuando no se usa, con Wake-on-LAN ya operativo (`shared/scripts/wake-mole.sh`, `docs/19-wake-on-lan.md`).

### Qué se busca

1. **Cockpit**, con el módulo `cockpit-machines`, instalado en `ryzen` y desplegado de forma remota (sin necesidad de acceso físico a la máquina) — panel web para gestionar las VMs.
2. **Acceso SSH a `ryzen`** más allá del uso puntual ya existente, para poder gestionar las máquinas virtuales de forma remota (CLI/`virsh`, o como paso previo a la automatización con Ansible).
3. **Arranque y parada de máquinas virtuales mediante Ansible.**
4. **`libvirt`** (`libvirtd` + `qemu-kvm` + `virsh`) como capa de gestión de las VMs — la pila estándar sobre la que trabaja también `cockpit-machines`.

### Qué haría falta

1. **Confirmar soporte de virtualización en `ryzen`** (VT-x/AMD-V activo en BIOS, `kvm-ok` o equivalente) — no verificado todavía; dato de partida obligatorio antes de instalar nada.
2. **Cockpit rompe el patrón habitual de este repo.** Todo lo demás se despliega como contenedor (Swarm o Compose); Cockpit, en cambio, se instala normalmente como paquete nativo del sistema (systemd, acceso directo a `libvirtd`, interfaces de red, dispositivos de bloque) — meterlo en un contenedor complica innecesariamente el acceso a esos recursos del host sin aportar nada. Documentar explícitamente esta excepción al criterio "todo containerizado" cuando se aborde.
3. **Decidir cómo se expone el panel de Cockpit** (puerto 9090, TLS propio): dado que da control total del host y de las VMs, el criterio de este clúster para superficies igual de sensibles ha sido Tailscale/LAN solamente, no público vía Traefik+`404labo.net` (mismo razonamiento ya aplicado a Pi-hole, mejora 41) — a confirmar, no asumir sin decidirlo explícitamente.
4. **Modelo de acceso SSH a `ryzen`.** Los otros 5 nodos siguen el patrón "un usuario dedicado sin privilegios compartidos por nodo" (`CLAUDE.md`, tabla de acceso SSH) — `ryzen` no tiene ese patrón hoy porque se usa normalmente en local. Decidir si el acceso remoto para VMs/Ansible reutiliza la clave estrecha ya existente (`pi-obs-cluster-admin`, hoy con un propósito muy distinto) o si hace falta un usuario/clave dedicados, siguiendo el mismo criterio de aislamiento que el resto del clúster.
5. **Red de las VMs**: bridge de red en el host (para que las VMs tengan IP real en la LAN) frente a NAT — si se opta por bridge, hace falta un plan de IPs coherente con `docs/02-plan-ip-y-dns.md` (IPs fijas ya asignadas a los 7 nodos existentes).
6. **Almacenamiento de los discos de VM**: local en `ryzen` es lo razonable por defecto (no hace falta que floten entre nodos, a diferencia de la discusión de la mejora 47) — confirmar espacio disponible antes de comprometerse.
7. **Arranque/parada por Ansible depende de la mejora 6** (migración del tooling a Ansible, no iniciada) — o, alternativamente, se podría escribir un playbook autocontenido solo para el ciclo de vida de las VMs sin esperar a la migración completa; a decidir cuál de las dos rutas compensa más cuando se aborde.
8. **`ryzen` se apaga cuando no se usa** (único nodo así, `docs/19-wake-on-lan.md`) — cualquier automatización de arranque/parada de VMs por Ansible necesita contemplar que el host puede estar dormido, y encadenar `wake-mole.sh` como paso previo si hace falta.
9. **Copias de seguridad**: los discos de VM son estado nuevo que respaldar, mismo criterio que el resto de servicios con estado (mejora 1) — no asumir que quedan cubiertos por algo ya existente.
10. **Fuera de alcance por ahora, anotado por si aparece más adelante**: `ryzen` ya reparte sus dos GPUs entre pares de servicios Docker que nunca deben coincidir (`switch-llm-backend.sh`/`switch-gpu1-backend.sh`, `docs/07`) — si en algún momento se quisiera pasar una GPU completa a una VM (passthrough), chocaría con ese esquema de alternancia y necesitaría diseñarse aparte; no forma parte de esta mejora tal como se ha pedido.

### Esfuerzo estimado
Medio-alto — la instalación de Cockpit/libvirt en sí es mecánica, pero hay varias decisiones reales de arquitectura antes (exposición del panel, modelo de acceso SSH, red de las VMs) y una dependencia parcial de la mejora 6 (Ansible) para la parte de automatización.

---

## 49. k3s en `ryzen`, sobre máquinas virtuales — clúster Kubernetes aislado para aprendizaje/experimentación

**Prioridad: baja**

### Qué hay hoy

`CLAUDE.md` fija como decisión de arquitectura explícita de todo este repo: el clúster está orquestado con **Docker Swarm, "explícitamente no Kubernetes"** (mejora 33/39, cerrada 2026-08-27). Esta mejora **no es una reconsideración de esa decisión** — el propio planteamiento del usuario ("usar las máquinas virtuales como nodos separados") lo deja claro: un clúster k3s aislado, corriendo dentro de VMs en `ryzen`, sin tocar ni sustituir ningún stack real de `docker-swarm/stacks/`. Vale la pena dejarlo dicho explícitamente aquí para que no se confunda con una migración cuando se retome: es un entorno paralelo de aprendizaje/experimentación, no una alternativa de producción.

### Dependencia dura con la mejora 48

"Usar las máquinas virtuales como nodos separados" exige que exista la infraestructura de VMs primero — **esta mejora no puede empezar antes de que la mejora 48 (Cockpit + libvirt en `ryzen`) esté al menos parcialmente resuelta.** No tiene sentido secuenciarla antes.

### Qué haría falta

1. **Número de nodos y reparto de recursos**: k3s admite 1 server + N agents — incluso un clúster mínimo de 3 nodos (1 server + 2 agents) ya permite practicar escenarios multi-nodo reales. Cada VM compite por la misma RAM/CPU de `ryzen` (62 GiB / 24 núcleos, mejora 30) que ya reparten los servicios Docker existentes (Ollama/vLLM/whisper/ComfyUI) — dimensionar dejando margen real, no solo lo que sobre en el momento de medir.
2. **Red aislada de las VMs** (mismo punto abierto que la mejora 48, punto 5): decidir si los nodos k3s llevan IP real de LAN (bridge) o quedan en una red NAT interna sin salir a la LAN salvo lo estrictamente necesario — para un entorno de aprendizaje, NAT interno es probablemente suficiente y evita ocupar IPs fijas del plan existente (`docs/02-plan-ip-y-dns.md`).
3. **Aislamiento del resto del clúster real**: mismo criterio que ya separa "Compose clásico" de "Swarm" en este repo (`CLAUDE.md`, sección de arquitectura — sin red Docker compartida entre los dos mundos, todo por LAN real si hace falta) — este tercer mundo (k3s) debería quedar igual de aislado, sin compartir red con `docker-swarm/stacks/` ni con las redes bridge de los nodos Compose.
4. **Registry privado ya reutilizable tal cual**: `registry.404labo.net` no es específico de Docker Swarm — cualquier `containerd` (el runtime de k3s) puede tirar de ahí sin montar un registro nuevo. Ojo con el mismo tipo de problema ya visto dos veces en este repo (`docs/31-docker-swarm.md`, incidente de CAs): si la imagen base de los nodos k3s no trae el almacén de CAs del sistema con el certificado de `404labo.net` ya confiado, el pull fallará con el mismo `x509: certificate signed by unknown authority` — comprobarlo desde el principio en vez de redescubrirlo.
5. **Aprovisionamiento**: instalación estándar vía `curl -sfL https://get.k3s.io | sh -` en el server y `K3S_URL`/`K3S_TOKEN` en los agents — encaja de forma natural como playbook de Ansible (sinergia real con la mejora 6 y con el punto 7 de la mejora 48, aunque ninguna de las dos esté hecha todavía) en vez de aprovisionar cada VM a mano.
6. **GPU, fuera de alcance salvo que se pida explícitamente**: mismo punto abierto que la mejora 48 (punto 10) — si algún día un workload de k3s quisiera GPU, haría falta *passthrough* real de una de las dos GPUs de `ryzen`, hoy repartidas entre servicios Docker vía `switch-llm-backend.sh`/`switch-gpu1-backend.sh`. No asumir disponibilidad sin diseñarlo aparte.
7. **Alcance real a decidir cuando se retome**: ¿es un entorno permanente (encendido junto con `ryzen`) o efímero (se crea/destruye para practicar y no vive entre sesiones)? Cambia bastante el diseño de almacenamiento (el `local-path-provisioner` por defecto de k3s no sobrevive a borrar la VM) y si merece la pena automatizar el ciclo de vida completo con Ansible o basta con un procedimiento manual documentado.

### Esfuerzo estimado
Medio-alto, y no antes de la mejora 48 — la instalación de k3s en sí es rápida una vez hay VMs disponibles; lo que lleva tiempo es decidir el alcance real (permanente vs. efímero) y el aislamiento de red respecto al clúster de producción.

---

## 50. Cudy R700 como router principal — gateway, DHCP, firewall y NAT del homelab

**Prioridad: baja**

### Qué se busca

Sustituir el router del ISP como gateway/DHCP/firewall/NAT de la LAN del homelab por un router Cudy R700, dejando el router de fibra como WAN1 y, opcionalmente, un router 5G con salida Ethernet como WAN2 de respaldo (failover, no balanceo). Guía completa ya escrita — cableado propuesto, direccionamiento, configuración paso a paso del Cudy y del router ISP, failover fibra↔5G con detección real de caída (no solo del enlace local), automatización (firmware Cudy de fábrica vs. migrar a OpenWrt oficial, soportado desde 24.10.5 para este modelo), y el problema de dejar el WiFi del router ISP en una red aguas arriba del Cudy con acceso hacia la LAN protegida: `docs/cudy.R700.router.md`. No se repite aquí — esta entrada solo engancha el trabajo al backlog y señala las decisiones que tocan específicamente a este repo, que la guía (escrita en genérico, sin conocer el clúster) no cubre.

### Choque real con el direccionamiento actual del clúster — decisión pendiente antes de empezar

La guía propone la LAN del Cudy en `192.168.10.0/24`, distinta de la `192.168.1.0/24` actual, con el router del ISP haciendo de intermediario (`WAN1` del Cudy en `192.168.1.2`) — arquitectura limpia en general, pero **hoy todo este repo asume `192.168.1.0/24` como la única LAN del clúster**: las IPs fijas de los 7 nodos están hardcodeadas en `CLAUDE.md`, `docs/02-plan-ip-y-dns.md`, `shared/dns/dns-records.md`, las rutas estáticas de Traefik (`docker-swarm/stacks/traefik/dynamic/routes.yml`) y los targets de Prometheus. Adoptar `192.168.10.0/24` tal cual la guía significaría renumerar el clúster entero (7 nodos + NAS), no solo reconfigurar un router — coste y riesgo muy por encima de lo que pide esta mejora. **Alternativa más simple, a valorar primero**: quedarse con `192.168.1.0/24` como LAN del propio Cudy (es decir, el Cudy pasa a ser `192.168.1.1` y sustituye al router del ISP como gateway/DHCP de esa misma red, en vez de crear una `192.168.10.0/24` nueva detrás de él) — así ningún nodo cambia de IP, ningún documento ni fichero de este repo necesita tocarse, y solo cambia *quién* hace de gateway/DHCP/firewall de la red que ya existe. Esto exige que el router del ISP pueda pasar a modo *bridge* puro (sin hacer NAT ni DHCP él mismo) para que el Cudy sea el único borde de la LAN — a confirmar contra el modelo real del router de fibra antes de comprometerse; si el ISP no permite bridge, esta opción no es viable y habría que reconsiderar entre el doble NAT con `192.168.10.0/24` de la guía o mantener el router ISP como está.

### Qué tocaría en este repo si se implementa

1. **`docs/02-plan-ip-y-dns.md`** — documentar el nuevo gateway (Cudy en vez del router ISP) y, si cambia de `192.168.1.1` a otra IP, actualizar la tabla de nodos.
2. **`shared/dns/dns-records.md`** — Pi-hole (`pi-dns`, `192.168.1.170`) sigue siendo la autoridad DNS de `404labo.net`; el Cudy solo debería servir DHCP, no DNS, para no duplicar responsabilidad (la guía lo deja como servidor DHCP **y** DNS local por defecto — en este clúster, apuntar el DNS que reparte el DHCP del Cudy a `192.168.1.170`, no dejar el propio Cudy como resolutor).
3. **Reservas DHCP de los 7 nodos** — recrearlas en el Cudy (por MAC) en vez de en el router ISP, para no perder las IPs fijas ya documentadas.
4. **Wake-on-LAN de `ryzen`** (`docs/19-wake-on-lan.md`, `shared/scripts/wake-mole.sh`) — verificar que el paquete mágico sigue llegando igual con el Cudy como gateway/firewall (broadcast dentro de la misma LAN, no debería cambiar, pero confirmarlo en vivo antes de dar el cambio por cerrado).
5. **`docs/17-firewall-acceso-directo.md`/`toggle-direct-access.sh`** — ese script gestiona la cadena `DOCKER-USER` en cada nodo, nivel completamente distinto del firewall del Cudy (borde de la LAN); no debería chocar, pero merece una revisión rápida tras el cambio de gateway.
6. Ningún servicio del clúster debería enterarse del cambio si se opta por la alternativa del punto anterior (mismo `192.168.1.0/24`, mismas IPs) — es precisamente lo que la hace preferible a la reconstrucción completa de direccionamiento que propone la guía en genérico.

### Esfuerzo estimado

Medio — la configuración del propio Cudy (WAN/LAN, DHCP, reglas de firewall, failover) es la parte bien documentada y acotada en la guía; el riesgo real está en el corte de conectividad de toda la LAN durante la migración (ventana de mantenimiento, no se puede hacer con el clúster en uso activo) y en confirmar si el router del ISP admite modo *bridge* antes de decidir entre las dos alternativas de direccionamiento de arriba. Sin dependencias de otras mejoras de este backlog.

---

## 51. Migrar las 4 Raspberry Pi de Ubuntu Server a Alpine Linux — reducir el consumo base del SO

**Prioridad: baja-media**

### Dictamen

**Factible, con matices reales que conviene conocer antes de comprometerse.** Afecta a los 4 nodos Raspberry Pi 5 del clúster — `pi-dns` (192.168.1.170), `pi-obs` (.171), `pi-sonar` (.172), `pi-utils` (.173) — no a `ryzen` ni `pinchi` (x86_64, fuera de alcance de esta mejora). El punto clave que hace esto viable en absoluto: **prácticamente todo lo que corre en estos 4 nodos ya está containerizado** (Docker Swarm stacks, más Pi-hole/Unbound/Tailscale en `pi-dns`, todos como contenedores según `pi-dns/docker-compose.yml`) — el libc del host (`glibc` en Ubuntu, `musl` en Alpine) es irrelevante para lo que corre *dentro* de un contenedor, porque cada imagen trae su propio userland. Cambiar el SO base no obliga a tocar ni un solo `docker-compose.yml` de servicio ni recompilar ninguna imagen — Pi-hole, Grafana, Loki, SonarQube, etc. seguirían siendo exactamente las mismas imágenes de siempre. Lo que sí cambia es todo lo **nativo del host**: cómo se instala/arranca Docker, el cortafuegos, la red estática, las actualizaciones del propio SO y el arranque del sistema (Alpine usa OpenRC, no systemd).

### Investigado (2026-09-15)

- **Soporte oficial de Alpine para Raspberry Pi 5**: confirmado, no es una incógnita. Alpine 3.19 (noviembre 2025, kernel 6.6 LTS) añadió soporte de RPi5; la rama estable actual (3.24.1, junio 2026) sigue publicando imágenes `aarch64` dedicadas para Raspberry Pi 3 a 5. Wiki oficial: `wiki.alpinelinux.org/wiki/Raspberry_Pi`.
- **Docker + Swarm sobre Alpine**: ampliamente usado en producción por terceros (Alpine es, de hecho, la base de muchas imágenes Docker oficiales) — el paquete `docker`/`docker-cli-compose` está en el repo `community`, con build `aarch64`. Un hallazgo real a evitar: un issue histórico de Moby (`moby/moby#31264`) documenta contenedores de Swarm muriendo en seco sobre un kernel Alpine con **grsec** habilitado — Alpine ofreció en el pasado sabores de kernel endurecidos con parches grsec que interactúan mal con las `capabilities` que Docker necesita. Mitigación directa: usar el kernel `linux-rpi` estándar (el que trae la imagen oficial de Raspberry Pi), no ningún sabor "hardened", y confirmarlo explícitamente en el piloto (fase 0 más abajo) antes de generalizar.
- **cgroups v2**: Alpine reciente los trae activados por defecto igual que Ubuntu 24.04+ — Docker moderno los soporta sin configuración especial. cAdvisor (ya desplegado, `docker-swarm/stacks/common/`) debería funcionar igual, pero no verificado en vivo sobre Alpine — punto a confirmar en el piloto.
- **La limitación ya conocida del driver `loki` nativo en arm64 no cambia con Alpine** (`CLAUDE.md`, comentario de `ryzen/docker-compose.observability.yml`: el plugin no tiene build para arm64, es un problema del binario del plugin, no del SO host) — los 4 Pi ya usan Promtail en su lugar; seguirá siendo así, sin relación con esta migración.
- **Qué es nativo del host hoy y necesitaría un equivalente en Alpine** (revisado contra `shared/scripts/` real de este repo, no genérico):
  - `install-docker-ubuntu.sh` — `apt-get`+`systemctl enable/start docker`. Alpine: `apk add docker docker-cli-compose` + `rc-update add docker default && rc-service docker start`.
  - `update-os.sh` — `apt-get update/upgrade/autoremove`. Alpine: `apk update && apk upgrade`.
  - `setup-unattended-upgrades.sh` — sin equivalente directo (`unattended-upgrades` es un paquete Debian/Ubuntu específico); Alpine necesitaría un cron/OpenRC propio ejecutando `apk upgrade` periódicamente, con su propia lógica de "qué se actualiza solo y qué no" (mismo criterio que hoy: nunca bases de datos/SonarQube en caliente sin ventana).
  - `check-os-updates.sh` (mejora 36, métrica de parcheo pendiente para Grafana) — usa `/var/run/reboot-required` (fichero específico de Ubuntu) y `apt list --upgradable`; necesitaría lógica nueva en Alpine (`apk list -u` para paquetes pendientes; "reboot required" no existe como concepto nativo, habría que aproximarlo comparando el kernel en ejecución contra el paquete `linux-rpi` instalado).
  - `setup-firewall.sh` — **buena noticia aquí**: ya NO usa `ufw` (se purga deliberadamente, ver comentario en el propio script — pisaba `iptables-persistent`) — ya trabaja directo con `iptables-persistent`. En Alpine el equivalente es el propio paquete `iptables` + su script de arranque OpenRC (`/etc/init.d/iptables save` vía `rc-service iptables save`), sin necesidad de purgar nada raro — probablemente el script que menos cambie de todos.
  - Red estática — `docs/03-instalacion-base-ubuntu-raspi.md` usa Netplan; Alpine no lo tiene, usa `/etc/network/interfaces` (`ifupdown-ng`) o `dhcpcd` — hay que rehacer esa parte de la guía de instalación, no solo el script.
  - Aprovisionamione inicial (cloud-init) — Raspberry Pi Imager sí lista Alpine Linux como SO oficial descargable para grabar la SD, pero el mecanismo de "primer arranque" (usuario, contraseña, SSH, IP) no es cloud-init sino el propio `answer file`/`setup-alpine` de Alpine — la guía `docs/03` necesitaría una sección paralela, no un simple `sed`.
  - `prepare-host.sh` — revisado, no usa `apt`/`systemctl`/Netplan directamente (solo `mkdir`/`chown`) — candidato a sobrevivir sin cambios, a confirmar en el piloto.
- **Ansible (mejora 6, todavía no iniciada)**: Alpine necesita `python3` instalado (no viene por defecto, a diferencia de Ubuntu Server) para que los módulos de Ansible funcionen — un paso más en el bootstrap, nada bloqueante.

### Ahorro esperado — expectativa realista, no vender humo

El ahorro real está en la **base del sistema operativo** (Alpine: unos 130-180 MB de imagen base frente a varios GB de una instalación Ubuntu Server con `snapd` y compañía) y en el **RAM ocioso** (sin `systemd` con sus decenas de unidades, sin journald indexando en background, sin `snapd`) — de manera realista, unos cientos de MB de RAM libres por nodo, no gigabytes, porque la carga real de cada Pi ya la marcan los contenedores en ejecución (Grafana, Loki, SonarQube...), que pesan lo mismo estén donde estén. El nodo donde más se notaría es `pi-sonar` (SonarQube es JVM, hambriento de RAM por diseño) — pero ahí el ahorro vendría de liberar margen para la JVM, no de que SonarQube en sí consuma menos. Vale la pena medir con datos reales de Prometheus/cAdvisor (mejora 38, tampoco iniciada) el RSS actual del SO en un nodo antes de prometer una cifra concreta.

### Riesgos a validar en el piloto antes de generalizar a los 4 nodos

1. Kernel `linux-rpi` estándar de Alpine 3.24.x, **no** ningún sabor hardened/grsec (ver hallazgo de Moby arriba).
2. Docker Swarm join/leave limpio, overlay networking real entre un nodo Alpine y los otros 4 nodos Ubuntu/x86_64 del swarm (clúster mixto durante toda la migración, nodo a nodo) — el propio protocolo Swarm es agnóstico del SO del host, pero no probado en este clúster concreto.
3. cAdvisor/node-exporter (mejora scraping de Prometheus) funcionando igual sobre cgroups v2 de Alpine.
4. WiFi/Bluetooth/firmware de la RPi5 — no se usa hoy en este clúster (todo por Ethernet), pero confirmar que el image `aarch64` de Alpine arranca limpio en el hardware real (BCM2712) sin necesitar firmware adicional para lo que sí importa: red Ethernet, USB, temperatura/throttling.
5. `docker plugin`/logging — confirmar que Promtail (ya en uso) sigue funcionando igual, sin sorpresas nuevas de permisos bajo Alpine.

### Plan de ejecución por fases

**Fase 0 — Piloto aislado, sin tocar el clúster real.** Grabar Alpine 3.24.x `aarch64` (imagen `rpi`) en una SD/nodo de pruebas (o, si no hay hardware de sobra, reservar una ventana para hacerlo directamente sobre `pi-utils` — ver fase 1, fusionando 0 y 1). Validar en aislamiento, sin unirlo aún al swarm real: Docker instalado y arrancando (`rc-service docker start` tras reboot), un contenedor de prueba con `docker run`, `iptables-persistent` real tras reboot, IP estática persistente, SSH con el usuario dedicado del nodo. Objetivo: descartar sorpresas de base antes de arriesgar un nodo productivo.

**Fase 1 — Migrar `pi-utils` (piloto real, primer nodo productivo).** Candidato explícitamente elegido como primero: es manager Swarm (confirma que Swarm-sobre-Alpine funciona de verdad en este clúster) pero sus servicios (RSSHub, markitdown-service, crawl4ai-scraper-service, n8n-aux, Vaultwarden, Capataz) son todos no críticos de forma individual y sin el riesgo de `pi-sonar` (mejora 44, todavía sin cerrar, no conviene sumarle una migración de SO encima) ni la criticidad de `pi-dns` (sin redundancia DNS todavía, mejora 40 pendiente). Pasos: `docker node update --availability drain` sobre `pi-utils` → drenar sus tareas Swarm a los otros managers → `docker swarm leave` → reinstalar con Alpine (red estática, Docker, firewall, `prepare-host.sh`) → `docker swarm join` con el token de manager → reasignar constraints/placement de sus stacks (`n8n-aux`, `rsshub`, `capataz`, etc., ver `docker-swarm/README.md`) → verificar réplicas `N/N` y los healthchecks de cada servicio. Dejarlo corriendo unos días antes de seguir, vigilando Grafana/Loki para cualquier anomalía nueva.

**Fase 2 — Migrar `pi-obs`.** Mismo procedimiento. Más delicado que `pi-utils` porque aloja el propio stack de observabilidad (Loki/Tempo/Prometheus/Grafana/otel-collector) — durante la ventana de migración el clúster queda temporalmente sin métricas/logs/alertas propios; avisar explícitamente de esa ventana antes de empezar, y comprobar que las alertas de Grafana (ntfy, mejora 4) vuelven a disparar con normalidad al terminar.

**Fase 3 — Migrar `pi-sonar`.** Solo después de cerrar (o descartar explícitamente) la mejora 44 (`sonarqube` colgándose con `infisical run` en `pinchi`) — no conviene mezclar una investigación de bug abierta con un cambio de SO en el mismo nodo. Prestar atención especial a memoria disponible para la JVM tras el cambio (ver "ahorro esperado" arriba).

**Fase 4 — Migrar `pi-dns`, el más delicado, el último a propósito.** No es manager Swarm, pero es la única resolución DNS de `*.404labo.net` de todo el clúster y el subnet router de Tailscale (`docs/18-tailscale.md`) — hoy sin redundancia (mejora 40, "DNS secundario del clúster", sigue sin implementar). **Recomendación fuerte: resolver la mejora 40 antes de tocar `pi-dns`**, o como mínimo tener un plan de contingencia explícito (entradas `/etc/hosts` temporales en los nodos críticos, aviso de ventana de mantenimiento con corte de acceso remoto vía Tailscale) para la duración de la reinstalación. Verificar en detalle antes de empezar: Pi-hole/Unbound (ya containerizados, deberían sobrevivir el cambio sin tocar su propio `docker-compose.yml`) y el contenedor `tailscale` (`network_mode: host`, necesita `/dev/net/tun` + módulos de kernel netfilter precargados en el host — confirmar que Alpine los trae/carga igual que Ubuntu, `CLAUDE.md` ya documenta esta dependencia con detalle).

**Fase 5 — Cerrar documentación.** Actualizar `docs/03-instalacion-base-ubuntu-raspi.md` (o crear un `docs/03b-instalacion-base-alpine-raspi.md` paralelo si conviene conservar ambos procedimientos, por ejemplo si algún nodo futuro sigue siendo Ubuntu), reescribir los scripts listados arriba (`install-docker-*.sh`, `update-os.sh`, `setup-unattended-upgrades.sh`, `check-os-updates.sh`, `setup-firewall.sh`) con rama o variante Alpine, y actualizar `CLAUDE.md`/`README.md` (la tabla de nodos ya no diría "Ubuntu Server 24.04 LTS" para los 4 Pi).

### Esfuerzo estimado

Medio-alto — no por dificultad técnica de cada paso individual (bien acotada, sin incógnitas grandes tras la investigación de esta ronda), sino por el número de nodos con roles distintos (2 managers Swarm "tranquilos", 1 con un bug abierto encima, y 1 crítico sin redundancia) y por tener que reescribir media docena de scripts operativos que hoy asumen Ubuntu/apt/systemd. Sin dependencia dura de ninguna otra mejora, pero **se beneficia mucho de la mejora 40 (DNS secundario) antes de la fase 4**, y de cerrar la mejora 44 antes de la fase 3.

---

## 52. Aplicar el procedimiento estándar de acceso SSH (`docs/38`) — usuario único `admin`, claves por nodo, script de conexión

**Prioridad: media**

### Qué hay ya

`docs/38-acceso-ssh-nodos.md` fija el procedimiento completo (instalación/configuración por SO — Ubuntu Server, Ubuntu Desktop, Alpine Linux —, endurecimiento de `sshd`, almacenamiento de claves en Infisical con respaldo en Vaultwarden, aplicable a SSH a pelo y a Ansible) — este es el trabajo real para aplicarlo, no descrito ahí a propósito, para no mezclar el "cómo debería ser" con el "qué falta hacer".

**Decisión explícita del usuario (2026-09-15), que cambia el modelo original de este documento**: en vez de un usuario distinto por nodo (`u-data`, `u-dns`...), un **único usuario `admin`, idéntico en los 7 nodos** — prioriza la predictibilidad (`ssh admin@<ip>` siempre, sin tabla que consultar) sobre la trazabilidad por nombre de cuenta. El aislamiento real entre nodos sigue viniendo de la clave SSH (distinta por nodo, sin cambios respecto al diseño original de `docs/38`), no del nombre de usuario.

### Qué falta

1. **Dar de alta `admin` en los 7 nodos, incluido `ryzen`** — hoy `ryzen` no tiene ningún usuario de administración dedicado (se opera como `linus`), y los otros 6 tienen usuarios antiguos con nombre distinto. Seguir `docs/38` sección 3.4: crear `admin` como cuenta **nueva** en cada nodo, verificar de punta a punta, y solo entonces retirar el usuario antiguo (`u-data`/`u-dns`/`u-obs`/`u-sonar`/`u-utils`/`u-forge`) — nunca al revés, para no perder acceso a ningún nodo a medio migrar.
2. **Una clave `ed25519` propia por nodo** (no la compartida de hoy) — auditado en vivo (`docs/38` sección 2): hoy una sola clave (`~/.ssh/id_ed25519` en `ryzen`) abre los 6 usuarios existentes. Con el cambio a `admin`, esto se resuelve de la misma pasada: cada nodo recibe su clave nueva junto con su cuenta `admin` nueva.
3. **Crear el proyecto `ssh-access` en Infisical** (carpeta `/ssh-access/<nodo>/` por nodo, secreto `PRIVATE_KEY`) y subir ahí cada clave nueva conforme se genera.
4. **Copia de respaldo en Vaultwarden** de cada clave, como vía de emergencia si Infisical (en `retaco`) no está disponible.
5. **Escribir `shared/scripts/ssh-node.sh`** — el envoltorio de los tres comandos sueltos descritos en `docs/38` sección 5.4 (`ssh-agent` + `infisical secrets get ... | ssh-add -` + `ssh admin@<ip>`), para que conectar a un nodo sea un solo comando; puede resolver `<nodo>` → IP internamente, así ni la IP hace falta recordar.
6. Actualizar `docs/01-topologia.md` (tabla de acceso SSH — usuario `admin` en los 7 nodos) y `shared/scripts/toggle-direct-access.sh` (mapa `NODE_SSH`) en cuanto la migración de cada nodo esté verificada, no antes.

### Esfuerzo estimado

Medio — sin incógnitas técnicas (todo ya validado conceptualmente contra mecanismos que este clúster ya usa, Infisical y Vaultwarden), pero son 7 nodos a dar de alta/migrar uno a uno sin cortar el acceso a ninguno mientras se hace (crear `admin` nuevo, verificar, solo entonces retirar la cuenta vieja donde exista — nunca al revés). Sin dependencias de otras mejoras.

---

## Resumen

| # | Mejora | Prioridad | Esfuerzo | Depende de |
|---|---|---|---|---|
| 1 | Automatizar las copias de seguridad y copiarlas fuera de nodo | Alta | Bajo–medio | — |
| 2 | ~~`git init` del repo + remoto~~ | Alta | — | **Completado** |
| 3 | ~~Alerta de espacio en disco~~ | Media | Bajo | **Completado** (2026-09-01) — `docs/14-monitorizacion-completa-cluster.md`; conectada a ntfy (mejora 4) |
| 4 | ~~ntfy (notificaciones proactivas)~~ | Media | Medio | **Completado** (2026-09-01) — `docs/34-ntfy-notificaciones.md`; stack Swarm desplegado y verificado en vivo, conectado como contact point de Grafana |
| 5 | ~~Integración NUT del SAI existente~~ | Media | Medio | **Completado** (2026-09-01) — `docs/33-nut-sai.md`; SAI conectado a `pi-obs` (no a `ryzen`), aviso proactivo ya conectado vía la mejora 4 (ntfy) |
| 6 | Migrar tooling de mantenimiento a Ansible | Media | Medio-alto | Punto 2 (ya cumplido) |
| 7 | Forgejo (repos + CI + artefactos), con GitHub como espejo | Media | Alto | Instalación núcleo hecha y verificada (2026-09-03, `docs/36-forgejo-repositorios-git.md`). Runners (7.3) desplegados y verificados en vivo (2026-09-04): `forgejo-runner-pinchi` (por defecto, siempre arriba) + `forgejo-runner-ryzen` (manual) — ambos Compose clásico, no Swarm (ver detalle en 7.3, límite real de Swarm con contenedores privilegiados) — pendiente: probar con un workflow real, SonarQube, cerrar `DISABLE_REGISTRATION`; migración de repos (7.2) sigue en rondas futuras |
| 8 | ~~Registry: limpieza y garbage collection~~ | Media | Bajo | **Implementado (uso manual)** — `docs/29-registry-mantenimiento.md`; alerta de disco cubierta por la mejora 3 (ya completada) |
| 9 | Tailscale: política de ACL | Baja | Bajo-medio | Tailscale ya desplegado (`docs/18`) |
| 10 | ~~NAS UGREEN: migrar `nfs-data` a NFSv4~~ — completada | Baja | — | Investigado en real: UGOS Pro revierte `/etc/exports` solo, sin tocar la GUI — inviable. NFSv3 definitivo (`docs/21`) |
| 11 | k6 para pruebas de carga automatizadas | Media | Bajo-medio | Prometheus/Grafana ya desplegados (`docs/08`) |
| 12 | RAG de libros en PDF desde Open WebUI | Media | Medio | `markitdown-service`, Qdrant y Ollama ya desplegados |
| 13 | Copiar logs/métricas de pi-obs al NAS | Media | Medio | NFS del NAS ya montado (`docs/21`) |
| 14 | Evaluar Floci como emulador local de AWS | Media | Bajo | — |
| 15 | ~~Panel de control de servicios + estado en `index.home.arpa`~~ | Media | — | **Completado** — `docs/28-capataz-consola-automatizacion.md`; Capataz sustituye la página estática, login real vía Authentik |
| 16 | ~~Sistema de secretos programático (Infisical)~~ | Media | — | **Completado** — `docs/26-infisical-secretos.md`; solo `apikey-service` migrado, resto en mejora 28 |
| 17 | ~~Open Terminal en modo MCP (Open WebUI + n8n)~~ | Media | — | **Completado** — `docs/24-open-terminal-mcp.md` |
| 18 | OpenClaw — asistente personal de IA autoalojado | Media | Medio | Ollama ya desplegado si se apunta a modelos locales |
| 19 | Opencode — agente de código open source para terminal | Media | Bajo | Ollama ya desplegado si se apunta a modelos locales |
| 20 | LiteLLM — proxy unificado hacia AWS Bedrock, conectado a Open WebUI | Media | Medio | Cuenta/IAM de AWS; Open WebUI ya desplegado; alternativa a mejora 21 |
| 21 | ~~Bifrost — gateway hacia AWS Bedrock, conectado a Open WebUI~~ | Media | — | **Completado** — `docs/23-bifrost-gateway-llm.md` |
| 22 | Coste de llamadas LLM (Bifrost) en Grafana, con vigilancia y alarmas | Media | Bajo-medio | Bifrost ya desplegado (`docs/23`, expone `bifrost_cost_total`); Prometheus/Grafana ya desplegados (`docs/08`); alerta conectable a ntfy (mejora 4, ya disponible) |
| 23 | ~~Mover `logs.db`/`config.db` de Bifrost a Postgres centralizado~~ | Media | — | **Completado** — `docs/23-bifrost-gateway-llm.md` |
| 24 | ~~Servidor Valkey (compatible Redis) securizado — key-value + pub/sub~~ | Media | — | **Completado** — `docs/25-valkey-cache.md` |
| 25 | ~~Authentik — authn/authz centralizado, piloto en Prometheus~~ | Media | — | **Completado** — `docs/27-authentik-sso.md`; solo Prometheus protegido, resto en mejora 29 |
| 26 | Investigar tool-calling fiable — modelos locales (Ollama) y Bedrock/Claude (Bifrost) | Media | Medio | Open Terminal MCP ya desplegado (mejora 17, `docs/24`); ningún modelo probado completa una llamada de herramienta hoy |
| 27 | Activar TLS en `postgres-main` | Media | Medio-alto | CA interna ya desplegada (`docs/15`); patrón ya probado con Valkey (mejora 24, `docs/25`) |
| 28 | ~~Migrar el resto de servicios del clúster a Infisical~~ | Media | — | **Completado (parcial)** — `docs/26-infisical-secretos.md`; 9 servicios migrados, `registry`/`postgres-exporter`/`whisper-service`/`vllm` quedan para más adelante |
| 29 | Integrar Authentik en el resto de paneles (OIDC nativo: Grafana, Portainer...) | Media | Medio | Authentik ya desplegado y patrón forward-auth validado (mejora 25, `docs/27`) |
| 30 | Entorno de notebooks en el clúster (code-server / JupyterLab) para estudios de datos | Baja-media | Bajo-medio | Postgres/Qdrant y NFS del NAS ya disponibles; Authentik (mejora 25) para protegerlo; solo compensa si hace falta ejecución que sobreviva a la sesión de escritorio |
| 31 | Nexus (u alternativa) como repositorio centralizado de paquetes, integrado con Forgejo | Baja | Medio | Forgejo (mejora 7) para la integración de CI; NFS del NAS ya disponible; experimento deliberado, no cubre carencia operativa hoy |
| 32 | ~~Dominio real + certificados Let's Encrypt (sustituye CA interna)~~ | Media | Medio-alto | **Completado** (2026-08-28, cierre mejora 41) — DNS-01 automatizado vía Route53/`dns_aws`, renovación por cron + rotación automática del secret de Traefik; CA interna reducida a un único consumidor (Valkey) |
| 33 | ~~Migrar el clúster a Docker Swarm, progresivamente~~ | Baja-media | Alto | **Completado** (2026-08-27) — `docs/31-docker-swarm.md`; `ryzen` (mejora 37) y `pi-dns` (mejora 39) quedan fuera del swarm |
| 34 | GitOps para las aplicaciones del clúster (propuestas a evaluar) | Media | Medio-alto | Depende de la propuesta elegida; sinergia con mejora 33 (ya completada) |
| 35 | ~~Sustituir `nginx` por Traefik, integrado con Docker Swarm~~ | Media | Alto | **Completado** (2026-08-28, cierre mejora 41) — `docker-swarm/stacks/traefik/`; `nginx` en `pi-dns` decomisionado del todo |
| 36 | ~~Vigilancia y alertas del estado de parcheo de los nodos (SO), y su continuación en Swarm~~ | Media | Bajo | **Completado** (2026-09-01) — `docs/16-mantenimiento-actualizaciones.md` sección 1.3; de paso, corregido un bug real de `mode: ingress` mezclando métricas entre nodos (`docs/31-docker-swarm.md`) |
| 37 | ~~`ryzen` (mole) fuera del clúster Swarm — operativa como nodo Compose independiente~~ | Baja-media | Bajo | **Completado** — decisión de alcance de la mejora 33, confirmada estable |
| 38 | Capacity planning con datos reales — `mem_limit`/`cpus` a partir de picos en Prometheus | Media | Bajo-medio | cAdvisor/Prometheus ya desplegados (`docs/04`, `docs/08`); inventario de servicios ya hecho (`docs/01`); GPU de `ryzen` queda fuera |
| 39 | ~~`pi-dns` fuera del clúster Swarm — solo DNS/Tailscale; Traefik en modo `global` dentro del swarm~~ | Media | Medio-alto | **Completado** — `apikey-service` migrado al Swarm (mejora 41, cierre), la copia local de `pi-dns` retirada |
| 40 | DNS secundario del clúster — resolución de `*.404labo.net` sin depender solo de `pi-dns` | Media | Bajo-medio | Config de Unbound/Pi-hole ya versionada; alcance de sincronización (Pi-hole completo vs. solo Unbound) queda como decisión abierta |
| 41 | ~~Retirar `*.home.arpa` por completo — todo bajo `404labo.net`~~ | Media | Medio | **Completado** (2026-08-28) — `home.arpa` retirado de Pi-hole/Traefik/Unbound, `nginx` decomisionado, ver `docs/31-docker-swarm.md` |
| 42 | Alertas de disponibilidad de nodos y servicios | Media | Bajo | Prometheus/Grafana Alerting ya desplegados, mismo patrón que la alerta de undervoltage (`docs/14`); canal de notificación real ya disponible (mejora 4, ntfy) — solo falta añadir el matcher correspondiente a `pi-obs/config/grafana/alerting/notification-policies.yml` |
| 43 | ~~Auditoría de bind-mounts en Docker Swarm — evaluar alternativas a la fijación por nodo y a los puertos en `mode: host`~~ | Media | Medio | **Completado** (2026-08-31) — Bifrost/Capataz/Infisical revisados y redesplegados (`docker config` + `mode: ingress` donde no había colisión real); NFS-backed volumes evaluados y descartados por ahora, sin medir, sin urgencia real |
| 44 | Pendiente de revisión — `sonarqube` se cuelga arrancando `infisical run` en `pinchi` | Media | Bajo-medio | Movido de vuelta a `pi-sonar` sin pérdida de datos; red/DNS/TLS/CA/allowlisting ya descartados como causa, falta sesión de depuración específica antes de reintentar el traslado |
| 45 | ~~Dashboards de Grafana por servicio~~ | Media | Medio | **Completado** (2026-09-03) — plantilla genérica `homelab-servicio-generico` (38 servicios, Swarm + Compose clásico unificados) + dashboards a medida de `apikey-service` (auditoría OTLP real) y `qdrant` (recursos/logs + métricas nativas reales vía API key de solo lectura) |
| 46 | Verificar si `toggle-direct-access.sh` cierra de verdad el acceso en los 5 managers, no solo en el nodo "asignado" | Media | Bajo-medio | Ningún servicio queda ya en `mode: host` tras la revisión de constraints (2026-08-31) -- confirmado en vivo que la routing mesh responde igual desde cualquier manager; falta comprobar si `DOCKER-USER` intercepta ese tráfico reenviado o lo bypasa |
| 47 | ~~Volúmenes Docker `type: nfs` en vez de montaje NFS manual por nodo~~ | Baja | Bajo-medio | **Completado** (2026-09-03), 10 servicios migrados en dos pasadas: `registry`/`epub2pdf-service`/`pdf2chunks-service` (+ constraint de arquitectura x86_64 en los dos con imagen solo-amd64) y `authentik`/`capataz`/`n8n-main`/`n8n-aux`/`open-terminal-mcp`/`open-webui`/`sonarqube` (solo `extensions/`) — mismo dato real en el NAS, sin migración de bytes. `postgres-main`/`qdrant`/`sonarqube data/` siguen explícitamente fuera sin resolver antes el *fencing* |
| 48 | Cockpit + libvirt en `ryzen` — gestión de VMs, arranque/parada por Ansible | Baja-media | Medio-alto | `ryzen` ya fuera del Swarm (mejora 37) y con Wake-on-LAN (mejora 19); acceso SSH hoy solo de alcance estrecho (`docs/16`); arranque/parada por Ansible depende de la mejora 6 (no iniciada) |
| 49 | k3s en `ryzen` sobre VMs — clúster Kubernetes aislado para aprendizaje | Baja | Medio-alto | Depende por completo de la mejora 48 (necesita las VMs primero); entorno paralelo, no sustituye la decisión explícita de "Docker Swarm, no Kubernetes" (mejora 33/39, `CLAUDE.md`) |
| 50 | Cudy R700 como router principal — gateway/DHCP/firewall/NAT del homelab | Baja | Medio | Guía completa en `docs/cudy.R700.router.md`; decisión pendiente sobre direccionamiento (mantener `192.168.1.0/24` vs. la `192.168.10.0/24` de la guía) antes de tocar nada — ver detalle en la sección 50 |
| 51 | Migrar las 4 Raspberry Pi (`pi-dns`/`pi-obs`/`pi-sonar`/`pi-utils`) de Ubuntu Server a Alpine Linux | Baja-media | Medio-alto | Factible (investigado 2026-09-15, soporte RPi5 confirmado desde Alpine 3.19) — se beneficia de la mejora 40 (DNS secundario) antes de tocar `pi-dns` y de cerrar la mejora 44 antes de `pi-sonar`; media docena de `shared/scripts/*.sh` a reescribir (apt/systemd → apk/OpenRC) |
| 52 | Aplicar el procedimiento de acceso SSH (`docs/38`) — usuario único `admin` en los 7 nodos, claves por nodo en Infisical, `ssh-node.sh` | Media | Medio | Procedimiento ya escrito (`docs/38-acceso-ssh-nodos.md`); falta dar de alta `admin` en los 7 nodos (incluido `ryzen`) y retirar los 6 usuarios antiguos una vez verificado |


Ninguna de estas mejoras es urgente ni bloqueante — el clúster funciona correctamente sin ellas.
