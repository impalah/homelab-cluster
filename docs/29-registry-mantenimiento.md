# 29 — Mantenimiento de registry.home.arpa

Fecha: 2026-08-15

Implementación de la mejora 8 de `docs/22-mejoras-futuras.md` ("Registry — limpieza y garbage collection"), con el alcance decidido explícitamente al implementarla: **todo manual, nada programado por cron**. `registry.home.arpa` (`registry:2.8.3` en `retaco`, ver `docs/05-instalacion-retaco.md` sección 5.3) no sobrescribe capas antiguas al recibir un `docker push` con el mismo tag — solo deja de referenciarlas; sin limpieza periódica, el disco crece sin límite.

## 1. Garbage collection — `shared/scripts/registry-garbage-collect.sh`

Recolecta (borra de disco) las capas ya huérfanas (sin ningún tag/manifest que las referencie).

```bash
bash /srv/homelab/shared/scripts/registry-garbage-collect.sh                     # dry-run (no borra nada)
bash /srv/homelab/shared/scripts/registry-garbage-collect.sh retaco registry --apply   # borra de verdad
```

- Por defecto en modo `--dry-run` — solo lista qué se borraría, hace falta `--apply` explícito.
- Para el contenedor `registry` durante la ejecución (`docker compose stop` + `docker compose run --rm registry bin/registry garbage-collect ...` + `docker compose start` vía `trap` en el `EXIT`, así se reinicia siempre aunque el propio GC falle a medias) — el comando oficial de la imagen exige que el registry no reciba pushes mientras corre, o corrompe el índice.
- **Solo ejecución manual, a propósito** — no hay cron ni systemd timer. El propio requisito de "sin pushes concurrentes" hace arriesgado automatizarlo sin supervisión en un clúster con pocos pushes reales; mejor revisar el dry-run a mano cada vez.
- Recolecta blobs ya huérfanos — no decide qué tags conservar. Para liberar espacio de verdad primero hay que podar tags antiguos (punto 2).

## 2. Política de retención — `shared/scripts/registry-prune-tags.sh`

Decisión: **3 versiones antiguas por imagen**, además de `latest` (hasta 4 tags vivos por repositorio). Actúa vía la API HTTP v2 del registry (el binario `bin/registry` no tiene un subcomando para borrar tags individuales, solo para el GC de blobs).

```bash
REGISTRY_USER=admin REGISTRY_PASSWORD=<credencial> bash /srv/homelab/shared/scripts/registry-prune-tags.sh              # dry-run, KEEP=3
REGISTRY_USER=admin REGISTRY_PASSWORD=<credencial> bash /srv/homelab/shared/scripts/registry-prune-tags.sh --apply 3    # borra de verdad
```

- Credencial: el usuario compartido de `registry.home.arpa` (htpasswd, ver `docs/05-instalacion-retaco.md` sección 5.3) — guardada en Vaultwarden ("Docker Registry (registry.home.arpa)"), **nunca hardcodeada** en el script ni en este documento.
- Por repositorio: ordena los tags de versión (excluyendo `latest`) con `sort -V` descendente, conserva los `KEEP` (3 por defecto) más recientes, y borra el manifest (`DELETE /v2/<repo>/manifests/<digest>`) de cualquier tag más antiguo.
- **Nunca borra el tag que comparte digest con `latest`** — comprobado explícitamente antes de cada delete, para no desreferenciar accidentalmente la imagen actual solo porque su tag de versión numérica también cae fuera de la ventana de retención.
- Maneja manifest lists multi-arch (Accept: `manifest.list.v2+json` / `oci.image.index.v1+json`, además de `manifest.v2+json`) — necesario para apikey-service/markitdown-service/capataz-api/capataz-runner, todos multi-arch (`docs/28-capataz-consola-automatizacion.md`).
- **Solo ejecución manual, a propósito** — mismo motivo que el GC: es una operación destructiva sobre un registry con pocas imágenes, mejor revisar el dry-run que automatizarla sin supervisión.
- Solo desreferencia tags — no libera espacio por sí solo. Ejecutar `registry-garbage-collect.sh --apply` después para recuperar el disco de verdad.
- Verificado en vivo (dry-run, 2026-08-15) contra los 9 repositorios reales del clúster: ninguno tenía todavía más de 3 versiones antiguas, así que no había nada que podar — confirmado también que con `KEEP=1` detecta y ordena correctamente los tags a borrar de `crawl4ai-scraper-service` (el único repo con 3+ versiones hoy: `0.1.2`/`0.1.1`/`0.1.0`), sin llegar a aplicar el borrado.

## 3. Copia de seguridad — `shared/scripts/backup-registry.sh`

```bash
bash /srv/homelab/shared/scripts/backup-registry.sh              # nodo=retaco, contenedor=registry
```

- Mismo patrón que `backup-vaultwarden.sh`: para el contenedor unos segundos, empaqueta `registry/{data,auth}` con `tar`, reinicia — evita capturar un blob a medio escribir. Incluye `auth/` (el `htpasswd`): sin él, restaurar solo `data/` deja un registry al que nadie puede autenticarse.
- Genera `/srv/homelab/backups/retaco/registry_<fecha>.tar.gz` — no hay script de restauración dedicado todavía (simétrico a `restore-postgres.sh`/`restore-vaultwarden.sh`); restaurar es parar `registry`, vaciar `registry/{data,auth}` y extraer el `tar.gz` ahí, luego arrancar de nuevo.
- **Preparado pero SIN EJECUTAR todavía** — decisión explícita al implementar esta mejora: las imágenes son reconstruibles desde el código fuente (`services/` de este repo, o el repo externo de Capataz), así que no hay pérdida de datos irrecuperable si el nodo falla antes de la primera ejecución real. Ejecutar cuando se decida incorporar el registry a la rotación de copias de seguridad (mejora 1 de `docs/22-mejoras-futuras.md`) — ver también `docs/12-backups-y-restore.md`.

## 4. Alerta de espacio en disco — diferida a la mejora 3

**No implementada aquí, a propósito.** El punto 4 original de la mejora 8 ("alerta de espacio en disco específica si crece más de lo esperado") se resuelve con el mismo patrón genérico de alertas de disco que ya cubre la mejora 3 de `docs/22-mejoras-futuras.md` ("Alertas de espacio en disco", regla Grafana sobre `node_filesystem_avail_bytes`) — no tiene sentido montar una alerta específica para `registry.home.arpa` antes de que exista la alerta genérica por nodo. Cuando se aborde la mejora 3, `retaco` (donde vive el registry) queda cubierto sin trabajo adicional.

## Despliegue

Los tres scripts están sincronizados en `/srv/homelab/shared/scripts/` de los 5 nodos siempre encendidos (`retaco`, `pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils`), mismo patrón que el resto de `shared/scripts/` — aunque solo son útiles en `retaco` (único nodo con el registry), se mantienen sincronizados en todos por consistencia con la convención ya establecida en este repo.
