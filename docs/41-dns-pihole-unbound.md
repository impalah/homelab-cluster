# 41 — DNS del clúster: Pi-hole + Unbound (arquitectura, incidente y checklist para `pi-dns2`)

Cómo está montado el DNS de `pi-dns` (`192.168.10.2`), qué se rompió el 2026-10-15 y cómo se arregló, y la lista de comprobación que **debe aplicarse tal cual al montar `pi-dns2`** (mejora 55 de `docs/22-mejoras-futuras.md`).

## Arquitectura

```
cliente / nodo ──► Pi-hole (:53 del host)  ──►  Unbound (172.20.0.2:5335)  ──►  raíz / TLD / autoritativos de internet
                    · bloquea anuncios            · resuelve él mismo, sin DNS público de por medio
                    · sirve *.404labo.net         · valida DNSSEC (auto-trust-anchor)
                      (registros locales)         · caché con prefetch y serve-expired
```

- **Pi-hole** (`pihole/pihole`, v6) recibe todas las consultas, bloquea (listas *gravity*) y contesta los registros locales `*.404labo.net` (fuente de verdad: `shared/dns/dns-records.md`, cargados con `shared/scripts/load-dns-records.sh`).
- **Unbound** (`mvance/unbound-rpi`, config en `pi-dns/config/unbound/unbound.conf`) es el **upstream** de Pi-hole: lo que no es local lo resuelve preguntando directamente a los servidores autoritativos, sin entregar el historial de consultas a Google/Cloudflare. Solo acepta consultas de `127.0.0.0/8` y de `172.20.0.0/24` (la red interna de Docker).
- Red `pi-dns-net` (`172.20.0.0/24`) con **IP fija para cada contenedor** (Unbound `.2`, Pi-hole `.3`, nut-server `.4`...). Pi-hole y Unbound se referencian por IP, no por nombre.

## Incidente 2026-10-15: Pi-hole reenviaba a Google y Unbound se caía en los arranques

**Síntoma.** Unbound figuraba parado (`Exited (255)`) y el upstream de Pi-hole era `8.8.8.8` / `8.8.4.4`. El DNS funcionaba, pero todas las consultas salían a Google y no había validación DNSSEC local.

**Dos causas independientes:**

1. **Variables de Pi-hole v5 en un Pi-hole v6.** El compose declaraba el upstream con `PIHOLE_DNS_` y `DNSSEC`. La v6 **solo entiende `FTLCONF_*`** y ignora las otras **sin avisar**, así que el upstream nunca estuvo realmente declarado: se quedó en lo que alguien puso a mano en la configuración (`### CHANGED` en `pihole.toml`). Es el mismo tropiezo que ya avisaba el comentario sobre `WEBPASSWORD`.
2. **Docker no reintenta `unbound` tras un fallo de red en el arranque.** En el journal de Docker aparece `failed to set up container networking: Address already in use` sobre Unbound (y otros contenedores) en arranques del host. A pesar de `restart: unless-stopped`, el contenedor se quedaba en `Exited (255)` hasta el siguiente reinicio. Con Pi-hole apuntando solo a Unbound eso es un DNS muerto, y probablemente por eso alguien puso `8.8.8.8` como salvavidas.

> **Aviso sobre las fechas.** Esta Raspberry no conserva bien la hora entre apagados: `docker ps` y `docker inspect` mostraban fechas de hace "2 meses" que no corresponden a lo que pasó (la hora se corrige por NTP después de arrancar los contenedores). Para saber cuándo ocurrió algo, usar `journalctl -u docker` y `journalctl --list-boots`, no el estado de Docker. La primera lectura de este incidente ("parado desde el 27-07") fue un error por fiarse de ellas.

## El arreglo (tres piezas)

| Pieza | Dónde | Qué hace |
|---|---|---|
| Upstream declarativo | `pi-dns/docker-compose.yml`, servicio `pihole` | `FTLCONF_dns_upstreams: 172.20.0.2#5335` y `FTLCONF_dns_dnssec: "false"` (Unbound ya valida; validar dos veces solo añade latencia). Fijado en cada arranque; la interfaz web lo muestra de solo lectura |
| IP fija para `nut-server` | mismo compose | Era la única sin `ipv4_address` (la asignaba Docker). Ahora `172.20.0.4`, la que ya tenía |
| Guardián de Unbound | `shared/scripts/dns-guard.sh` + cron cada minuto | Si Unbound no está `running`: `docker start`; si no, reconecta a la red con su IP fija; si no, `docker compose up -d unbound`. Comprueba que Unbound y Pi-hole resuelven y escribe métricas |

Métricas del guardián (textfile collector, `/srv/homelab/node-exporter-textfile/dns-guard.prom`): `homelab_dns_unbound_up`, `homelab_dns_pihole_resolve_ok`, `homelab_dns_guard_recovered_last_run`, `homelab_dns_guard_last_run_timestamp_seconds`. Candidatas a alerta en Grafana (mejora 42): `unbound_up == 0`, `pihole_resolve_ok == 0`, o un `last_run_timestamp` con más de 5 minutos.

**Verificado en vivo (2026-10-15):** recreando solo `pihole` no hubo ningún fallo de resolución en un sondeo cada 0,5 s; parando Unbound a mano, el guardián lo levantó en 8 s y el DNS volvió. **No ejercitado**: los pasos 2 y 3 del guardián (reconexión a la red y `compose up`); solo se probó el `docker start`.

Cambios en el nodo (copias previas a este arreglo: `docker-compose.yml.bak-pre-upstream-fix` y `pihole.toml.bak-pre-upstream-fix` junto al original):

```bash
# compose y script desplegados con /tmp + sudo cp (admin no es dueño de /srv/homelab)
cd /srv/homelab/pi-dns && docker compose config -q            # validar antes
docker compose up -d --no-deps pihole                          # recrear SOLO pihole
crontab -e   # * * * * * /usr/bin/bash /srv/homelab/shared/scripts/dns-guard.sh >> /var/log/homelab-dns-guard.log 2>&1
```

## Checklist para `pi-dns2` (mejora 55)

> **Aplicado el 2026-10-15** en `pi-dns2` (`pi-dns2/docker-compose.yml`): todos los puntos salvo la prueba de conmutación completa. Detalles propios: Unbound y red con las mismas IP (`pi-dns-net`, 172.20.0.0/24, red local a cada host), el `.env` es de `admin` con modo 600, y `/etc/resolv.conf` del nodo usa `127.0.0.1` y `192.168.10.2` (respaldo para el arranque).

Aplicar **desde el principio**, no como parche posterior:

1. **Variables `FTLCONF_*`, nunca `PIHOLE_DNS_` ni `DNSSEC`/`WEBPASSWORD`** (v5). Upstream = el Unbound del propio nodo (`172.20.0.2#5335` si se copia la misma red), **no** un DNS público. Si más adelante se quisiera un respaldo público, sabiendo que Pi-hole consulta a *todos* los upstreams y que eso mandaría parte de las consultas fuera.
2. **IP fija para todos los contenedores** de la red DNS (`ipv4_address`), sin excepciones.
3. **Copiar `unbound.conf`** (`access-control` limitado a la red interna, `auto-trust-anchor-file`, `hide-identity`, `harden-*`, caché y prefetch) y comprobar que el contenedor es `healthy`.
4. **Instalar el guardián** con sus variables ajustadas al nodo si cambian los nombres (`DNS_NETWORK`, `DNS_UNBOUND_IP`, `DNS_COMPOSE_FILE`; por defecto son los de `pi-dns`), su cron cada minuto y su log con `logrotate`.
5. **Orden de arranque**: `pihole` con `depends_on: unbound` en `service_healthy`, y `restart: unless-stopped` en ambos (el guardián cubre lo que Docker no reintenta).
6. **Sincronización con `pi-dns`**: los registros locales salen del repo con `load-dns-records.sh` apuntado a cada Pi-hole (mejora 55, punto 2); no editar a mano un solo Pi-hole.
7. **Probar la conmutación en los dos sentidos** (mejora 55, punto 7) y, además, **parar Unbound en cada nodo** y comprobar que el guardián lo recupera.
8. **Hora**: confirmar que el nodo sincroniza por NTP **antes** de depender de DNSSEC; con la hora errónea la validación falla (las firmas aún "no son válidas") justo tras un arranque. `timedatectl` debe decir `System clock synchronized: yes`.

## Comprobaciones

```bash
# Upstream real de Pi-hole (debe ser el Unbound local, no 8.8.8.8)
docker exec pihole pihole-FTL --config dns.upstreams            # -> [ 172.20.0.2#5335 ]
# Unbound responde y valida DNSSEC (primero con flag "ad", segundo SERVFAIL)
docker exec pihole dig +time=5 @172.20.0.2 -p 5335 sigok.verteiltesysteme.net   | grep flags
docker exec pihole dig +time=5 @172.20.0.2 -p 5335 sigfail.verteiltesysteme.net | grep status
# Pi-hole resuelve un nombre local y uno externo
dig +short @192.168.10.2 registry.404labo.net example.com
# Guardián: estado y log
grep -v '^#' /srv/homelab/node-exporter-textfile/dns-guard.prom; tail /var/log/homelab-dns-guard.log
```

Si el upstream aparece de nuevo con IP pública: no es un fallo de Docker, alguien lo cambió en la interfaz o con `pihole-FTL --config`. Con `FTLCONF_dns_upstreams` definido la interfaz no debería dejar cambiarlo; si lo permite, el compose desplegado no tiene la variable.
