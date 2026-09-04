# pinchi — nodo nuevo, sistema base

**IP:** `192.168.1.175`
**Hardware:** PC GMKtec NucBox G10 Pro, Ubuntu Server 26.04 LTS, x86_64

## Estado actual

Sistema base provisionado (2026-08-22, `docs/30-instalacion-pinchi.md`) y unido al Docker
Swarm del clúster (mejora 33) — el grueso de lo que corre en `pinchi` son servicios Swarm
sin `docker-compose.yml` propio.

**Excepción, desde la mejora 5 (`docs/33-nut-sai.md`, 2026-09-01)**: este nodo tiene ahora
su primer `docker-compose.yml` clásico, dedicado únicamente a `nut-upsmon` (cliente NUT que
apaga este host si el SAI físico del clúster, conectado a `pi-obs`, ordena un apagado por
batería crítica) — necesita `privileged: true` de verdad, que Swarm ignora en silencio, así
que no podía ser un servicio Swarm más. No migra ningún otro servicio a Compose clásico.

**Segunda excepción, mejora 7.3 (`docs/22-mejoras-futuras.md`, 2026-09-04)**: el mismo fichero
suma ahora `forgejo-runner-pinchi` (+ su sidecar `dind`) — runner por defecto de Forgejo
Actions, siempre en ejecución. Iba a ser un stack Swarm de verdad; descartado tras confirmar en
vivo que Swarm ignora en silencio **tanto** `privileged` **como** `security_opt` (sin este
último, el `mount()` que necesita un `dockerd` anidado queda bloqueado por el seccomp por
defecto, sin ninguna vía de escape dentro de Swarm) — mismo síntoma exacto ya visto aquí con
`nut-upsmon`, confirmado esta vez además con `docker service create --help`, que ni siquiera
tiene un flag `--security-opt`.

- IP estática (Netplan), paquetes base, Docker Engine + Compose plugin instalados.
- Usuario de administración dedicado `u-forge` (sudo sin contraseña, clave SSH, mismo patrón que el resto de nodos) — acceso remoto por contraseña deshabilitado.
- Docker Swarm: unido como manager (mejora 33) — sin servicios pinnados propios, recibe carga vía routing mesh.

## Si se decide alojar algo más aquí

Seguir el mismo patrón que el resto de nodos (`config/`, `data/`) dentro de este
`docker-compose.yml` ya existente, y añadir el caso específico en
`shared/scripts/prepare-host.sh` si hace falta alguna subcarpeta de datos nueva.

## Arranque rápido (solo sistema base, hoy)

```bash
ssh u-forge@192.168.1.175
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pinchi
docker compose version   # confirma Docker Engine + Compose plugin operativos
```
