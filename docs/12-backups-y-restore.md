# 12 — Copias de seguridad y restauración

## Estrategia general

1. **Copia de seguridad de las bases de datos PostgreSQL** — volcados SQL (`pg_dump`) de cada instancia de Postgres.
2. **Copia de seguridad de los volúmenes de datos** — copia mediante `rsync`/`tar` de los directorios bajo `/srv/homelab/`.

Las copias de seguridad se guardan localmente en cada nodo, bajo `/srv/homelab/backups/` — todavía no hay copia automática fuera del nodo de origen (ver `docs/22-mejoras-futuras.md`, punto 1).

---

## Copia de seguridad de PostgreSQL

### Retaco — postgres-main

`postgres-main` vive en `retaco` y aloja **varias bases aisladas** (n8n, sonarqube, apikeys, authentik, y cualquier otra creada con `create-postgres-db.sh`) — hay que respaldar cada una por separado:

```bash
bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main n8n
bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main sonarqube
bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main apikeys
bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main authentik
```

Genera `/srv/homelab/backups/retaco/postgres-main_<db>_<fecha>.sql.gz`.

### Retaco — postgres-infisical

Instancia SEPARADA de `postgres-main` a propósito — no multi-tenant, solo Infisical (mejora 16, `docs/adr/0002-infisical-postgres-dedicado.md`):

```bash
bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-infisical infisical
```

Además del volcado SQL, `retaco/.env` guarda `ENCRYPTION_KEY`/`AUTH_SECRET` de Infisical — sin ellos, un volcado restaurado no sirve de nada (`ENCRYPTION_KEY` cifra todos los secretos guardados). Copiarlos también a Vaultwarden, no solo confiar en el `.env` del nodo.

## Restauración de PostgreSQL

```bash
bash /srv/homelab/shared/scripts/restore-postgres.sh retaco postgres-main n8n \
  /srv/homelab/backups/retaco/postgres-main_n8n_<fecha>.sql.gz
```

> Detener el servicio dependiente antes de restaurar:
> ```bash
> ssh retaco "cd /srv/homelab/retaco && docker compose stop n8n-main"
> ssh pi-sonar "docker compose -f /srv/homelab/pi-sonar/docker-compose.yml stop sonarqube"
> ```

---

## Copia de seguridad de Vaultwarden (pi-utils)

SQLite, no PostgreSQL — script propio porque SQLite en modo WAL no se copia en caliente de forma segura. Detalle completo en `docs/10-instalacion-pi4-utils.md`.

```bash
bash /srv/homelab/shared/scripts/backup-vaultwarden.sh
# → /srv/homelab/backups/pi-utils/vaultwarden_<fecha>.tar.gz

bash /srv/homelab/shared/scripts/restore-vaultwarden.sh /srv/homelab/backups/pi-utils/vaultwarden_<fecha>.tar.gz
```

---

## Copia de seguridad del registry (retaco)

Mismo patrón que Vaultwarden (para el contenedor, `tar` de `data/`+`auth/`, reinicia). Detalle completo (incluida la política de retención de tags y el garbage collection) en `docs/29-registry-mantenimiento.md`.

```bash
bash /srv/homelab/shared/scripts/backup-registry.sh
# → /srv/homelab/backups/retaco/registry_<fecha>.tar.gz
```

⚠️ **Script preparado pero sin ejecución todavía** (decisión explícita, mejora 8 de `docs/22-mejoras-futuras.md`) — las imágenes son reconstruibles desde el código fuente, así que no se ha incorporado aún a la rotación real de copias de seguridad. No hay `restore-registry.sh` dedicado: restaurar es parar `registry`, vaciar `registry/{data,auth}` en el nodo y extraer ahí el `.tar.gz`, luego arrancar de nuevo.

---

## Copia de seguridad de los volúmenes de datos

```bash
NODE=ryzen  # o retaco, pi-obs, pi-sonar, pi-utils
DATE=$(date +%Y%m%d-%H%M)

tar -czf /srv/homelab/backups/${NODE}/${NODE}-data-${DATE}.tar.gz \
  --exclude=/srv/homelab/${NODE}/postgres \
  /srv/homelab/${NODE}/
# Postgres se respalda por separado con pg_dump
```

| Incluir | Excluir |
|---|---|
| ollama/models, vllm/models, comfyui/models | postgres/data (usar pg_dump) |
| n8n/data | sonarqube/temp |
| qdrant/storage | grafana/data/sessions |
| grafana/data | loki/data/index (regenerable) |
| pihole/etc-pihole | |

---

## Automatización con cron

```bash
crontab -e
```

```cron
# Retaco: copia de seguridad de cada base aislada de postgres-main, a las 3:00
0 3 * * * /bin/bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main n8n >> /var/log/homelab-backup.log 2>&1
5 3 * * * /bin/bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main sonarqube >> /var/log/homelab-backup.log 2>&1
10 3 * * * /bin/bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main apikeys >> /var/log/homelab-backup.log 2>&1
15 3 * * * /bin/bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main authentik >> /var/log/homelab-backup.log 2>&1

# pi-utils: vaultwarden, a las 4:00
0 4 * * * /bin/bash /srv/homelab/shared/scripts/backup-vaultwarden.sh >> /var/log/homelab-backup.log 2>&1
```

> A día de hoy **no hay ningún cron activo** en ningún nodo — este bloque es la referencia para cuando se programe (pendiente en el backlog, `docs/22-mejoras-futuras.md`, punto 1).

---

## Sincronización a almacenamiento externo (opcional, no configurado todavía)

```bash
# Opción A: rsync a un NAS local
rsync -avz --delete /srv/homelab/backups/ homelab@nas.home.arpa:/backups/homelab/

# Opción B: rclone a la nube
rclone config
rclone sync /srv/homelab/backups/ remote:homelab-backups/
```

---

## Retención de las copias de seguridad

```bash
find /srv/homelab/backups/ -name "*.sql.gz" -mtime +30 -delete
find /srv/homelab/backups/ -name "*.tar.gz" -mtime +30 -delete
```

---

## Lista de comprobación para la recuperación ante desastres

1. [ ] Reinstalar Ubuntu Server siguiendo `docs/03-instalacion-base-ubuntu-raspi.md` + el documento de instalación del nodo (`docs/05` a `docs/10`).
2. [ ] Clonar el repositorio de configuraciones en `/srv/homelab/`.
3. [ ] Ejecutar `prepare-host.sh <nodo>` para recrear los directorios.
4. [ ] Restaurar la copia de seguridad de PostgreSQL con `restore-postgres.sh`.
5. [ ] Restaurar los datos de los volúmenes desde el `.tar.gz`.
6. [ ] `docker compose up -d`.
7. [ ] Verificar con `check-health.sh <nodo>`.
