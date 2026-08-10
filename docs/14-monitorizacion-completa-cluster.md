# 14 — Monitorización completa del clúster (todos los nodos en Grafana)

## Contexto

`node-exporter` y `cadvisor` se ejecutan en **todos** los nodos (definición común en `docs/04-servicios-comunes.md`) — este documento cubre la parte específica de este tema: cómo Prometheus (en `pi-obs`) recopila sus métricas de todos ellos, los dashboards resultantes y las alertas configuradas.

## Prometheus: scrape targets

`pi-obs/config/prometheus.yml`:

```yaml
  - job_name: node-exporter-ryzen
    static_configs:
      - targets: ["192.168.1.150:9100"]
        labels:
          node: ryzen

  - job_name: cadvisor-ryzen
    static_configs:
      - targets: ["192.168.1.150:8081"]
        labels:
          node: ryzen

  # ... mismo patrón para retaco (192.168.1.174), pi-dns (192.168.1.170),
  # pi-sonar (192.168.1.172) y pi-utils (192.168.1.173)
```

Aplicar sin reiniciar el contenedor (Prometheus se ejecuta con `--web.enable-lifecycle`):

```bash
cp /srv/homelab/pi-obs/config/prometheus.yml /srv/homelab/pi-obs/prometheus/prometheus.yml
curl -X POST http://localhost:9090/-/reload
```

### ⚠️ Aviso específico para pi-dns (red con IPs fijas)

`pi-dns-net` asigna IPs fijas a `unbound`/`pihole`/`nginx`/`apikey-service`. Si al ejecutar `docker compose up -d` Docker recrea `pihole` en la misma operación en que crea `node-exporter`/`cadvisor` (que no piden IP fija), existe una ventana de carrera donde `node-exporter` puede auto-asignarse la IP que `pihole` necesita. Síntoma: `pihole` se queda en `Created` sin arrancar.

**Solución si ocurre:**

```bash
docker rm -f node-exporter
docker compose up -d pihole          # reclama su IP fija primero
docker compose up -d node-exporter   # ahora coge la siguiente IP libre
```

---

## Verificar

### Targets en Prometheus

```
https://prometheus.home.arpa/targets
```

Desde un navegador (mejora 25, `docs/27-authentik-sso.md`) esto ya pide login de Authentik primero — normal, es justo lo que protege ahora. Para consultarlo desde script/`curl`, ese login interactivo no vale — usar la IP directa del nodo en la LAN en su lugar (sin pasar por nginx/Authentik, mismo criterio que `check-health.sh`):

```bash
curl -s http://192.168.1.171:9090/api/v1/targets | \
  jq -r '.data.activeTargets[] | "\(.labels.job) \(.labels.node // "-") \(.health)"'
```

### check-health.sh

```bash
bash /srv/homelab/shared/scripts/check-health.sh ryzen
bash /srv/homelab/shared/scripts/check-health.sh pi-dns
bash /srv/homelab/shared/scripts/check-health.sh pi-sonar
bash /srv/homelab/shared/scripts/check-health.sh pi-utils
```

### Dashboards en Grafana

Ver `docs/08-instalacion-pi2-observabilidad.md` sección 7 para la lista completa (Node Exporter Full, Docker/cAdvisor, PostgreSQL Overview, Loki Logs). Ambos dashboards de sistema traen selector de `instance`/`job` — los 6 nodos aparecen ahí, no solo `pi-obs`.

---

## Alertas en Grafana

### Baja tensión (undervoltage) en nodos Raspberry Pi

Aprovisionada por `pi-obs/config/grafana/alerting/undervoltage.yml`.

**Cómo funciona:**

- `node-exporter` expone `node_hwmon_in_lcrit_alarm_volts` (chip `firmware_raspberrypi_hwmon`) en cada Raspberry Pi — mismo sensor que hace que el kernel imprima `Undervoltage detected!` (`docs/13-troubleshooting.md`). `0` en condiciones normales, `1` durante la alarma.
- La regla (**Alerting → Alert rules → "Homelab Alerts" → "Raspberry Pi - Undervoltage detectado"**) consulta cada 10s y pasa a **Firing** en cuanto el valor es mayor que 0 en cualquier nodo (`for: 0s`, sin gracia).
- `ryzen` no tiene esta métrica (no es una Raspberry Pi) — la regla no evalúa nada para ese nodo.

**Importante — solo de consulta, no envía avisos activos:** sin *contact point* ni política de notificación (no hay SMTP ni ningún otro canal montado). Hay que entrar manualmente a **Alerting → Alert rules** para comprobar el estado.

**Limitación conocida:** los picos de baja tensión muy breves pueden no quedar capturados si Prometheus no consultó las métricas justo en ese instante — garantiza detectar el caso sostenido, no necesariamente uno puntual.

```bash
curl -s 'http://192.168.1.171:9090/api/v1/query?query=node_hwmon_in_lcrit_alarm_volts' | jq .
```

> Alerta de espacio en disco (mismo patrón, pendiente de implementar) y canal de notificación proactivo (ntfy): ver `docs/22-mejoras-futuras.md`, puntos 3 y 4.
