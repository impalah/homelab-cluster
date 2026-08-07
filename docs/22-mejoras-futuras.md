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

## 15. Panel de control para arrancar/parar servicios y estado en `index.home.arpa`

**Prioridad: media**

### Qué hay hoy

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

## 16. Sistema de secretos para consumo programático (HashiCorp Vault / Infisical)

**Prioridad: media**

### Qué hay hoy

Vaultwarden guarda las credenciales del clúster, pero está pensado para que una persona las desbloquee, no para que un contenedor las pida solo al arrancar — no tiene secretos dinámicos, ni permisos finos por servicio, ni auditoría de quién leyó qué y cuándo. El patrón real hoy es manual: los valores se copian a mano desde Vaultwarden a los `.env.example` → `.env` de cada nodo/servicio durante el despliegue (`docs/05` a `docs/10`), y ahí se quedan, fijos, hasta que alguien los rota también a mano.

### Qué haría falta

1. Elegir entre dos filosofías distintas, no solo dos productos:
   - **HashiCorp Vault (OSS)** — autenticación por servicio vía `AppRole` (cada microservicio con su `role_id`/`secret_id`), con un motor de secretos dinámicos que podría llegar a generar credenciales de Postgres de vida corta para `postgres-main` en vez de contraseñas fijas eternas, más versionado (KV v2) y auditoría. Más potente, pero una pieza de infraestructura real que aprender a operar bien (proceso de *unseal*, políticas de acceso).
   - **Infisical** — mismo concepto de fondo (identidades de máquina, secretos versionados, `infisical run --` para inyectar variables de entorno sin tocar el código), pero mucho más ligero de desplegar y mantener, con una interfaz web más amigable — a cambio de no tener secretos dinámicos.
2. Nodo: `retaco` encaja mejor que una Raspberry Pi — es el nodo de datos, siempre encendido, y ya aloja `postgres-main` (Infisical necesita Postgres + Redis; Vault, con almacenamiento Raft integrado, no necesita nada externo).
3. Migración incremental, no de golpe: empezar por un único servicio —`apikey-service` es el candidato obvio, ya que su propio `APIKEY_ADMIN_TOKEN` y el DSN de su base de datos son justo el tipo de secreto que tiene sentido dejar de tener fijo en un `.env`—, confirmar que el patrón funciona bien en la práctica, y solo entonces extenderlo al resto.
4. Decidir si se publica detrás de `nginx`/`apikey-service` o no: probablemente no vía HTTPS público del clúster — el acceso debería quedar limitado a la red interna, ya que es la pieza que termina protegiendo a todas las demás.
5. Vaultwarden no desaparece: sigue siendo el sitio correcto para credenciales que de verdad usa una persona (paneles de administración, cuentas de servicios de terceros). El sistema de secretos nuevo cubre el consumo entre máquinas, no sustituye a Vaultwarden.

### Esfuerzo estimado
Medio-alto — sobre todo por decidir la arquitectura de acceso (qué servicio tiene qué política) y migrar credenciales existentes sin romper nada por el camino; desplegar el propio servicio es la parte más sencilla.

---

## 17. Open Terminal en modo MCP, conectado desde Open WebUI y n8n

**Prioridad: media**

### Qué hay hoy

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

## 22. Integrar las métricas de Bifrost en Grafana

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
5. Con esto en Grafana, se podría además dar de baja el presupuesto con aviso manual por n8n propuesto en `docs/23` (sección "Seguimiento de coste") en favor de una alerta nativa de Grafana sobre `bifrost_cost_total` — a evaluar cuál de los dos caminos conviene más una vez se pruebe este.

### Esfuerzo estimado
Bajo — reutiliza infraestructura ya montada (Prometheus, Grafana, patrón de `scrape_config` con auth), el trabajo real es decidir qué paneles importan y probar el `basic_auth` contra Bifrost.

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

## Resumen

| # | Mejora | Prioridad | Esfuerzo | Depende de |
|---|---|---|---|---|
| 1 | Automatizar las copias de seguridad y copiarlas fuera de nodo | Alta | Bajo–medio | — |
| 2 | ~~`git init` del repo + remoto~~ | Alta | — | **Completado** |
| 3 | Alerta de espacio en disco | Media | Bajo | Reutiliza patrón de `docs/14` |
| 4 | ntfy (notificaciones proactivas) | Media | Medio | — |
| 5 | Integración NUT del SAI existente | Media | Medio | Modelo de SAI compatible con `usbhid-ups` |
| 6 | Migrar tooling de mantenimiento a Ansible | Media | Medio-alto | Punto 2 (ya cumplido) |
| 7 | Forgejo (repos + CI + artefactos), con GitHub como espejo | Media | Alto | Punto 2 (ya cumplido) |
| 8 | Registry: limpieza y garbage collection | Media | Bajo | Registry ya desplegado (`docs/05`) |
| 9 | Tailscale: política de ACL | Baja | Bajo-medio | Tailscale ya desplegado (`docs/18`) |
| 10 | NAS UGREEN: migrar `nfs-data` a NFSv4 | Baja | Bajo-medio | NAS ya configurado en NFSv3 (`docs/21`) |
| 11 | k6 para pruebas de carga automatizadas | Media | Bajo-medio | Prometheus/Grafana ya desplegados (`docs/08`) |
| 12 | RAG de libros en PDF desde Open WebUI | Media | Medio | `markitdown-service`, Qdrant y Ollama ya desplegados |
| 13 | Copiar logs/métricas de pi-obs al NAS | Media | Medio | NFS del NAS ya montado (`docs/21`) |
| 14 | Evaluar Floci como emulador local de AWS | Media | Bajo | — |
| 15 | Panel de control de servicios + estado en `index.home.arpa` | Media | Medio | Portainer ya desplegado (`docs/10`) |
| 16 | Sistema de secretos programático (Vault / Infisical) | Media | Medio-alto | `postgres-main` ya desplegado (`docs/05`); complementa a Vaultwarden (`docs/10`) |
| 17 | Open Terminal en modo MCP (Open WebUI + n8n) | Media | Bajo-medio | Open WebUI y n8n ya desplegados |
| 18 | OpenClaw — asistente personal de IA autoalojado | Media | Medio | Ollama ya desplegado si se apunta a modelos locales |
| 19 | Opencode — agente de código open source para terminal | Media | Bajo | Ollama ya desplegado si se apunta a modelos locales |
| 20 | LiteLLM — proxy unificado hacia AWS Bedrock, conectado a Open WebUI | Media | Medio | Cuenta/IAM de AWS; Open WebUI ya desplegado; alternativa a mejora 21 |
| 21 | ~~Bifrost — gateway hacia AWS Bedrock, conectado a Open WebUI~~ | Media | — | **Completado** — `docs/23-bifrost-gateway-llm.md` |
| 22 | Integrar las métricas de Bifrost (`/metrics`) en Grafana | Media | Bajo | Bifrost ya desplegado (`docs/23`); Prometheus/Grafana ya desplegados (`docs/08`) |
| 23 | ~~Mover `logs.db`/`config.db` de Bifrost a Postgres centralizado~~ | Media | — | **Completado** — `docs/23-bifrost-gateway-llm.md` |

Ninguna de estas mejoras es urgente ni bloqueante — el clúster funciona correctamente sin ellas.
