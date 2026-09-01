# 29 — Mantenimiento de registry.404labo.net

Fecha original: 2026-08-15. **Scripts reescritos el 2026-09-01** para el registry como stack Swarm (`docker-swarm/stacks/registry/`, sin `constraints` de nodo desde el 2026-08-31, datos en NFS `/mnt/nfs-data/registry/`) — la migración de Fase 4 (`docs/31-docker-swarm.md`) dejó estos tres scripts apuntando a un `docker-compose.yml` por nodo y una ruta de datos que ya no existen para este servicio (`registry-garbage-collect.sh` fallaba con `no such service: registry`, encontrado real al intentar ejecutarlo, no solo al leer el código). `registry:2.8.3` no sobrescribe capas antiguas al recibir un `docker push` con el mismo tag — solo deja de referenciarlas; sin limpieza periódica, el disco crece sin límite.

Implementación de la mejora 8 de `docs/22-mejoras-futuras.md` ("Registry — limpieza y garbage collection"), con el alcance decidido explícitamente al implementarla: **todo manual, nada programado por cron**.

## 1. Garbage collection — `shared/scripts/registry-garbage-collect.sh`

Recolecta (borra de disco) las capas ya huérfanas (sin ningún tag/manifest que las referencie).

```bash
bash /srv/homelab/shared/scripts/registry-garbage-collect.sh              # dry-run (no borra nada)
bash /srv/homelab/shared/scripts/registry-garbage-collect.sh --apply      # borra de verdad
```

- Por defecto en modo `--dry-run` — solo lista qué se borraría, hace falta `--apply` explícito.
- **Cómo funciona ahora**: `docker service scale registry_registry=0` (cluster-wide, sin importar en qué nodo estuviera corriendo la tarea), espera a que la tarea pare de verdad (hasta 60s, aborta sin tocar nada si no para), y corre un contenedor suelto (`docker run --rm`) con la misma imagen (`registry:2.8.3`), montando directamente `/mnt/nfs-data/registry/data`, para ejecutar `bin/registry garbage-collect` — sin necesidad de `REGISTRY_HTTP_SECRET` ni de ningún otro env var del stack, es una operación de mantenimiento offline sobre el storage backend, no sirve HTTP. Un `trap` en el `EXIT` reescala siempre a 1 réplica, incluso si el propio GC falla a medias.
- **Ejecutar en cualquier nodo con `/mnt/nfs-data` montado** (los 5 managers Swarm salvo `pi-dns`) — no hace falta que sea el mismo nodo donde estuviera corriendo la tarea real, es el mismo volumen NFS remoto se mire desde donde se mire.
- **Solo ejecución manual, a propósito** — no hay cron ni systemd timer. El propio requisito de "sin pushes concurrentes" hace arriesgado automatizarlo sin supervisión en un clúster con pocos pushes reales; mejor revisar el dry-run a mano cada vez.
- Recolecta blobs ya huérfanos — no decide qué tags conservar. Para liberar espacio de verdad primero hay que podar tags antiguos (punto 2).
- **Verificado en vivo (dry-run, 2026-09-01)** tras el fix, desde `retaco`: `818 blobs marked, 0 blobs and 0 manifests eligible for deletion` — nada que recolectar todavía (registry joven, pocos re-pushes al mismo tag), pero confirma el flujo completo end-to-end: escalado a 0, GC real ejecutado, reescalado a 1, `registry.404labo.net` respondiendo de nuevo (`401` en `/v2/`, la respuesta esperada con auth) tras terminar.

## 2. Política de retención — `shared/scripts/registry-prune-tags.sh`

Decisión: **3 versiones antiguas por imagen**, además de `latest` (hasta 4 tags vivos por repositorio). Actúa vía la API HTTP v2 del registry (el binario `bin/registry` no tiene un subcomando para borrar tags individuales, solo para el GC de blobs) — **no depende de Compose ni de Swarm en absoluto**, solo habla HTTP con `https://registry.404labo.net`, así que la migración a Swarm no lo afectó (confirmado en vivo, 2026-09-01: sin credenciales exportadas falla exactamente con el mensaje esperado — `Debes exportar REGISTRY_USER` — no con ningún error de infraestructura).

```bash
REGISTRY_USER=admin REGISTRY_PASSWORD=<credencial> bash /srv/homelab/shared/scripts/registry-prune-tags.sh              # dry-run, KEEP=3
REGISTRY_USER=admin REGISTRY_PASSWORD=<credencial> bash /srv/homelab/shared/scripts/registry-prune-tags.sh --apply 3    # borra de verdad
```

- Credencial: el usuario compartido de `registry.404labo.net` (htpasswd, ver `docs/05-instalacion-retaco.md` sección 5.3) — guardada en Vaultwarden ("Docker Registry (registry.404labo.net)"), **nunca hardcodeada** en el script ni en este documento.
- Por repositorio: ordena los tags de versión (excluyendo `latest`) con `sort -V` descendente, conserva los `KEEP` (3 por defecto) más recientes, y borra el manifest (`DELETE /v2/<repo>/manifests/<digest>`) de cualquier tag más antiguo.
- **Nunca borra el tag que comparte digest con `latest`** — comprobado explícitamente antes de cada delete, para no desreferenciar accidentalmente la imagen actual solo porque su tag de versión numérica también cae fuera de la ventana de retención.
- Maneja manifest lists multi-arch (Accept: `manifest.list.v2+json` / `oci.image.index.v1+json`, además de `manifest.v2+json`) — necesario para apikey-service/markitdown-service/capataz-api/capataz-runner, todos multi-arch (`docs/28-capataz-consola-automatizacion.md`).
- **Solo ejecución manual, a propósito** — mismo motivo que el GC: es una operación destructiva sobre un registry con pocas imágenes, mejor revisar el dry-run que automatizarla sin supervisión.
- Solo desreferencia tags — no libera espacio por sí solo. Ejecutar `registry-garbage-collect.sh --apply` después para recuperar el disco de verdad.
- Verificado en vivo (dry-run, 2026-08-15) contra los 9 repositorios reales del clúster: ninguno tenía todavía más de 3 versiones antiguas, así que no había nada que podar — confirmado también que con `KEEP=1` detecta y ordena correctamente los tags a borrar de `crawl4ai-scraper-service` (el único repo con 3+ versiones hoy: `0.1.2`/`0.1.1`/`0.1.0`), sin llegar a aplicar el borrado.

## 3. Copia de seguridad — `shared/scripts/backup-registry.sh`

```bash
bash /srv/homelab/shared/scripts/backup-registry.sh
```

- Mismo patrón que `backup-vaultwarden.sh`: escala el servicio a 0 réplicas unos segundos durante el empaquetado, empaqueta `registry/{data,auth}` con `tar`, reescala a 1 (mismo `trap` en `EXIT` que el GC) — evita capturar un blob a medio escribir. Incluye `auth/` (el `htpasswd`): sin él, restaurar solo `data/` deja un registry al que nadie puede autenticarse.
- Lee directamente `/mnt/nfs-data/registry/{data,auth}` — mismo motivo que el GC, ejecutable desde cualquier nodo con `/mnt/nfs-data` montado.
- Genera `/srv/homelab/backups/registry/registry_<fecha>.tar.gz` — **ruta fija, no `/srv/homelab/backups/<nodo>/`** como `backup-postgres.sh`/`backup-vaultwarden.sh` (esos servicios siguen pinnados a un `node.hostname` fijo, registry no desde el 2026-08-31, así que un directorio por nodo dispersaría los backups sin motivo real). No hay script de restauración dedicado todavía (simétrico a `restore-postgres.sh`/`restore-vaultwarden.sh`); restaurar es escalar `registry_registry` a 0, vaciar `/mnt/nfs-data/registry/{data,auth}` y extraer el `tar.gz` ahí, luego reescalar a 1.
- **Preparado pero SIN EJECUTAR todavía** — decisión explícita al implementar esta mejora, que sigue en pie tras el fix del 2026-09-01: las imágenes son reconstruibles desde el código fuente (`services/` de este repo, o el repo externo de Capataz), así que no hay pérdida de datos irrecuperable si el nodo falla antes de la primera ejecución real. Ejecutar cuando se decida incorporar el registry a la rotación de copias de seguridad (mejora 1 de `docs/22-mejoras-futuras.md`) — ver también `docs/12-backups-y-restore.md`.

## 4. Alerta de espacio en disco — cubierta por la mejora 3

**Completada** (mejora 3 de `docs/22-mejoras-futuras.md`, cerrada 2026-09-01, `docs/14-monitorizacion-completa-cluster.md`) — la regla genérica de espacio en disco (`pi-obs/config/grafana/alerting/disk-space.yml`, `node_filesystem_avail_bytes`) incluye `/mnt/nfs-data` (donde vive `registry`) entre los sistemas de ficheros vigilados en los 5 nodos que lo montan, conectada a ntfy (`docs/34-ntfy-notificaciones.md`) — sin necesidad de una alerta específica para el registry.

## Despliegue

Los tres scripts están sincronizados en `/srv/homelab/shared/scripts/` de los 5 nodos siempre encendidos (`retaco`, `pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils`), mismo patrón que el resto de `shared/scripts/`. A diferencia de la nota original de este documento ("solo son útiles en retaco, único nodo con el registry") — ya no es así desde que el registry perdió su `constraints` de nodo: **el GC y el backup son útiles desde cualquiera de los 5**, mientras tengan `/mnt/nfs-data` montado.
