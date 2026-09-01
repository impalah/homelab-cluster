# 16 — Mantenimiento: actualizaciones de sistema y de contenedores

Gestión centralizada de dos cosas distintas, con estrategias distintas porque el riesgo es distinto:

1. **Sistema operativo (apt)** — parches de seguridad automáticos + actualización completa bajo demanda.
2. **Imágenes Docker** — auto-actualización solo para servicios sin estado; para todo lo demás, solo aviso en Grafana, la actualización siempre es manual.

---

## 1. Sistema operativo

### 1.1 Parches de seguridad automáticos (`unattended-upgrades`)

Activo en los seis nodos. Configuración en `shared/config/apt/`:

- `51-homelab-unattended.conf` — deja el valor por defecto de Ubuntu (solo `-security`/ESM, no `-updates` general). `Automatic-Reboot "false"` explícito — **ningún nodo se reinicia solo**.
- `20auto-upgrades.conf` — activa los temporizadores periódicos. Sin esto, `unattended-upgrades` puede estar instalado pero no ejecutarse nunca — justo lo que se encontró desactivado en `pi-sonar` y `pi-utils` al auditar el clúster.

```bash
sudo bash /srv/homelab/shared/scripts/setup-unattended-upgrades.sh
```

```bash
systemctl list-timers apt-daily.timer apt-daily-upgrade.timer
cat /var/log/unattended-upgrades/unattended-upgrades.log
```

### 1.2 Actualización completa bajo demanda

```bash
bash /srv/homelab/shared/scripts/update-os.sh <nodo|all>
```

- Actualiza, limpia paquetes huérfanos, **avisa si hace falta reiniciar** — nunca reinicia solo.
- Con `all`: `ryzen retaco pi-obs pi-sonar pi-utils pi-dns` — **`pi-dns` siempre el último**.
- Requiere ejecutarse desde un equipo con SSH a todos los nodos (`ryzen`/`mole`).
- ⚠️ **`pinchi` no está en esta lista** (ni en `setup-unattended-upgrades.sh`) — se incorporó al clúster (mejora 30) después de escribirse estos dos scripts y nunca se añadió. Confirmado en vivo (2026-09-01, auditando la mejora 36) que `pinchi` ya trae `unattended-upgrades` activo por defecto de la instalación base de Ubuntu Server, pero **sin** la configuración explícita del repo (`51-homelab-unattended.conf`/`20auto-upgrades.conf`) — funciona, pero no de forma verificada/uniforme con el resto. Pendiente, no bloqueante: añadir `pinchi` a los mapas de nodos de ambos scripts.

⚠️ **`pi-dns` es el único punto de fallo del DNS de toda la LAN.** Tras actualizarlo, coordinar el reinicio con cuidado — ver `docs/13-troubleshooting.md`.

### 1.3 Vigilancia y alertas del estado de parcheo (mejora 36)

Hasta la mejora 36 (`docs/22-mejoras-futuras.md`, cerrada 2026-09-01), saber si un nodo tenía parches de seguridad pendientes o necesitaba reinicio exigía entrar por SSH a cada uno — sin métrica, sin panel, sin alerta. `shared/scripts/check-os-updates.sh` cierra ese hueco, con un diseño distinto a `check-image-updates.sh` (2.2 más abajo): en vez de centralizarse por SSH desde `pi-obs`, **corre localmente por cron en cada uno de los 7 nodos** (los 6 "de siempre" más `pinchi`), escribiendo dos métricas en el *textfile collector* de su propio `node-exporter`:

- `node_apt_security_updates_pending` — nº de paquetes `-security` pendientes (`apt list --upgradable`).
- `node_reboot_required` — 1 si `/var/run/reboot-required` existe, 0 si no.

```bash
bash /srv/homelab/shared/scripts/check-os-updates.sh   # local, cron diario 07:15 en los 7 nodos
```

**Prerrequisito confirmado en vivo, no asumido**: el *textfile collector* de `node-exporter` (`--collector.textfile.directory` + bind-mount de `/srv/homelab/node-exporter-textfile`) ya estaba provisionado de fábrica en los 5 nodos del stack Swarm `common` (dejado preparado a propósito para esta mejora, ver el comentario en `docker-swarm/stacks/common/docker-compose.yml`), pero **no** en `ryzen` ni en `pi-dns` (Compose clásico) — añadido a ambos como parte de esta mejora.

**Panel en Grafana**: `homelab-actualizaciones-pendientes` (mismo dashboard que las imágenes Docker, sección 2.2), paneles nuevos "Nodos con reinicio pendiente" y "Parcheo del sistema operativo por nodo".

**Alertas** (`pi-obs/config/grafana/alerting/os-patching.yml`, conectadas a ntfy — mejora 4, `docs/34-ntfy-notificaciones.md`): reinicio pendiente sostenido 3 días (1 día para `pi-dns`, con severidad `critical` en vez de `warning` — único punto de fallo del DNS, punto 4 de la mejora) y más de 20 actualizaciones de seguridad acumuladas sostenidas 3 días (umbral por encima del ruido de fondo normal de `unattended-upgrades`, que corre a diario). Ninguna de las dos reinicia nada — solo avisa, mismo principio que el resto de este documento.

⚠️ **Bug real de infraestructura encontrado y corregido implementando esta mejora, sin relación directa con el parcheo del SO**: los puertos de `node-exporter`/`cadvisor` en el stack `common` estaban en `mode: ingress` (la malla de Swarm podía reenviar una petición a la IP de un nodo hacia el node-exporter de OTRO nodo cualquiera), lo que podía mezclar la atribución de nodo de cualquier métrica de esos dos exporters desde la migración a Swarm. Corregido a `mode: host` — detalle completo, cómo se encontró y el segundo incidente real al aplicar el fix (colisión de puerto por la reserva `ingress` global al swarm) en `docs/31-docker-swarm.md`.

---

## 2. Imágenes Docker

### 2.1 Watchtower — auto-actualización, SOLO servicios sin estado

Un `watchtower` por nodo (seis en total, ver `docs/04-servicios-comunes.md`), vigilando solo el Docker local de su host. `WATCHTOWER_LABEL_ENABLE=true`: **solo toca contenedores con la label** `com.centurylinklabs.watchtower.enable=true`.

Esa label está puesta **únicamente** en:

| Contenedor | Nodos |
|---|---|
| `node-exporter` | los seis |
| `cadvisor` | los seis |
| `portainer-agent` | los seis |
| `postgres-exporter` | pi-obs |

Todo lo demás — `postgres-main`, `n8n-main`, `qdrant`, `registry`, `sonarqube`, `vaultwarden`, `portainer` (servidor), `n8n-aux`, `rsshub`, `markitdown-service`, `pihole`, `unbound`, `nginx`, `apikey-service`, `ollama`, `open-webui`, `whisper-service`, `vllm`, `comfyui` — **nunca se auto-actualiza**. Son servicios con estado (bases de datos, configuración, credenciales, workflows, modelos cargados) donde una actualización automática sin supervisión puede traer una migración de esquema rota o un tiempo de inactividad en el peor momento.

Programación: `04:00` cada nodo, con limpieza de imágenes antiguas (`WATCHTOWER_CLEANUP=true`).

**Añadir un servicio nuevo a la auto-actualización:**
```yaml
labels:
  - "com.centurylinklabs.watchtower.enable=true"
```
Solo si el servicio es genuinamente sin estado.

**Verificar qué vigila un watchtower concreto:**
```bash
docker logs watchtower --tail=20
```

### 2.2 Aviso de imagen nueva para lo que NO se auto-actualiza

`shared/scripts/check-image-updates.sh`, cron diario (`03:30`) **en `pi-obs`**, revisa por SSH cada nodo y compara el digest de cada contenedor sin label de Watchtower contra el digest actual del registro para el mismo tag.

Resultado como métrica Prometheus (*textfile collector*) en `/srv/homelab/pi-obs/node-exporter-textfile/image-updates.prom`.

**Panel en Grafana:** `https://grafana.404labo.net/d/homelab-actualizaciones-pendientes/actualizaciones-pendientes`.

**Acceso a `ryzen` desde `pi-obs`:** se instaló y activó `openssh-server` en `ryzen` (no lo tenía) y se generó una clave SSH dedicada en `pi-obs` (`pi-obs-cluster-admin`), autorizada en el resto de nodos.

**Limitaciones conocidas:**
- Detecta que el **mismo tag** se reconstruyó — **no** que exista un **tag de versión nuevo** para una imagen fijada (p. ej. no avisa de `vaultwarden/server:1.37.0` mientras está en marcha la `1.36.0`). Revisar el changelog de vez en cuando, sobre todo Vaultwarden.
- No cubre imágenes construidas localmente sin publicar (hoy solo `whisper-service` — `apikey-service`/`markitdown-service` sí se publican en `registry.404labo.net` desde hace tiempo, esta limitación quedó desactualizada en algún punto y no se había corregido hasta ahora) — se actualiza con `git pull` + rebuild manual.
- Docker Hub limita a 100 peticiones/6h por IP en modo anónimo.
- ⚠️ **`pinchi` no estaba en el mapa de nodos de este script** — se incorporó al clúster (mejora 30) después de escribirse, y como además aloja tareas Swarm sin `constraints` de nodo (`registry`, `ntfy`...) cualquiera que aterrizara ahí quedaba invisible a esta vigilancia. Añadido el 2026-09-01 (mejora 36, punto 5 — "continuación en Swarm"). **Pendiente**: la clave SSH de `pi-obs` todavía no está autorizada en `pinchi` (acción de seguridad, dejada fuera a propósito de ese cambio, pendiente de confirmación explícita) — hasta entonces el script trata `pinchi` como nodo inalcanzable (`WARN`, sin romper el resto de la ejecución).

```bash
bash /srv/homelab/shared/scripts/check-image-updates.sh
```

### 2.3 Actualizar manualmente un servicio con estado

```bash
bash /srv/homelab/shared/scripts/update-stack.sh <nodo> [fichero-compose]
```

Revisar el changelog **antes** de tirar de la imagen nueva, especialmente Postgres, Qdrant, SonarQube, n8n y Vaultwarden.

---

## 3. Resumen de responsabilidades

| Qué | Cómo | Automático? |
|---|---|---|
| Parches de seguridad del SO | `unattended-upgrades` | Sí, diario, sin reinicio |
| Actualización completa del SO | `update-os.sh` | No, bajo demanda |
| Reinicio tras actualizar el SO | Manual | No, nunca automático |
| Vigilancia de parcheo del SO (mejora 36) | `check-os-updates.sh` + alerta Grafana → ntfy | Sí, cron diario local + aviso |
| node-exporter, cadvisor, portainer-agent, postgres-exporter | Watchtower | Sí, diario 04:00 |
| Resto (con estado, incl. vllm/comfyui) | Aviso en Grafana (`check-image-updates.sh`) | No, solo notifica (o nada, si es imagen local) |
| whisper-service (imagen local, único caso hoy) | `git pull` + rebuild manual | No |
