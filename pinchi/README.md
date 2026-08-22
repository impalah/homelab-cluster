# pinchi — nodo nuevo, sistema base

**IP:** `192.168.1.175`
**Hardware:** PC GMKtec NucBox G10 Pro, Ubuntu Server 26.04 LTS, x86_64

## Estado actual

Solo el **sistema base** está provisionado (2026-08-22) — no hay `docker-compose.yml` ni `.env.example` en este directorio todavía porque no se ha decidido qué servicios va a alojar. Ver `docs/30-instalacion-pinchi.md` para el detalle completo de lo ya hecho:

- IP estática (Netplan), paquetes base, Docker Engine + Compose plugin instalados.
- Usuario de administración dedicado `u-forge` (sudo sin contraseña, clave SSH, mismo patrón que el resto de nodos) — acceso remoto por contraseña deshabilitado.
- Docker listo para Swarm (viene integrado en el motor) pero **sin inicializar/unir todavía** — pendiente de que se ejecute la mejora 33 (`docs/22-mejoras-futuras.md`).

## Cuando se decida qué aloja este nodo

Añadir aquí `docker-compose.yml`/`.env.example`, seguir el mismo patrón que el resto de nodos (`config/`, `data/`), y añadir su caso específico en `shared/scripts/prepare-host.sh` (ahora mismo solo crea el directorio base, sin subcarpetas de datos).

## Arranque rápido (solo sistema base, hoy)

```bash
ssh u-forge@192.168.1.175
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pinchi
docker compose version   # confirma Docker Engine + Compose plugin operativos
```
