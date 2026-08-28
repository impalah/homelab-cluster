# PoC — compatibilidad de `node-exporter`/`cadvisor` con `docker stack deploy`

Valida el riesgo técnico señalado en la mejora 33 (punto 7 de `docs/22-mejoras-futuras.md`):
¿acepta Swarm las claves que usan estos dos servicios hoy en Compose puro (`devices:`,
`privileged:`, `cgroup: host`, `pid: host`)? Resultado completo en `docs/31-docker-swarm.md`,
sección "Riesgos técnicos identificados". Resumen:

- `cgroup: host` **hace fallar** `docker stack deploy` (error de validación de esquema) — se quita
  del compose antes de desplegar.
- `devices:`, `pid: host`, `privileged: true` no dan error, pero Swarm los **ignora en silencio**.
- `node-exporter` funciona igual sin ellos. `cadvisor`, en `pinchi` (cgroup v2 unificado), también
  — sigue viendo métricas de todos los contenedores del host, solo pierde la monitorización de
  `/dev/kmsg` (eventos OOM vía dmesg), degradación menor.
- **Pendiente de reconfirmar en las Raspberry Pi** antes de generalizar a `mode: global` en la
  Fase 1 — cgroup v1 vs v2 puede cambiar el resultado.

Este `docker-compose.yml` ya refleja la versión que sí desplegó (sin `cgroup: host`) — usarlo tal
cual para repetir la prueba en otro nodo, cambiando el `node.hostname` del `constraints`.

## Repetir la prueba en otro nodo

```bash
rsync -av docker-compose.yml u-<x>@192.168.1.17x:/srv/homelab/<nodo>/docker-swarm-check/
ssh u-<x>@192.168.1.17x "cd /srv/homelab/<nodo>/docker-swarm-check && docker stack deploy -c docker-compose.yml check-swarm"
# editar antes el constraints (node.hostname == <nodo>) para que aterrice donde toca
ssh u-<x>@192.168.1.17x "curl -s http://127.0.0.1:8181/metrics | grep '^container_last_seen{' | grep -v 'image=\"\"'"
ssh u-<x>@192.168.1.17x "docker stack rm check-swarm"
```
