# 11 — Operación diaria del clúster

> Para logs, reinicios, consola dentro de un contenedor o ver uso de CPU/RAM sin usar la terminal, **Portainer** (`https://portainer.home.arpa`) cubre gran parte de lo que hay en esta página desde una interfaz, para los seis nodos — ver `docs/10-instalacion-pi4-utils.md`. Los comandos de abajo siguen siendo la referencia para todo lo que no cubre la interfaz (copias de seguridad, cron, rotación de credenciales, etc.).

## Comandos habituales por nodo

### Ryzen (192.168.1.150)

Dos stacks independientes — ver `ryzen/README.md`: `docker-compose.yml` (IA, GPU) y `docker-compose.observability.yml` (host, sin `.env`). Los comandos sin `-f` afectan solo al primero (es el nombre por defecto de Compose).

```bash
cd /srv/homelab/ryzen

docker compose ps
docker compose -f docker-compose.observability.yml ps

docker compose logs -f
docker compose logs -f ollama
docker compose logs -f whisper-service

docker compose restart <servicio>

docker compose down
docker compose pull   # ver aviso más abajo
docker compose up -d

docker compose -f docker-compose.observability.yml down
docker compose -f docker-compose.observability.yml up -d
```

> ⚠️ `docker compose up -d` sin indicar un servicio arranca **todos** los del fichero — incluidos `vllm`/`comfyui`, que compiten por VRAM con `ollama`/`whisper-service`. Para alternar entre ellos, usar siempre `switch-llm-backend.sh` (GPU 0) y `switch-gpu1-backend.sh` (GPU 1), nunca `docker compose up -d <servicio>` suelto — ver `docs/07-instalacion-ryzen.md`.

> ⚠️ **`docker compose pull` antes de cada arranque del stack de IA.** Al pararse/arrancarse a demanda, `ollama/ollama:latest` puede quedar cacheada sin refrescar durante semanas.

> `n8n-main` no vive en `ryzen` — está en `retaco` para seguir funcionando (cron, webhooks) aunque este stack esté parado. Ver `docs/05-instalacion-retaco.md`.

### Retaco (192.168.1.174)

```bash
cd /srv/homelab/retaco && docker compose ps
docker compose logs -f postgres-main
docker compose logs -f n8n-main
docker compose logs -f qdrant

source /srv/homelab/retaco/.env
curl -s http://192.168.1.174:6333/collections -H "api-key: ${QDRANT_API_KEY}" | jq .
```

### pi-dns (192.168.1.170)

```bash
cd /srv/homelab/pi-dns && docker compose ps
docker compose logs -f nginx
docker compose logs -f pihole
docker compose logs -f apikey-service

docker exec nginx nginx -t
docker exec nginx nginx -s reload
```

> ⚠️ Si el cambio en `nginx.conf` llegó por `rsync`/`scp` (rename atómico), `nginx -s reload` **no** basta — el contenedor sigue viendo el inodo viejo del bind mount. Hace falta `docker compose up -d --force-recreate nginx`. Ver `docs/13-troubleshooting.md`.

### pi-obs (192.168.1.171)

```bash
cd /srv/homelab/pi-obs && docker compose ps
curl -X POST http://192.168.1.171:9090/-/reload
curl -s http://192.168.1.171:9090/api/v1/alerts | jq .
curl -s http://192.168.1.171:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'
```

### pi-sonar (192.168.1.172)

```bash
cd /srv/homelab/pi-sonar && docker compose ps
curl -s http://192.168.1.172:9000/api/system/status | jq .
docker compose logs -f sonarqube
```

### pi-utils (192.168.1.173)

```bash
cd /srv/homelab/pi-utils && docker compose ps
docker compose logs -f markitdown-service
docker compose logs -f n8n-aux
```

---

## Healthcheck global

> Todos los nodos exponen métricas de sistema (`node-exporter`) y de contenedores (`cadvisor`), recopiladas por Prometheus en pi-obs y visibles en Grafana — ver `docs/14-monitorizacion-completa-cluster.md`.

⚠️ **`check-health.sh` hace `docker inspect` y comprueba algún endpoint en
`127.0.0.1` — solo da resultados correctos ejecutado *localmente en el
propio nodo*, por SSH.** Lanzarlo desde otra máquina apuntando a un nodo
remoto por nombre da `[FAIL]` falsos en todos los checks de Docker (mira
el Docker del host donde se ejecuta el script, no el del nodo) y en los
endpoints `127.0.0.1` (Pi-hole en pi-dns, Loki/Tempo en pi-obs) — visto en
vivo, no es hipotético.

```bash
bash /srv/homelab/shared/scripts/check-health.sh ryzen   # local, sin ssh

for target in \
  "u-data@192.168.1.174:retaco" \
  "u-dns@192.168.1.170:pi-dns" \
  "u-obs@192.168.1.171:pi-obs" \
  "u-sonar@192.168.1.172:pi-sonar" \
  "u-utils@192.168.1.173:pi-utils"
do
  ssh_target="${target%%:*}"
  node="${target##*:}"
  echo "=== ${node} ==="
  ssh -o BatchMode=yes "${ssh_target}" "bash /srv/homelab/shared/scripts/check-health.sh ${node}"
done
```

O individualmente, por SSH al nodo en cuestión: `ssh <usuario>@<ip> "bash /srv/homelab/shared/scripts/check-health.sh <nodo>"`.

---

## Actualización de stacks

> Desde `docs/16-mantenimiento-actualizaciones.md`, gran parte de esto ya no hace falta a mano: Watchtower auto-actualiza los servicios sin estado en los seis nodos, y el resto avisa solo en el panel de Grafana **Actualizaciones pendientes**. Los comandos de abajo siguen siendo válidos para forzar una actualización puntual.

```bash
bash /srv/homelab/shared/scripts/update-stack.sh <nodo>

# ryzen tiene dos stacks independientes:
bash /srv/homelab/shared/scripts/update-stack.sh ryzen
bash /srv/homelab/shared/scripts/update-stack.sh ryzen docker-compose.observability.yml
```

El script: `docker compose pull` → `docker compose up -d` → `docker image prune -f`.

### Actualizar todos los nodos (secuencial, requiere SSH)

```bash
for node in pi-dns ryzen retaco pi-obs pi-sonar pi-utils; do
  echo "Actualizando $node..."
  ssh homelab@$node.home.arpa "bash /srv/homelab/shared/scripts/update-stack.sh $node"
done
```

> Actualizar `pi-dns` primero para garantizar resolución DNS durante el resto del proceso.

---

## Actualización del sistema operativo

Detalle completo en `docs/16-mantenimiento-actualizaciones.md`. Resumen:

```bash
bash /srv/homelab/shared/scripts/update-os.sh <nodo|all>
```

Nunca reinicia nada por sí solo — revisar el aviso `[REBOOT-REQUIRED]` y decidir cuándo reiniciar. Cuidado especial con `pi-dns` (único punto de fallo del DNS de la LAN).

---

## Gestión de recursos

```bash
docker stats --no-stream
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

docker system df
du -sh /srv/homelab/<nodo>/*/

docker system prune -f    # limpia imágenes, redes y volúmenes sin usar
docker image prune -f     # solo imágenes huérfanas, más seguro
```

---

## Gestión de modelos Ollama

```bash
docker exec ollama ollama list
docker exec ollama ollama pull <modelo>
docker exec ollama ollama rm <modelo>
docker exec ollama ollama show <modelo>
```

---

## Acceso por hostname (`*.home.arpa`) desde el PC de gestión

Para que `https://grafana.home.arpa` etc. resuelvan sin depender de que el router ya reparta pi-dns por DHCP — ver `docs/06-instalacion-pi1-dns.md` sección 8.1 (instrucciones `nmcli` para Ubuntu Desktop).

---

## Acceso SSH al clúster

```
Host ryzen
  HostName 192.168.1.150
  User homelab
  IdentityFile ~/.ssh/id_ed25519

Host retaco
  HostName 192.168.1.174
  User homelab
  IdentityFile ~/.ssh/id_ed25519

Host pi-dns
  HostName 192.168.1.170
  User homelab
  IdentityFile ~/.ssh/id_ed25519

Host pi-obs
  HostName 192.168.1.171
  User homelab
  IdentityFile ~/.ssh/id_ed25519

Host pi-sonar
  HostName 192.168.1.172
  User homelab
  IdentityFile ~/.ssh/id_ed25519

Host pi-utils
  HostName 192.168.1.173
  User homelab
  IdentityFile ~/.ssh/id_ed25519
```

```bash
ssh ryzen
ssh pi-obs
ssh ryzen "docker compose -f /srv/homelab/ryzen/docker-compose.yml ps"
```

---

## Cortafuegos — cerrar el acceso directo por IP y puerto

Servicios como `ollama.home.arpa` también son alcanzables directamente por IP y puerto, saltándose `apikey-service`:

```bash
bash shared/scripts/toggle-direct-access.sh <nodo|all> off      # cerrar
bash shared/scripts/toggle-direct-access.sh <nodo|all> on       # reabrir
bash shared/scripts/toggle-direct-access.sh <nodo|all> status   # ver estado
```

Requiere `bash shared/scripts/setup-firewall.sh <nodo>` una vez por nodo antes. Ver `docs/17-firewall-acceso-directo.md`.

---

## Rotación de credenciales

1. Editar el `.env` del nodo afectado.
2. Reiniciar los servicios dependientes: `docker compose up -d`.
3. Si es una clave de n8n (`N8N_ENCRYPTION_KEY`) o de `apikey-service`, **no cambiarla** una vez en uso — ver aviso específico en el documento de cada nodo.
