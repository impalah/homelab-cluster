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

**Prioridad: media** — **implementado (uso manual), 2026-08-15**

### Qué se hizo

Los tres scripts (`shared/scripts/registry-garbage-collect.sh`, `registry-prune-tags.sh`, `backup-registry.sh`) están listos y sincronizados en los 5 nodos — detalle completo, comandos y verificación en vivo en `docs/29-registry-mantenimiento.md`. Alcance decidido explícitamente al implementarlo:

1. **Garbage collection**: script listo, **solo ejecución manual** (sin cron) — el propio comando exige que el registry no reciba pushes mientras corre, automatizarlo sin supervisión era más riesgo que beneficio en un clúster con pocos pushes reales.
2. **Retención de tags**: **3 versiones antiguas por imagen** (además de `latest`) — script propio (`registry-prune-tags.sh`, vía la API HTTP del registry), también solo manual.
3. **Copia de seguridad**: script listo (`backup-registry.sh`, mismo patrón que `backup-vaultwarden.sh`) pero **sin ejecutar todavía** — decisión explícita, las imágenes son reconstruibles desde el código fuente.
4. **Alerta de espacio en disco**: **diferida a la mejora 3** (alertas de espacio en disco genéricas) — no tiene sentido una alerta específica de registry antes de que exista la genérica por nodo; `retaco` queda cubierto sin trabajo adicional en cuanto se aborde esa mejora.

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

## 10. NAS UGREEN — migrar `nfs-data` a NFSv4

**Prioridad: baja**

### Qué hay hoy

NFSv3 funciona perfectamente para `nfs-data` (root sin squash, confirmado en uso real con bind mounts de Docker) — ver `docs/21-configuracion-nas-ugreen.md`. NFSv4 se negocia a nivel de kernel (`/proc/fs/nfsd/versions` muestra `+4`), pero los montajes v4 fallan con `No such file or directory` porque UGOS Pro no expone un pseudo-root de NFSv4 (`fsid=0`) en el `/etc/exports` que genera desde la GUI. Sin urgencia — v3 cubre el uso actual sin problema, se retoma cuando apetezca.

### Qué haría falta

1. Confirmar el mecanismo real que usa UGOS Pro para generar `/etc/exports` (¿desde `nfs.json`, igual que `nfs.conf`, o desde otro sitio?) antes de tocarlo a mano — mismo riesgo ya conocido de que la GUI lo sobrescriba en cuanto se vuelva a tocar esa pantalla.
2. Añadir a mano, por SSH, un export raíz con `fsid=0` (p. ej. algo del estilo `/volume1 192.168.1.0/24(ro,fsid=0,no_subtree_check)`, o el ajuste equivalente si UGOS Pro expone alguna opción para esto en la GUI que no se haya encontrado todavía).
3. Probar montaje v4 desde un cliente Linux con la ruta relativa a esa raíz (no la ruta real `/volume1/nfs-data` usada hoy con v3).
4. Si funciona: actualizar `docs/21-configuracion-nas-ugreen.md` y el `/etc/fstab` de los clientes que usen `nfs-data`.
5. Si UGOS Pro no lo permite de forma estable (revierte el export raíz al tocar la GUI): documentar como limitación permanente del NAS y descartar el punto, quedándose en v3 definitivamente.

### Esfuerzo estimado
Bajo-medio — la parte técnica es sencilla si UGOS Pro lo permite; la incertidumbre real es si la GUI lo revierte.

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
6. Conectar esa alerta al canal de notificación proactivo (ntfy, mejora 4) en cuanto exista; hasta entonces, un *contact point* de correo o quedarse solo con el aviso visual del panel como mínimo viable.
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
  - [Zot](https://github.com/project-zot/zot) (Go, Apache-2.0, sandbox de CNCF) — registry OCI/Docker moderno, binario único, huella mínima; candidato a sustituir `registry:2` (mejora 8) si se revisita esa pieza más adelante.
  Cada componente consume una fracción del heap mínimo de Nexus y se actualiza/reinicia de forma independiente — más "filosofía Unix", pero más piezas sueltas que mantener (el trade-off inverso a Nexus).
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
3. Cliente ACME: `certbot`/`acme.sh` con el plugin del proveedor DNS elegido, corriendo en `pi-dns` junto al `nginx` actual — o, si se aborda junto con la mejora 35 (Traefik), su integración ACME nativa (`certificatesResolvers`), que evitaría montar un cliente ACME aparte.
4. **Renovación automática obligatoria** — a diferencia de la CA interna (10 años, prácticamente "y olvídate"), los certificados de Let's Encrypt caducan a los 90 días. Sin cron/hook de renovación con recarga de nginx, el clúster completo quedaría con TLS caducado en menos de tres meses.
5. Decidir el alcance: ¿sustituye del todo a la CA interna, o conviven? Los hostnames `*.home.arpa` seguirían resolviendo a IPs internas vía Pi-hole igual que hoy — lo que cambia es el certificado que sirve `nginx`, que pasaría a tener SAN del dominio real en vez de (o además de) `*.home.arpa`. Servicios pensados para quedarse siempre puramente internos podrían mantenerse en la CA propia si no compensa el cambio.
6. Revisar el impacto en todo lo que hoy confía en la CA interna a nivel de sistema (`docs/15-ca-interna.md`, sección Linux/Docker) — con Let's Encrypt, un certificado válido públicamente ya no necesita que cada nodo/dispositivo instale nada a mano, lo cual elimina de raíz la clase de problema que motivó varios de los gotchas ya documentados en este repo.
7. Confirmar que el Split DNS de Tailscale (`docs/18-tailscale.md`) sigue funcionando igual una vez el hostname resuelto por dentro del tailnet difiera del hostname real del certificado, si se elige no usar el dominio real también ahí.

### Esfuerzo estimado
Medio-alto — depende sobre todo del proveedor DNS elegido (facilidad de su API para el reto DNS-01) y de si se combina con la migración a Traefik (mejora 35), que simplificaría bastante el mecanismo de renovación.

---

## 33. Migrar el clúster a Docker Swarm, progresivamente

**Prioridad: baja-media**

### Qué hay hoy

Este mismo `CLAUDE.md` fija como decisión de arquitectura explícita: *"Docker Engine + Docker Compose v2 only (explicitly no Kubernetes, no Docker Swarm)"*. Hoy son 6 stacks de Compose completamente independientes, cada uno con su propia red bridge (`<nodo>-net`), sin red Docker compartida entre nodos — el tráfico entre nodos va por la LAN real vía `*.home.arpa` (`docs/01-topologia.md`). Adoptar Swarm sería revertir esa decisión de forma consciente, no una continuación natural de lo que hay — conviene evaluarlo con calma antes de tocar nada, empezando por un piloto de bajo riesgo, no un cambio de golpe en los 6 nodos.

### Qué haría falta

1. **Decidir el alcance real primero**: ¿un único swarm con los 6 nodos, o empezar con un subconjunto? Swarm no exige arquitectura homogénea entre nodos (arm64 y amd64 conviven en el mismo clúster sin problema), pero cada *servicio* concreto sigue necesitando su propia imagen multi-arch si va a poder programarse en cualquier nodo — ya resuelto para `apikey-service`/`markitdown-service` (`docker buildx build --platform linux/amd64,linux/arm64`), no para `whisper-service` (amd64-only a propósito, necesita CUDA).
2. **Quórum de managers, y `ryzen` fuera del propio Swarm**: Raft necesita mayoría de managers vivos para aceptar escrituras — con los nodos restantes, un esquema típico serían 3 managers (impar, tolera 1 caída) y el resto workers. `ryzen`/`mole` queda **decidido fuera del clúster Swarm por completo, ni siquiera como worker** (no solo "mal candidato a manager") — se apaga habitualmente cuando no se usa (`docs/19-wake-on-lan.md`) y aloja servicios especializados con alternancia de GPU (`switch-llm-backend.sh`/`switch-gpu1-backend.sh`) que no encajan con que el scheduler de Swarm decida dónde correr algo. Sigue gestionado con Docker Compose puro, tal cual hoy — detalle de las implicaciones de esta exclusión en la mejora 37.
3. **Red overlay**: Swarm sustituye las redes bridge por nodo por una red overlay cifrada entre nodos vía VXLAN — revisar qué puertos hace falta abrir en el firewall gestionado hoy por `shared/scripts/setup-firewall.sh`/`toggle-direct-access.sh` (`docs/17-firewall-acceso-directo.md`), y si el tráfico VXLAN puede ir sin fricción por la LAN interna ya existente.
4. **Migración incremental sugerida**: empezar por un servicio sin estado y de bajo riesgo (un microservicio propio, p. ej.) desplegado como `docker stack deploy` en paralelo al `docker-compose.yml` actual, verificar equivalencia funcional, y solo entonces plantear servicios con estado. Éstos son el caso realmente delicado: Swarm no resuelve por sí solo la persistencia multi-nodo — sigue haciendo falta bind-mount local, y el scheduler podría reprogramar el contenedor en otro nodo perdiendo acceso a sus propios datos si no se fija explícitamente con `constraints` (`node.hostname==retaco`, por ejemplo, para `postgres-main`).
5. **`docker-compose.yml` no se traduce 1:1 a `docker stack deploy`** — Swarm ignora `build:` (haría falta ya tener las imágenes publicadas en `registry.home.arpa`, lo cual este repo ya cumple para los servicios propios) y trata algunas claves de forma distinta. Revisar cada `docker-compose.yml` del repo antes de asumir que basta con `docker stack deploy -c docker-compose.yml <nombre>`.
6. **Relación con la mejora 35 (Traefik)**: Traefik es el proxy natural de un clúster Swarm (descubre servicios vía labels, igual que ya hace hoy sobre Docker standalone) — decidir si Swarm se aborda junto con Traefik desde el principio, o antes, dejando `nginx` configurado a mano un tiempo más sobre el nuevo Swarm.
7. **`watchtower`/`shared/scripts/update-stack.sh` actuales asumen Compose standalone** — revisar el equivalente nativo de Swarm (`docker service update --image ...`, con rolling update incorporado), que sería una mejora real sobre el `--force-recreate` que se usa hoy. Mantener actualizados los contenedores ya desplegados en Swarm (vigilancia + aplicación del rolling update) es justo la continuación natural del mecanismo ya existente hoy para Compose (`watchtower` + `check-image-updates.sh`, `docs/16-mantenimiento-actualizaciones.md`) — no es un problema nuevo que diseñar desde cero, ver mejora 36.
8. **Justificar el cambio con honestidad, no solo "porque se puede"**: en un clúster de un solo operador, el argumento fuerte de Swarm no es alta disponibilidad real (nadie necesita failover automático 24/7 en un homelab) — es rolling updates nativos, red overlay gestionada y `docker secret`/`docker config` propios. Documentar explícitamente qué se gana frente al coste de complejidad añadida antes de comprometerse, mismo criterio que se aplicó a la comparativa Vault-vs-Infisical (mejora 16).

### Esfuerzo estimado
Alto — no por dificultad técnica puntual, sino por ser un cambio de paradigma que toca los 6 nodos y cada `docker-compose.yml` del repo; abordar por fases, nunca de golpe, empezando por un piloto sin estado.

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

1. Traefik en modo *Docker provider* (standalone) o *Docker Swarm provider* si se aborda junto con la mejora 33 — descubre servicios automáticamente vía labels declaradas en el propio `docker-compose.yml`/stack (`traefik.http.routers.<servicio>.rule=Host(...)`), sin tocar un fichero de configuración central por cada hostname nuevo. Resuelve directamente la fricción operativa que hoy tiene `nginx`.
2. **Punto crítico de esta mejora**: Traefik solo aporta descubrimiento automático real si corre sobre el mismo Docker que orquesta los servicios a exponer. Hoy `pi-dns` es un nodo aparte de donde corre la mayoría de servicios del clúster (arquitectura de "un nodo, una IP, LAN real entre nodos, sin red Docker compartida", `docs/01-topologia.md`) — un Traefik en modo Docker standalone en `pi-dns` solo vería los contenedores de `pi-dns` mismo, no los de `retaco`/`pi-utils`/etc. Para descubrir servicios de otros nodos automáticamente hace falta el *provider* de Docker Swarm (mejora 33) o, si no, declarar cada servicio a mano vía el *provider* de fichero — perdiendo la ventaja principal frente a `nginx`. **Esta mejora depende en la práctica de la 33**: sin Swarm, Traefik en este clúster cambia la sintaxis de configuración manual, pero no elimina el trabajo manual en sí.
3. Si se combina con la mejora 32 (Let's Encrypt): Traefik trae integración ACME nativa (`certificatesResolvers`, reto DNS-01 con el proveedor DNS elegido) — sería la pieza que más simplifica esa mejora si se abordan juntas, evitando montar `certbot`/`acme.sh` como proceso aparte.
4. `auth_request` (`apikey-auth.conf`, protección de `ollama`/`epub2pdf`/etc.) tiene equivalente directo en Traefik vía el middleware `ForwardAuth` — mismo concepto (llamada a `apikey-service` antes de dejar pasar la petición), sintaxis distinta, hay que migrarlo servicio a servicio.
5. Migración incremental: Traefik y `nginx` pueden convivir temporalmente en puertos distintos mientras se migra servicio a servicio — mismo criterio de evaluar en paralelo ya usado con Bifrost/LiteLLM (mejoras 20/21).
6. Dashboard propio de Traefik: decidir si se expone (protegido con Authentik forward-auth, mejoras 25/29) o se deja solo accesible en local, mismo criterio ya aplicado a otros paneles de administración del clúster.
7. Revisar los snippets especiales que `nginx` ya resuelve hoy (`proxy-common.conf`, `proxy_buffering off` + timeouts largos para el streaming SSE de `open-terminal-mcp`, mejora 17) — cada uno necesita su middleware equivalente en Traefik antes de dar por sustituible la configuración actual.

### Esfuerzo estimado
Alto — depende directamente de si se aborda junto con la migración a Swarm (mejora 33): por separado, la ganancia real es mucho menor (se cambia la sintaxis de configuración manual, pero no el trabajo manual en sí) y probablemente no compensa reescribir toda la configuración de `nginx` ya probada en producción.

---

## 36. Vigilancia y alertas del estado de parcheo de los nodos (SO) — y su continuación en Swarm

**Prioridad: media**

### Qué hay hoy

**No es un hueco nuevo — es un punto ciego dentro de algo que ya funciona.** `docs/16-mantenimiento-actualizaciones.md` ya resuelve tanto la actualización del sistema operativo (`unattended-upgrades` para parches de seguridad automáticos en los seis nodos, `update-os.sh` para actualización completa bajo demanda) como la de las imágenes Docker (Watchtower para lo sin estado, `check-image-updates.sh` con panel en Grafana para el resto) — ver también la mejora 6, que **no es lo mismo**: esa mejora migra el *tooling* de mantenimiento a Ansible por idempotencia (evitar el bug de `chown -R` que rompió `postgres-main`, `docs/13-troubleshooting.md`), no añade vigilancia ni alertas nuevas — Ansible o bash seguiría teniendo el mismo punto ciego si no se aborda aparte.

El punto ciego real: las actualizaciones de **imagen Docker** sí tienen visibilidad centralizada (métrica Prometheus vía *textfile collector*, panel `homelab-actualizaciones-pendientes` en Grafana, `docs/16` sección 2.2) — pero las actualizaciones de **sistema operativo** no tienen ningún equivalente. Hoy, saber si un nodo tiene parches de seguridad pendientes o si necesita reinicio tras uno (`/var/run/reboot-required`) exige entrar por SSH a cada nodo y mirar `unattended-upgrades.log` a mano — no hay métrica, no hay panel, no hay alerta. Es exactamente el mismo tipo de hueco que ya se cerró para espacio en disco (mejora 3) y para imágenes Docker (`docs/16`), pero sin cerrar todavía para parches del propio SO.

### Qué haría falta

1. **Métrica de estado de parcheo por nodo**, mismo patrón que `check-image-updates.sh` (`docs/16` sección 2.2): un script (o, si ya existe para entonces, un playbook de Ansible — mejora 6 — que reutilice sus propios *facts*) que escriba, vía *textfile collector* de `node-exporter`, dos cosas por nodo: número de paquetes con actualización de seguridad pendiente (`apt list --upgradable` filtrado a `-security`) y si `/var/run/reboot-required` existe (0/1). A diferencia de `check-image-updates.sh` (centralizado en `pi-obs`, vía SSH a los demás nodos), aquí probablemente sea más simple que cada nodo escriba su propio fichero `.prom` localmente por cron — confirmar que el *textfile collector* de `node-exporter` está montado en los seis nodos (hoy documentado explícitamente solo para `pi-obs`, `pi-obs/docker-compose.yml`) antes de asumir que ya está listo en el resto.
2. **Panel en Grafana**, junto al ya existente de imágenes pendientes (`homelab-actualizaciones-pendientes`) o como panel nuevo en el mismo dashboard — mismo criterio de reutilizar infraestructura ya montada que el resto de mejoras de este documento.
3. **Alerta**: reinicio pendiente durante más de X días, o número de actualizaciones de seguridad por encima de un umbral — mismo patrón que la alerta de undervoltage/disco (mejora 3), conectada al canal de notificación proactivo (ntfy, mejora 4) en cuanto exista.
4. **Cuidado especial con `pi-dns`**: único punto de fallo del DNS de toda la LAN (`docs/16`, ya lo advierte para el reinicio manual) — cualquier alerta de reinicio pendiente en `pi-dns` merece más visibilidad que en el resto, pero **la alerta sigue siendo solo aviso, nunca dispara un reinicio automático** — mismo principio ya fijado en `docs/16` ("ningún nodo se reinicia solo").
5. **Continuación en Swarm, si se llega a adoptar (mejora 33)**: mantener actualizados los contenedores desplegados como `docker stack deploy` no es un problema nuevo que diseñar desde cero — es la misma vigilancia de imagen (punto 1 de esta lista, ya resuelto para Compose) aplicada sobre `docker service ls`/`docker service update --image`, que además da rolling update nativo en vez del `--force-recreate` actual (ver mejora 33, punto 7). Confirmar si Watchtower en modo Swarm (existe, vigila servicios en vez de contenedores sueltos) sirve tal cual, o si conviene sustituirlo por el propio mecanismo de Swarm combinado con el aviso de `check-image-updates.sh` ya existente.

### Esfuerzo estimado
Bajo — reutiliza infraestructura ya montada (*textfile collector*, Grafana, el propio patrón de `check-image-updates.sh`); el trabajo real es escribir el script/playbook y decidir umbrales de alerta razonables. El punto 5 (continuación en Swarm) solo aplica si se adopta la mejora 33.

---

## 37. `ryzen` (mole) fuera del clúster Swarm — operativa como nodo Compose independiente

**Prioridad: baja-media**

### Qué hay hoy

Decidido explícitamente (ver mejora 33, punto 2): si el resto del clúster migra a Docker Swarm, **`ryzen`/`mole` se queda fuera por completo**, ni siquiera como worker — sigue gestionado con Docker Compose puro, tal cual hoy. Motivo doble: es el único nodo que se apaga habitualmente cuando no se usa (`docs/19-wake-on-lan.md`, GPU de escritorio, no infraestructura siempre encendida) y aloja servicios especializados con alternancia manual de GPU (`ryzen/switch-llm-backend.sh` para GPU 0 ollama/vllm, `ryzen/switch-gpu1-backend.sh` para GPU 1 whisper-service/comfyui, `docs/07-instalacion-ryzen.md`) que dependen de que el operador controle explícitamente qué corre y cuándo — justo lo contrario de dejar que un scheduler decida.

`ryzen` ya tiene hoy dos stacks de Compose completamente independientes (`docker-compose.yml` para GPU/AI, `docker-compose.observability.yml` para node-exporter/cadvisor sin `.env`) — esta pieza **ya existe y no necesita rehacerse** por la migración a Swarm de los demás nodos. Lo que sí falta es dejar explícita la operativa de un clúster mixto Swarm+Compose, para no dar por hecho luego que "todo el clúster" se comporta igual.

### Qué haría falta

1. **Networking**: si los otros 5 nodos pasan a una red overlay VXLAN (mejora 33, punto 3), `ryzen` se queda fuera de esa red — sigue expuesto solo por la LAN real vía `*.home.arpa`, exactamente como hoy (`docs/01-topologia.md`). No requiere ningún cambio en `ryzen/docker-compose.yml` ni en `docker-compose.observability.yml` por este motivo.
2. **Traefik/nginx (mejora 35) no puede autodescubrir `ryzen`**: si `pi-dns` pasa a Traefik con *provider* de Docker Swarm, ese autodescubrimiento por labels solo ve contenedores dentro del propio Swarm — los servicios de `ryzen` (`ollama`, `vllm`, `open-webui`, `whisper-service`, `comfyui`) seguirán necesitando declararse a mano (vía IP/hostname fijo, como hoy con nginx) en vez de vía labels. Documentar esto como excepción permanente cuando se aborde la mejora 35, no como un pendiente de migrar más adelante.
3. **`apikey-service` sigue protegiendo `ryzen` igual que hoy**: al no depender de redes Docker compartidas entre nodos (el `auth_request` de nginx/Traefik llama por HTTP sobre la LAN), la protección de `ollama` y demás servicios de `ryzen` no cambia con la migración del resto a Swarm.
4. **Mantenimiento del nodo se queda en el mecanismo Compose actual, sin excepción**: `watchtower`, `check-image-updates.sh`, `update-stack.sh`, y los propios `switch-llm-backend.sh`/`switch-gpu1-backend.sh` (`docs/16-mantenimiento-actualizaciones.md`) — `ryzen` **nunca** pasa a los equivalentes nativos de Swarm (`docker service update --image`, mejora 33 punto 7, ni la vigilancia de imagen en modo Swarm de la mejora 36 punto 5), porque nunca entra en el Swarm. Dejarlo dicho explícitamente para que nadie intente aplicarle tooling de Swarm por costumbre una vez el resto del clúster lo use.
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
| 8 | ~~Registry: limpieza y garbage collection~~ | Media | Bajo | **Implementado (uso manual)** — `docs/29-registry-mantenimiento.md`; alerta de disco diferida a la mejora 3 |
| 9 | Tailscale: política de ACL | Baja | Bajo-medio | Tailscale ya desplegado (`docs/18`) |
| 10 | NAS UGREEN: migrar `nfs-data` a NFSv4 | Baja | Bajo-medio | NAS ya configurado en NFSv3 (`docs/21`) |
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
| 22 | Coste de llamadas LLM (Bifrost) en Grafana, con vigilancia y alarmas | Media | Bajo-medio | Bifrost ya desplegado (`docs/23`, expone `bifrost_cost_total`); Prometheus/Grafana ya desplegados (`docs/08`); alerta conectable a ntfy (mejora 4) en cuanto exista |
| 23 | ~~Mover `logs.db`/`config.db` de Bifrost a Postgres centralizado~~ | Media | — | **Completado** — `docs/23-bifrost-gateway-llm.md` |
| 24 | ~~Servidor Valkey (compatible Redis) securizado — key-value + pub/sub~~ | Media | — | **Completado** — `docs/25-valkey-cache.md` |
| 25 | ~~Authentik — authn/authz centralizado, piloto en Prometheus~~ | Media | — | **Completado** — `docs/27-authentik-sso.md`; solo Prometheus protegido, resto en mejora 29 |
| 26 | Investigar tool-calling fiable — modelos locales (Ollama) y Bedrock/Claude (Bifrost) | Media | Medio | Open Terminal MCP ya desplegado (mejora 17, `docs/24`); ningún modelo probado completa una llamada de herramienta hoy |
| 27 | Activar TLS en `postgres-main` | Media | Medio-alto | CA interna ya desplegada (`docs/15`); patrón ya probado con Valkey (mejora 24, `docs/25`) |
| 28 | ~~Migrar el resto de servicios del clúster a Infisical~~ | Media | — | **Completado (parcial)** — `docs/26-infisical-secretos.md`; 9 servicios migrados, `registry`/`postgres-exporter`/`whisper-service`/`vllm` quedan para más adelante |
| 29 | Integrar Authentik en el resto de paneles (OIDC nativo: Grafana, Portainer...) | Media | Medio | Authentik ya desplegado y patrón forward-auth validado (mejora 25, `docs/27`) |
| 30 | Entorno de notebooks en el clúster (code-server / JupyterLab) para estudios de datos | Baja-media | Bajo-medio | Postgres/Qdrant y NFS del NAS ya disponibles; Authentik (mejora 25) para protegerlo; solo compensa si hace falta ejecución que sobreviva a la sesión de escritorio |
| 31 | Nexus (u alternativa) como repositorio centralizado de paquetes, integrado con Forgejo | Baja | Medio | Forgejo (mejora 7) para la integración de CI; NFS del NAS ya disponible; experimento deliberado, no cubre carencia operativa hoy |
| 32 | Dominio real + certificados Let's Encrypt (sustituye CA interna) | Media | Medio-alto | CA interna ya desplegada (`docs/15`); sinergia con mejora 35 (ACME nativo de Traefik) |
| 33 | Migrar el clúster a Docker Swarm, progresivamente | Baja-media | Alto | Reversión consciente de la decisión "no Swarm" fijada en este `CLAUDE.md`; imágenes multi-arch ya resueltas para `apikey-service`/`markitdown-service` |
| 34 | GitOps para las aplicaciones del clúster (propuestas a evaluar) | Media | Medio-alto | Depende de la propuesta elegida; sinergia con mejora 33 si se adopta Swarm |
| 35 | Sustituir `nginx` por Traefik, integrado con Docker Swarm | Media | Alto | Depende en la práctica de la mejora 33 (Swarm) para aportar valor real sobre `nginx` |
| 36 | Vigilancia y alertas del estado de parcheo de los nodos (SO), y su continuación en Swarm | Media | Bajo | Distinto de la mejora 6 (Ansible = idempotencia del tooling, no vigilancia); reutiliza el patrón de `check-image-updates.sh` (`docs/16`) y la alerta de disco (mejora 3) |
| 37 | `ryzen` (mole) fuera del clúster Swarm — operativa como nodo Compose independiente | Baja-media | Bajo | Decisión de alcance de la mejora 33 (`ryzen` excluido, ni siquiera worker); documentación de la mejora 35 (Traefik no puede autodescubrirlo) |
| 38 | Capacity planning con datos reales — `mem_limit`/`cpus` a partir de picos en Prometheus | Media | Bajo-medio | cAdvisor/Prometheus ya desplegados (`docs/04`, `docs/08`); inventario de servicios ya hecho (`docs/01`); GPU de `ryzen` queda fuera |

Ninguna de estas mejoras es urgente ni bloqueante — el clúster funciona correctamente sin ellas.
