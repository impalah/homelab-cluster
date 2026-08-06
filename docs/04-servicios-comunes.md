# 04 — Servicios comunes a todos los nodos

Hay cuatro servicios que se repiten, casi sin cambios, en el `docker-compose.yml` de **todos** los nodos (o casi todos: se indica la excepción en cada caso). Se documentan aquí una sola vez, en vez de repetir la misma explicación en el documento de cada nodo; cada documento de nodo enlaza a este y solo detalla lo que tiene de distinto (puerto, red, algún volumen adicional).

## Diagrama

```mermaid
flowchart LR
    subgraph nodo["Cualquier nodo del clúster"]
        NE[node-exporter]
        CA[cadvisor]
        PA[portainer-agent]
        WT[watchtower]
    end

    NE -- métricas del host --> PROM[Prometheus\npi-obs]
    CA -- métricas de contenedores --> PROM
    PA -- socket Docker --> PORT[Portainer server\npi-utils]
    WT -- vigila imágenes con label --> DOCKER[(Docker local\nde ese nodo)]
```

## node-exporter — ¿para qué sirve?

Expone métricas del **sistema operativo del host** (CPU, RAM, disco, red, temperatura y voltaje en el caso de la Raspberry Pi) en formato Prometheus. No hace nada por sí mismo, solo expone `/metrics`; es Prometheus, en `pi-obs`, quien lo consulta periódicamente y convierte esos datos en series temporales que se pueden consultar desde Grafana.

```yaml
node-exporter:
  image: prom/node-exporter:v1.8.0
  container_name: node-exporter
  restart: unless-stopped
  labels:
    - "com.centurylinklabs.watchtower.enable=true"
  command:
    - "--path.procfs=/host/proc"
    - "--path.rootfs=/rootfs"
    - "--path.sysfs=/host/sys"
    - "--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)"
  volumes:
    - /proc:/host/proc:ro
    - /sys:/host/sys:ro
    - /:/rootfs:ro
  ports:
    - "9100:9100"
  networks:
    - <red-del-nodo>
  pid: host
```

**Puerto**: `9100` en todos los nodos, publicado a la LAN (en `0.0.0.0`, no en loopback), porque Prometheus vive en *otro* host (`pi-obs`) y necesita alcanzarlo por IP. La única excepción es el propio `pi-obs`: como Prometheus está en ese mismo nodo, su `node-exporter` puede quedarse en `127.0.0.1:9100`, sin que nadie externo lo necesite.

**`pid: host`**: necesario para que pueda ver los procesos del host real, y no solo los del propio contenedor.

En la Raspberry Pi 5 expone, además, la métrica `node_hwmon_in_lcrit_alarm_volts` (del chip `firmware_raspberrypi_hwmon`), que es la que hay detrás de la alerta de baja tensión — consulta `docs/14-monitorizacion-completa-cluster.md`.

## cadvisor — ¿para qué sirve?

Es el equivalente a `node-exporter`, pero para **contenedores Docker** en vez de para el sistema operativo: mide CPU, RAM, red y disco por cada contenedor individual, no de forma agregada por host. Junto con `node-exporter`, es lo que permite ver en Grafana "qué contenedor concreto se está comiendo la RAM", y no solo "este nodo está al 80 % de RAM".

```yaml
cadvisor:
  image: gcr.io/cadvisor/cadvisor:v0.55.1
  container_name: cadvisor
  restart: unless-stopped
  command:
    - "-disable_metrics=advtcp,cpu_topology,cpuset,hugetlb,memory_numa,process,referenced_memory,resctrl,sched,tcp,udp,disk,diskIO"
  labels:
    - "com.centurylinklabs.watchtower.enable=true"
  volumes:
    - /:/rootfs:ro
    - /var/run:/var/run:ro
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
    - /dev/disk/:/dev/disk:ro
  ports:
    - "8081:8080"
  networks:
    - <red-del-nodo>
  privileged: true
  cgroup: host
  devices:
    - /dev/kmsg
```

**Puerto `8081` (en el host) → `8080` (en el contenedor), y no `8080:8080`**: en `ryzen`, el puerto `8080` ya lo usa `open-webui`. Para no tener que hacer una excepción distinta solo en ese nodo, **todos** los nodos usan `8081:8080` por coherencia, aunque solo `ryzen` lo necesite en realidad.

**`privileged: true`**: cadvisor necesita acceso profundo al cgroup y al espacio de nombres del host para poder leer las métricas de todos los demás contenedores; no hay forma de acotarlo más sin perder esa visibilidad.

**`cgroup: host`**: desde Docker 20.10, los contenedores arrancan por defecto con `cgroupns: private` (namespace de cgroups aislado). Sin esta opción, cadvisor queda encerrado en su propio namespace y no puede resolver los cgroups de los contenedores hermanos — el síntoma es que solo ve las métricas del árbol de cgroups del host (`system.slice`, `user.slice`, etc.) pero no identifica nombre, imagen ni labels (`container_label_com_docker_compose_project`, etc.) de los contenedores Docker reales, haciendo imposible filtrar por contenedor en Grafana.

**`-disable_metrics=...,disk,diskIO`**: mantiene los grupos de métricas que cadvisor ya desactiva por defecto (`advtcp,cpu_topology,cpuset,hugetlb,memory_numa,process,referenced_memory,resctrl,sched,tcp,udp` — especificar `-disable_metrics` sustituye la lista por defecto entera, no la amplía, así que hay que repetirla) y añade `disk,diskIO`. Los grupos `disk`/`diskIO` son los que activan el escaneo de uso de disco por contenedor (`container_fs_*`) — caro en un nodo con muchos contenedores/capas, y no es una prioridad de monitorización en este clúster. Desactivarlo bajó drásticamente el consumo de RAM propio de cadvisor (visto en producción: 707MB → 47MB en `pi-utils`, 463MB → 23MB en `retaco`).

## promtail — ¿para qué sirve?

Envía los logs (stdout/stderr) de **todos** los contenedores Docker de este nodo a Loki, en `pi-obs`, para poder verlos y buscarlos desde Grafana (**Explore** → datasource **Loki**). Sin esto, los logs de un contenedor solo existen en `docker logs <container>` de ese nodo concreto — no hay forma de verlos ni correlacionarlos desde Grafana.

Usa el descubrimiento de contenedores de Promtail (`docker_sd_configs` contra `docker.sock`) en vez de una lista fija — cualquier contenedor nuevo en el nodo se detecta y se empieza a scrapear automáticamente, sin tocar la configuración. No requiere ningún cambio en el código ni en el `docker-compose.yml` de los servicios monitorizados: es puramente un agente de lectura, el driver de logging de cada contenedor sigue siendo el `json-file` por defecto, así que `docker logs` sigue funcionando exactamente igual que siempre.

```yaml
promtail:
  image: grafana/promtail:3.0.0
  container_name: promtail
  restart: unless-stopped
  labels:
    - "com.centurylinklabs.watchtower.enable=true"
  volumes:
    - /srv/homelab/<nodo>/promtail/promtail-config.yaml:/etc/promtail/config.yaml:ro
    - /srv/homelab/<nodo>/promtail/data:/data
    - /var/run/docker.sock:/var/run/docker.sock:ro
    - /var/lib/docker/containers:/var/lib/docker/containers:ro
  command: -config.file=/etc/promtail/config.yaml
  networks:
    - <red-del-nodo>
```

Config (`config/promtail/promtail-config.yaml`, un fichero por nodo — solo cambia el valor `node:` en `relabel_configs`):

```yaml
server:
  http_listen_port: 9080
  grpc_listen_port: 0

positions:
  filename: /data/positions.yaml

clients:
  - url: http://192.168.1.171:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_id']
        replacement: '/var/lib/docker/containers/$1/*.log'
        target_label: '__path__'
      - source_labels: ['__meta_docker_container_name']
        regex: '/(.*)'
        target_label: 'container'
      - source_labels: ['__meta_docker_container_label_com_docker_compose_project']
        target_label: 'compose_project'
      - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
        target_label: 'compose_service'
      - source_labels: ['__meta_docker_container_label_com_docker_compose_service']
        target_label: 'job'
      - target_label: 'node'
        replacement: '<nodo>'
    pipeline_stages:
      - docker: {}
```

**Label `job`**: además de `compose_service`, se repite explícitamente como `job` — es el nombre de label que casi todo el ecosistema Grafana/Loki asume por convención para "qué servicio es este log" (igual que Prometheus con las métricas). El pipeline OTLP de `apikey-service` (sección 9 de `docs/08-instalacion-pi2-observabilidad.md`) también pone `job`, así que con esto **ambas rutas de logs (Promtail y OTLP) se pueden consultar con el mismo nombre de label**, sin tener que acordarse de cuál usa cada contenedor.

**`docker_sd_configs` + `__path__` construido a mano**: Promtail descubre los contenedores vía la API de Docker (igual que `docker ps`), pero no sabe por sí solo dónde está el fichero de log de cada uno — el `relabel_config` sobre `__meta_docker_container_id` reconstruye la ruta real (`/var/lib/docker/containers/<id>/<id>-json.log`, usando el glob `*.log` para no repetir el ID dos veces).

**`pipeline_stages: - docker: {}`**: stage integrado de Promtail que parsea el formato JSON que usa el driver `json-file` de Docker (`{"log":"...","stream":"...","time":"..."}`), separando el mensaje real, el stream (`stdout`/`stderr`, como label) y el timestamp — sin esto, cada línea en Loki sería el JSON crudo de Docker en vez del log real de la aplicación.

**Requiere que Loki esté accesible por la LAN** (`pi-obs/docker-compose.yml`, puerto `3100` — antes solo en `127.0.0.1`, cambiado a `3100:3100` igual que Prometheus, ya que Promtail corre en los otros 5 nodos y necesita alcanzarlo por red).

## portainer-agent — ¿para qué sirve?

Le da al servidor de Portainer (que hay uno solo, en `pi-utils` — ver `docs/10-instalacion-pi4-utils.md`) acceso al Docker de este nodo en concreto: arrancar y parar contenedores, ver registros, abrir una consola interactiva, todo desde la interfaz web y sin necesidad de SSH. El agente es el que hace el trabajo pesado (monta `docker.sock`); el servidor central solo habla con los agentes, nunca directamente con el Docker de los nodos remotos.

```yaml
portainer-agent:
  image: portainer/agent:2.42.0
  container_name: portainer-agent
  restart: unless-stopped
  labels:
    - "com.centurylinklabs.watchtower.enable=true"
  environment:
    AGENT_CLUSTER_ADDR: ""
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - /var/lib/docker/volumes:/var/lib/docker/volumes
  ports:
    - "9001:9001"
  networks:
    - <red-del-nodo>
```

⚠️ Monta `/var/run/docker.sock`, lo que da control total sobre Docker en ese host, equivalente en la práctica a acceso como root. Es aceptable en este clúster porque ya se exige estar dentro de la LAN doméstica; conviene tenerlo presente si `portainer.home.arpa` llegara a exponerse alguna vez fuera de la red de casa.

## watchtower — ¿para qué sirve?

Actualiza automáticamente los contenedores **sin estado** cuando aparece una imagen nueva para la misma etiqueta de versión, pero **solo** los que llevan explícitamente la etiqueta `com.centurylinklabs.watchtower.enable=true` (los cuatro de esta misma página —`node-exporter`, `cadvisor`, `portainer-agent`— y también `postgres-exporter`, en `pi-obs`). Todo lo demás (bases de datos, n8n, SonarQube, Vaultwarden, Ollama, etcétera) se actualiza siempre a mano, porque son servicios con estado en los que una actualización sin supervisión puede romper algo. Consulta `docs/16-mantenimiento-actualizaciones.md` para el detalle completo de la estrategia de actualizaciones.

```yaml
watchtower:
  image: nickfedor/watchtower:latest
  container_name: watchtower
  restart: unless-stopped
  environment:
    WATCHTOWER_LABEL_ENABLE: "true"
    WATCHTOWER_CLEANUP: "true"
    WATCHTOWER_SCHEDULE: "0 0 4 * * *"
    WATCHTOWER_INCLUDE_RESTARTING: "true"
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
  networks:
    - <red-del-nodo>
```

> Imagen `nickfedor/watchtower`, no `containrrr/watchtower` — el proyecto original está archivado (diciembre 2025); este es el fork activamente mantenido.

Se ejecuta a las `04:00` cada noche, en cada nodo, y vigila solo el Docker local de ese host: no existe un watchtower "central" para todo el clúster.

## Resumen de puertos

| Servicio | Puerto | Publicado a la LAN |
|---|---|---|
| node-exporter | 9100 | Sí (excepto en pi-obs, donde queda en `127.0.0.1`, ya que se consulta a sí mismo) |
| cadvisor | 8081→8080 | Sí (excepto en pi-obs, donde queda en `127.0.0.1`) |
| portainer-agent | 9001 | Sí, en los 6 nodos |
| watchtower | — | No expone ningún puerto |
| promtail | 9080 (interno) | No publicado — nadie necesita consultar la API propia de promtail, solo empuja datos hacia Loki |

Ninguno de estos cinco servicios pasa por `nginx` ni por `apikey-service`, porque no están pensados para que una persona acceda a ellos mediante el navegador con un nombre de host (`node-exporter` y `cadvisor` los consulta Prometheus directamente por IP; a `portainer-agent` lo consulta el servidor de Portainer; `watchtower` y `promtail` no exponen nada). Por eso tampoco aparecen en `docs/17-firewall-acceso-directo.md` como puertos que se puedan cerrar: cerrarlos rompería una integración legítima entre nodos, no supondría evitar el paso por nginx.
