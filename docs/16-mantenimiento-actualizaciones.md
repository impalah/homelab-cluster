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

⚠️ **`pi-dns` es el único punto de fallo del DNS de toda la LAN.** Tras actualizarlo, coordinar el reinicio con cuidado — ver `docs/13-troubleshooting.md`.

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

**Panel en Grafana:** `https://grafana.home.arpa/d/homelab-actualizaciones-pendientes/actualizaciones-pendientes`.

**Acceso a `ryzen` desde `pi-obs`:** se instaló y activó `openssh-server` en `ryzen` (no lo tenía) y se generó una clave SSH dedicada en `pi-obs` (`pi-obs-cluster-admin`), autorizada en el resto de nodos.

**Limitaciones conocidas:**
- Detecta que el **mismo tag** se reconstruyó — **no** que exista un **tag de versión nuevo** para una imagen fijada (p. ej. no avisa de `vaultwarden/server:1.37.0` mientras está en marcha la `1.36.0`). Revisar el changelog de vez en cuando, sobre todo Vaultwarden.
- No cubre imágenes construidas localmente sin publicar (`whisper-service`, `apikey-service`, `markitdown-service`) — se actualizan con `git pull` + rebuild manual.
- Docker Hub limita a 100 peticiones/6h por IP en modo anónimo.

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
| node-exporter, cadvisor, portainer-agent, postgres-exporter | Watchtower | Sí, diario 04:00 |
| Resto (con estado, incl. vllm/comfyui/apikey-service/markitdown-service) | Aviso en Grafana (`check-image-updates.sh`) | No, solo notifica (o nada, si es imagen local) |
| whisper-service, apikey-service, markitdown-service (imagen local) | `git pull` + rebuild manual | No |
