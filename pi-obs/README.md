# pi-obs — Observabilidad

**IP:** `192.168.1.171`  
**Hardware:** Raspberry Pi 5 (8 GB RAM recomendado)

## Servicios

| Servicio | Puerto (host) | URL pública |
|---|---|---|
| otel-collector | 4317 (gRPC), 4318 (HTTP) | — (receptor interno) |
| prometheus | 127.0.0.1:9090 | https://prometheus.home.arpa |
| grafana | 127.0.0.1:3000 | https://grafana.home.arpa |
| loki | 127.0.0.1:3100 | — (interno) |
| tempo | 127.0.0.1:3200 | — (interno) |
| node-exporter | 127.0.0.1:9100 | — (consultado por Prometheus) |
| cadvisor | 127.0.0.1:8080 | — (consultado por Prometheus) |
| postgres-exporter | 127.0.0.1:9187 | — (consultado por Prometheus) |
| watchtower | — | Auto-actualiza node-exporter/cadvisor/postgres-exporter/portainer-agent — ver `docs/16-mantenimiento-actualizaciones.md` |

> Nota: otel-collector expone sus puertos 4317/4318 en todas las interfaces (0.0.0.0) para recibir telemetría de otros nodos del clúster.

> Este nodo también ejecuta, por cron (`03:30` diario), `shared/scripts/check-image-updates.sh` — revisa por SSH todo el clúster en busca de imágenes Docker desactualizadas (las que no auto-actualiza Watchtower) y expone el resultado como métrica Prometheus mediante el *textfile collector* de `node-exporter`. Panel: `https://grafana.home.arpa/d/homelab-actualizaciones-pendientes/`. Detalle completo en `docs/16-mantenimiento-actualizaciones.md`.

## Arranque rápido

```bash
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pi-obs
cp .env.example .env
nano .env    # Ajustar GF_ADMIN_PASSWORD y POSTGRES_EXPORTER_DSN
docker compose up -d
docker compose ps
```

## Configuración de archivos

```
pi-obs/
├── docker-compose.yml
├── .env.example
├── README.md
└── config/
    ├── otel-collector.yaml     ← pipelines OTLP → Loki/Tempo/Prometheus
    ├── prometheus.yml          ← jobs de scrape
    ├── loki.yaml               ← retención 14 días
    ├── tempo.yaml              ← retención 72h trazas
    └── grafana/
        ├── datasources.yml         ← datasources aprovisionadas automáticamente
        ├── alerting/
        │   └── undervoltage.yml    ← alerta de baja tensión (undervoltage) en los nodos Raspberry Pi
        └── dashboards/
            ├── dashboards.yml          ← proveedor de dashboards por fichero
            └── json/
                └── actualizaciones-pendientes.json  ← panel de imágenes Docker desactualizadas
```

## Envío de telemetría desde otros nodos

Configurar en cada servicio instrumentado:

```bash
OTEL_EXPORTER_OTLP_ENDPOINT=http://192.168.1.171:4317
OTEL_SERVICE_NAME=<nombre-servicio>
```

## Post-arranque Grafana

1. Acceder: `https://grafana.home.arpa` → admin / valor de `GF_ADMIN_PASSWORD`
2. Verificar datasources: **Configuration → Data Sources** → todos en estado **OK**
3. Importar dashboards recomendados:
   - Node Exporter Full: ID `1860`
   - Docker cAdvisor: ID `14282`
   - PostgreSQL: ID `9628`
4. Alertas: **Alerting → Alert rules → carpeta "Homelab Alerts"** — la regla "Raspberry Pi - Undervoltage detectado" aprovisionada por `config/grafana/alerting/undervoltage.yml` (ver `docs/14-monitorizacion-completa-cluster.md`). Es solo para consulta: no hay ningún canal de notificación configurado, así que no avisa por email/push a ningún sitio — hay que entrar a esa pantalla para ver si está en estado "Firing".
5. Dashboards → carpeta **Homelab** → **Actualizaciones pendientes** — aprovisionado por `config/grafana/dashboards/`, ver `docs/16-mantenimiento-actualizaciones.md`.
