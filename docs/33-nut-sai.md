# 33 — Integración NUT del SAI (mejora 5)

## Qué resuelve

El clúster tiene un SAI físico (Salicru SPS 2200 SOHO+) protegiendo los 6 nodos + switches de red, pero hasta esta mejora ningún nodo sabía si estaba con batería ni cuánta autonomía quedaba — un corte de luz largo simplemente apagaba todo en frío, con el mismo riesgo de corrupción de tarjeta SD/estado Raft de Swarm que ya documenta `docs/20-apagado-y-encendido-cluster.md` para un apagado manual mal hecho.

Esta mejora integra [Network UPS Tools (NUT)](https://networkupstools.org/) para que:

1. `pi-obs` (donde está conectado el SAI por USB) sepa el estado real de la batería.
2. El resto de nodos lo consulten por red y se apaguen solos, limpio, si la batería llega a nivel crítico.
3. Prometheus/Grafana tengan visibilidad y alerten sobre el estado del SAI.

## Hardware real (confirmado en vivo, 2026-09-01)

El SAI está conectado por USB a **`pi-obs`** (192.168.1.171, no a `mole`/`ryzen` como suponía originalmente `docs/22-mejoras-futuras.md`, mejora 5). Identificado por `lsusb`:

```
Bus 004 Device XXX: ID 06da:ffff Phoenixtec Power Co., Ltd Offline UPS
```

El número de bus/dispositivo (`XXX`) **cambia** cada vez que el SAI se desconecta y reconecta — por eso el contenedor del servidor monta `/dev/bus/usb` entero, no un `/dev/hidrawN`/`/dev/bus/usb/BBB/DDD` concreto (ver más abajo).

Driver NUT correcto: **`usbhid-ups`**, subdriver detectado automáticamente **"Phoenixtec/Liebert HID 0.41"** — es un dispositivo HID Power Device estándar, no hace falta `nutdrv_qx`/`blazer_usb` (protocolo Megatec/Q1) ni el flag `-x pollonly` que a veces necesitan otros SAIs con este mismo vendor ID.

## Arquitectura

- **Servidor** (`pi-obs/nut-server/`, desplegado en `pi-obs/docker-compose.yml` — Compose **clásico**, no Swarm): un único contenedor con el driver `usbhid-ups`, `upsd` y un `upsmon` local en modo `primary`, todos gestionados por `pi-obs/nut-server/entrypoint.sh`. `upsd` se publica en el puerto `3493` de la LAN (mismo criterio que `postgres-main` en 5432 — hay consumidores remotos).
- **Clientes** (`shared/docker/nut-client/` + `shared/config/nut/`, un servicio `nut-upsmon` añadido al `docker-compose.yml` clásico de **los 6 nodos**: `ryzen`, `retaco`, `pi-dns`, `pi-sonar`, `pi-utils` y `pinchi`): cada uno corre `upsmon` en modo `secondary`, apuntando a `sai@192.168.1.171` por IP real (nunca alias Docker — cruza la frontera Swarm/Compose clásico, ver `CLAUDE.md`).
- **`pinchi` estrena aquí su primer `docker-compose.yml` propio** — hasta esta mejora era Swarm-only (`docs/30-instalacion-pinchi.md`). No migra nada más a Compose clásico, es únicamente para `nut-upsmon`.
- **`nut-exporter`** (`druggeri/nut_exporter:3.3.0`) vive en el stack Swarm `docker-swarm/stacks/pi-obs/`, junto a Prometheus/Grafana — mismo patrón que `postgres-exporter` (scrapea un servicio remoto por IP real aunque esté en el mismo nodo físico, porque las dos redes Docker —overlay del swarm y bridge clásica— no se comparten).
- **Alerta de Grafana**: `pi-obs/config/grafana/alerting/sai-bateria.yml`, 3 reglas (SAI en batería, batería baja, `nut-exporter` sin respuesta), mismo patrón que `undervoltage.yml`.

## Por qué el cliente NO puede ser un servicio Swarm

Hallazgo crítico de esta mejora: **`docker stack deploy` ignora en silencio `privileged`/`devices`/`pid`** (ya lo documentaba `docker-swarm/stacks/common/docker-compose.yml` desde el PoC de la mejora 33). El apagado real (ver siguiente sección) **necesita** `privileged: true` de verdad — sin él, AppArmor bloquea la conexión D-Bus con el host:

```
Failed to open connection to "system" message bus: An AppArmor policy prevents this sender from sending this message to this recipient
```

Confirmado en vivo en `pinchi`: mismo comando, sin `--privileged` falla, con `--privileged` funciona. Por eso `nut-upsmon` tiene que vivir en Compose clásico en **los 5 nodos que también son managers de Swarm** (`retaco`, `pi-obs`, `pi-sonar`, `pi-utils`, `pinchi`), no como un servicio Swarm — perdería `privileged` sin ningún error visible en el despliegue, y el apagado automático fallaría en silencio justo cuando más falta hace.

## Apagado automático real

`SHUTDOWNCMD` de `upsmon` en los 7 contenedores (servidor + 6 clientes) es `shared/scripts/nut-shutdown-host.sh`, que usa D-Bus/logind para apagar el **sistema operativo real del host**, no el contenedor:

```sh
dbus-send --system --print-reply --dest=org.freedesktop.login1 /org/freedesktop/login1 \
    org.freedesktop.login1.Manager.PowerOff boolean:true
```

Requiere `privileged: true` + montar `/run/dbus/system_bus_socket` del host (ver sección anterior). **Validado con hardware real en `pinchi`** (2026-09-01): una llamada `PowerOff` real apagó la máquina de verdad (confirmado por pérdida de ping, sin volver a responder pasados varios minutos). En el resto de nodos solo se verificó de forma no destructiva (`CanPowerOff` → `"yes"`), sin llegar a cortarles la corriente — el mecanismo es idéntico en los 7, y el único modo de fallo real encontrado (AppArmor sin `privileged`) ya está cubierto en los 7 por igual.

⚠️ **`pinchi` no tiene Wake-on-LAN configurado** (solo `ryzen` lo tiene, `docs/19-wake-on-lan.md`) — tras un apagado real necesitó el botón físico de encendido para volver. Ningún otro nodo de los 6 tiene WoL tampoco, así que un apagado real por batería crítica en cualquiera de ellos requiere intervención física para volver a encenderlos (el `docs/20` ya asume esto para el apagado manual: "las Raspberry Pi 5 arrancan solas al recibir alimentación por USB-C" — pero eso es al **reconectar la corriente**, no tras un `poweroff` limpio con la corriente ya presente).

### Probar el apagado sin cortar la luz de verdad

Comprobación no destructiva (autorización D-Bus, sin ejecutar el apagado):

```bash
docker exec nut-upsmon sh -c \
  'dbus-send --system --print-reply --dest=org.freedesktop.login1 /org/freedesktop/login1 \
   org.freedesktop.login1.Manager.CanPowerOff'
# -> string "yes"
```

## Verificación rápida

```bash
# Estado del SAI, desde el propio pi-obs o cualquier cliente
docker exec nut-server upsc sai@localhost      # en pi-obs
docker exec nut-upsmon upsc sai@192.168.1.171  # en cualquier otro nodo

# Metricas en Prometheus (desde cualquier nodo -- ver nota de hairpin NAT abajo)
curl -s 'http://192.168.1.171:9090/api/v1/query?query=network_ups_tools_ups_status'
```

⚠️ **Limitación de Swarm (hairpin NAT), no un fallo real**: un nodo no puede alcanzar su propio puerto publicado por la routing mesh vía `localhost`/su propia IP — probar `curl http://localhost:9090/...` **desde el propio `pi-obs`** se queda colgado indefinidamente aunque Prometheus esté perfectamente sano (confirmado en vivo: el mismo `curl` desde `retaco` responde `200` al instante, y `docker exec` dentro del propio contenedor de Prometheus también responde bien). Si algo publicado por Swarm en `pi-obs` parece "colgado", prueba primero desde otro nodo antes de asumir que está roto.

## Gotchas encontrados (todos ya corregidos en el código actual)

1. **NUT exige ASCII puro** en sus ficheros de configuración — un acento en un comentario de `ups.conf` bastaba para que el parser rechazara caracteres y el driver no arrancara (`addchar: discarding invalid character`).
2. **El paquete `nut-server`/`nut-client` de Ubuntu bloquea `upsd`/`upsmon` si `MODE=none`** en `/etc/nut/nut.conf` (el valor de fábrica) — hace falta `MODE=netserver` (servidor) o `MODE=netclient` (clientes) explícito, o ambos daemons se quedan sin arrancar con el mensaje "disabled, please adjust the configuration", sin que el driver USB (que sí puede estar funcionando bien) dé ninguna pista de por qué.
3. **El driver hace *drop* de privilegios al usuario `nut` antes de abrir el dispositivo USB**, y el UID/GID de ese usuario dentro del contenedor no tiene por qué coincidir con el que la regla `udev` del paquete autoriza en el host — falla con `insufficient permissions on everything` pese a `privileged: true` y el bind-mount de `/dev/bus/usb` entero. Solución: forzar `user = root` (driver, en `ups.conf`), `-u root` (`upsd`) y `RUN_AS_USER root` (`upsmon`) — el contenedor ya es `privileged` a propósito, así que no depende de que esos UID/GID coincidan.
4. El README del proyecto `nut_exporter` dice "scratch-based image" — su `Dockerfile` real es Alpine (con shell), confirmado antes de decidir cómo inyectarle la contraseña desde un Docker secret (mismo patrón `entrypoint: sh -c 'export ... && exec ...'` que `postgres-exporter`, que si hubiera sido scratch de verdad no habría funcionado).
5. **`DEADTIME` por defecto (15s) puede disparar un apagado real por un simple blip de red, sin que el SAI tenga ningún problema** — confirmado en vivo el 2026-09-01: un reinicio normal de `nut-server` en `pi-obs` (motivo puntual, no un crash-loop) cortó la comunicación con el cliente de `pi-utils` durante ~4 segundos; con `DEADTIME 15` y `MINSUPPLIES 1`, `upsmon` interpretó esa breve pérdida de datos como "SAI en estado desconocido" y ejecutó el `SHUTDOWNCMD` real, apagando el nodo de verdad sin ningún corte de luz. Detalle completo del incidente y la correlación de logs en `docs/31-docker-swarm.md`. **Fix**: `DEADTIME` subido a `60` en los 7 contenedores (`shared/config/nut/upsmon-client.conf.template`, los 6 clientes, y `pi-obs/config/nut/upsmon.conf.template`, el primario) — margen de sobra frente a los ~4s reales observados, sin renunciar a la detección de un corte genuino (dura minutos). `MINSUPPLIES` se dejó en `1` a propósito: bajarlo a `0` eliminaría también la protección real de que un nodo se apague solo si `pi-obs` muere de verdad en un corte antes de poder emitir el `FSD` — no era la causa del falso positivo.

## Pendiente / limitaciones conocidas

- ~~**Canal de notificación proactivo**: `ntfy` (mejora 4, `docs/22-mejoras-futuras.md`) todavía no está desplegado — la alerta de Grafana funciona (visible en la UI/panel) pero sin push a un teléfono/canal hasta que esa mejora se implemente.~~ **Cerrado** (mejora 4 implementada) — `sai-bateria.yml` ya enruta a ntfy vía `pi-obs/config/grafana/alerting/notification-policies.yml`, ver `docs/34-ntfy-notificaciones.md`.
- **Capacidad real del SAI bajo carga completa**: en el momento de escribir esto, el SAI marcaba ~12% de carga con los 6 nodos + switches conectados (confirmado por el usuario) — probablemente porque `ryzen` está normalmente apagado cuando no se usa (`docs/19-wake-on-lan.md`). No se ha medido la autonomía real con `ryzen` encendido bajo carga de GPU, que puede consumir varios cientos de W él solo. Si el SAI resulta insuficiente para dar tiempo a un apagado ordenado con todo encendido a la vez, es un problema de dimensionado del hardware, no de esta integración software.
- **`docs/20-apagado-y-encendido-cluster.md`** documenta el apagado/encendido *manual* — no se ha actualizado su procedimiento de apagado para asumir que ahora también puede dispararse solo por NUT; el de encendido (orden `retaco` → `pi-dns` → resto) sigue aplicando igual tanto si el apagado fue manual como automático.
