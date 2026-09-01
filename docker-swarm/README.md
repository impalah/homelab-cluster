# docker-swarm — migración a Docker Swarm (mejora 33)

Todo lo relativo a la migración a Docker Swarm vive aquí, separado de los `docker-compose.yml`
por nodo que siguen siendo la fuente de verdad hasta que un servicio concreto se migra. El
diseño completo, las decisiones tomadas y el estado real de la migración viven en
`docs/31-docker-swarm.md` — este README es solo el mapa de directorios y el arranque rápido.

## Nodos del swarm

`retaco`, `pi-obs`, `pi-sonar`, `pi-utils`, `pinchi` — los 5 como **manager** (máxima tolerancia
a caídas). `ryzen` y `pi-dns` quedan fuera por completo (mejoras 37/39), sin excepción.

## Estructura

```
docker-swarm/
├── init/
│   ├── init-swarm.sh            ← bootstrap del swarm (pinchi en solitario, luego join del resto)
│   ├── label-nodes.sh           ← node labels de rol (role=stateful en retaco/pinchi)
│   └── setup-swarm-firewall.sh  ← restringe el tráfico de control de Swarm a los 5 nodos
├── poc/
│   ├── synthetic-db/            ← PoC de un solo nodo en pinchi, datos sintéticos
│   └── common-services-check/   ← PoC de compatibilidad node-exporter/cadvisor con Swarm
└── stacks/
    ├── common/          ← node-exporter/cadvisor, mode: global (Fase 1, completada); puertos en
    │                        mode: host desde el 2026-09-01 (docs/31, incidente real de mode: ingress
    │                        mezclando métricas entre nodos, encontrado implementando la mejora 36)
    ├── portainer/       ← agent-stack.yml oficial (agente, mode: global) (Fase 1, completada) —
    │                        no confundir con portainer-server/ más abajo (el servidor, Fase 4)
    ├── markitdown/      ← primer servicio de aplicación real, sin constraints (Fase 2, completada)
    ├── apikey-service/  ← copia swarm en paralelo a pi-dns, para que Traefik pueda validar
    │                        X-Api-Key vía ForwardAuth (Fase 3b, completada)
    ├── traefik/         ← Fase 3, completada: descubrimiento (3a), TLS real + cutover de DNS (3b);
    │                        cierre de la mejora 41 (2026-08-28, docs/22): retirados los ~26
    │                        routers `*.home.arpa` y su cert, nginx en pi-dns decomisionado del
    │                        todo (ya no es vía de rollback, no queda desplegado)
    ├── registry/        ← primer servicio CON ESTADO migrado (Fase 4, completada, 2026-08-27),
    │                        pinnado a retaco (node.hostname==retaco), mismos datos sin mover
    ├── qdrant/          ← segundo servicio con estado (Fase 4, completada, 2026-08-27), pinnado
    │                        a retaco; open-webui (mismo nodo) pasó del alias Docker interno a
    │                        IP:puerto real para sobrevivir a la migración
    ├── n8n-main/        ← tercer servicio con estado (Fase 4, completada, 2026-08-27), pinnado a
    │                        retaco; mismo ajuste que qdrant, hacia postgres-main (todavía clásico)
    ├── n8n-aux/         ← cuarto servicio con estado (Fase 4, completada, 2026-08-27), pinnado a
    │                        pi-utils; SQLite propio, sin dependencias cruzadas
    ├── authentik/       ← quinto servicio con estado (Fase 4, completada, 2026-08-27), server +
    │                        worker en el mismo stack, ambos pinnados a retaco; sin cambios en
    │                        Traefik (ya apuntaba por IP desde el primer incremento de 3b)
    ├── vaultwarden/     ← sexto servicio con estado (Fase 4, completada, 2026-08-27), pinnado a
    │                        pi-utils; el más sensible a pérdida de datos, backup obligatorio
    │                        ejecutado antes de migrar
    ├── postgres-main/   ← séptimo servicio con estado (Fase 4, completada, 2026-08-27), pinnado a
    │                        retaco; compartido por casi todo lo demás del clúster, backup físico
    │                        completo previo, todos los consumidores verificados
    ├── pi-obs/          ← Loki+Tempo+Prometheus+otel-collector+Grafana+postgres-exporter, los 6
    │                        en UN SOLO stack (Fase 4, COMPLETA, 2026-08-27), pinnados a pi-obs;
    │                        de paso corrige un bug de DNS de postgres-exporter de 3 días
    ├── sonarqube/       ← Fase 4, completada, 2026-08-27, pinnado a pi-sonar; imagen fijada por
    │                        digest tras un incidente real de versión (tag flotante resolvió una
    │                        actualización no pedida, revertido con el usuario)
    ├── bifrost/         ← Fase 4, completada, 2026-08-27, pinnado a pi-sonar; sin estado real
    │
    │   Ampliación de alcance explícita del usuario (2026-08-27, "migra todo lo que falte del
    │   clúster") — resto de retaco/pi-utils, ver docs/31-docker-swarm.md:
    ├── infisical/       ← infisical + postgres-infisical combinados (mismo alias de red),
    │                        pinnados a retaco; base de secretos de todo el clúster
    ├── valkey/          ← pinnado a retaco; sin persistencia (solo caché), valkey.404labo.net
    │                        preservado como alias DNS directo
    ├── open-webui/       ← pinnado a retaco; mode: host en :8080 (choque con bifrost)
    ├── epub2pdf-service/ ← pinnado a retaco (constraints obligatorio — mount NFS de ketekasko)
    ├── pdf2chunks-service/ ← pinnado a retaco (mismo motivo que epub2pdf-service)
    ├── open-terminal-mcp/ ← pinnado a retaco
    ├── rsshub/          ← pinnado a pi-utils (constraints obligatorio — CA/binario Infisical
    │                        con ruta de nodo; sin constraints el scheduler falla intermitente)
    ├── crawl4ai-scraper-service/ ← sin constraints (sin estado real), cualquiera de los 5 nodos
    ├── capataz/         ← capataz-api + capataz-runner + capataz-frontend combinados, pinnados
    │                        a pi-utils; 7 secrets nativos de Compose convertidos a docker secret
    ├── portainer-server/ ← servidor Portainer, pinnado a pi-utils; último servicio Compose
    │                        clásico de ese nodo (junto con watchtower, que nunca se migra)
    └── ntfy/            ← mejora 4 (docs/22-mejoras-futuras.md, cerrada), canal de notificación
                             proactivo del clúster; nace ya como stack Swarm (no es una migración),
                             `node.labels.role == stateful` en vez de un `node.hostname` fijo — ver
                             docs/34-ntfy-notificaciones.md
```

Con esto, `retaco`, `pi-obs`, `pi-sonar` y `pi-utils` quedan con Compose clásico reducido a un
único servicio en cada uno: `watchtower` (deliberadamente excluido, ver mejora 33 punto 7).

Cada servicio existente que se migre (postgres-main, qdrant, n8n-*, vaultwarden, authentik,
registry...) obtiene su propio `stacks/<nombre>/docker-compose.yml` cuando le toque su fase —
la migración es incremental por diseño, nunca todo de golpe.

**Forgejo (mejora 7) queda fuera de esta migración a propósito** — decisión del usuario
(2026-08-24), se aborda en un esfuerzo separado una vez el clúster esté migrado a Swarm por
completo y el DNS esté resuelto. Sigue en backlog en `docs/22-mejoras-futuras.md`.

## Arranque rápido (Fase 0)

```bash
# 1. Swarm de un solo nodo en pinchi
bash init/init-swarm.sh init

# 2. PoC con datos sintéticos — ver docker-swarm/poc/synthetic-db/README.md
cd poc/synthetic-db && cat README.md

# 3. Solo si el PoC valida los dos riesgos técnicos (bind-mount + constraints,
#    y compatibilidad de node-exporter/cadvisor con docker stack deploy):
bash init/init-swarm.sh join-all
bash init/label-nodes.sh
bash init/init-swarm.sh status
```
