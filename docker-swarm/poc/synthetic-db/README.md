# PoC — Swarm de un solo nodo en `pinchi`

Valida, antes de tocar ningún otro nodo, dos cosas concretas (Fase 0 de `docs/31-docker-swarm.md`):

1. El patrón real que usará todo servicio con estado bajo Swarm: bind-mount local +
   `constraints: node.hostname==<nodo>`, para que el scheduler nunca reprograme el contenedor a
   otro sitio y los datos sobrevivan a un `docker service update --force`.
2. Que `docker stack deploy` acepta las claves que usan `node-exporter`/`cadvisor` hoy
   (`devices`, `privileged`, `cgroup: host`, `pid: host`) — el mayor riesgo técnico no verificado
   de toda la migración (mejora 33, punto 7).

Usa siempre datos **sintéticos** — nunca una copia de `postgres-main` ni de ninguna base real.

## Paso a paso

```bash
# 1. Swarm de un solo nodo en pinchi (si no está hecho ya)
bash ../../init/init-swarm.sh init

# 2. Directorios de datos en pinchi (mismo patrón que prepare-host.sh)
ssh u-forge@192.168.1.175 "mkdir -p /srv/homelab/pinchi/docker-swarm-poc/postgres/data /srv/homelab/pinchi/docker-swarm-poc/postgres/seed"

# 3. Desplegar el fichero de semilla y el compose
rsync -av seed/001-synthetic-data.sql u-forge@192.168.1.175:/srv/homelab/pinchi/docker-swarm-poc/postgres/seed/
rsync -av docker-compose.yml u-forge@192.168.1.175:/srv/homelab/pinchi/docker-swarm-poc/

# 4. Desplegar el stack (docker stack deploy se ejecuta desde un manager)
ssh u-forge@192.168.1.175 "cd /srv/homelab/pinchi/docker-swarm-poc && docker stack deploy -c docker-compose.yml poc-swarm"

# 5. Verificar que arrancó y que los datos sintéticos están
ssh u-forge@192.168.1.175 "docker service ls"
ssh u-forge@192.168.1.175 "docker exec \$(docker ps -q -f name=poc-swarm_poc-postgres) psql -U poc -d poc_swarm -c 'SELECT count(*) FROM poc_rows;'"

# 6. Forzar un recreate y confirmar que los datos sobreviven (valida el bind-mount)
ssh u-forge@192.168.1.175 "docker service update --force poc-swarm_poc-postgres"
ssh u-forge@192.168.1.175 "docker exec \$(docker ps -q -f name=poc-swarm_poc-postgres) psql -U poc -d poc_swarm -c 'SELECT count(*) FROM poc_rows;'"
```

## Limpieza

```bash
ssh u-forge@192.168.1.175 "docker stack rm poc-swarm"
ssh u-forge@192.168.1.175 "rm -rf /srv/homelab/pinchi/docker-swarm-poc"
```

No dejar el stack corriendo una vez validado — es solo un PoC, no un servicio real.
