# 20 — Apagado y encendido ordenado del clúster (mantenimiento físico)

## Qué resuelve

Procedimiento para apagar de forma segura la mayor parte del clúster (por ejemplo, para una intervención física: mover hardware, limpiar, cambiar cableado) y volver a encenderlo sin corromper datos ni dejar servicios en un estado a medias. Cubre `pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils` y `retaco` — los cinco nodos que se pueden apagar físicamente sin más consecuencia que "no están disponibles mientras dure la intervención".

`ryzen` (`mole`) se trata aparte: normalmente se queda **encendido** (es un PC de sobremesa, no una Raspberry Pi con tarjeta SD delicada) con su propio Docker parado, para poder usarlo como punto de control por SSH durante la intervención. Si alguna vez hay que apagarlo también físicamente, sigue el mismo patrón que los demás (parar Docker, `sudo poweroff`, esperar a que dejen de responder los pings) — para volver a encenderlo hace falta acceso físico o Wake-on-LAN desde otro nodo, ver `docs/19-wake-on-lan.md`.

## Por qué importa el orden

- **Al apagar**: no es estrictamente necesario un orden concreto entre nodos — cada `docker compose down` es una operación local a ese nodo. Lo que sí es crítico es **no cortar la alimentación en frío**: hacer siempre un apagado limpio del sistema operativo (`sudo poweroff`) antes de desconectar. Las Raspberry Pi arrancan desde tarjeta SD, especialmente sensible a corrupción si se corta la alimentación con el filesystem montado en lectura-escritura a medio escribir; `retaco` tiene un SSD, más tolerante pero con el mismo riesgo en el `postgres-main` que aloja.
- **Al encender**: el orden **sí es crítico** y es el mismo que en la instalación (`docs/01-topologia.md`, sección "Orden de instalación"): `retaco` primero — el propio `docker-compose.yml` de `pi-dns` no arranca sano sin retaco ya arriba, porque `nginx` depende (`depends_on: condition: service_healthy`) de `apikey-service`, y `apikey-service` necesita conectar con su base de datos en `postgres-main` (retaco) para arrancar sano. Si `pi-dns` arranca antes que `retaco`, `apikey-service` queda reintentando la conexión (`restart: unless-stopped`) hasta que `retaco` responde — se autocorrige solo, pero es innecesario esperar a que se autocorrija pudiendo evitarlo con el orden correcto.

## Apagado

Todo lo siguiente se ejecuta desde `mole` (`ryzen`), que se queda encendida — usa los mismos usuarios SSH por IP de `shared/scripts/` (`u-data`, `u-dns`, `u-obs`, `u-sonar`, `u-utils`).

### 1. Parar el Docker de `mole` (opcional, según lo que vayas a hacer)

```bash
cd /srv/homelab/ryzen
docker compose down
docker compose -f docker-compose.observability.yml down
```

### 2. Parar Docker y apagar el sistema operativo de cada nodo

Orden sugerido — el inverso al de instalación, por costumbre y simetría con `docs/01-topologia.md`, aunque para el apagado en sí no es obligatorio (sí lo es no saltarse el `sudo poweroff` limpio en cada uno):

```bash
for target in \
  "u-utils@192.168.1.173:pi-utils" \
  "u-sonar@192.168.1.172:pi-sonar" \
  "u-obs@192.168.1.171:pi-obs" \
  "u-dns@192.168.1.170:pi-dns" \
  "u-data@192.168.1.174:retaco"
do
  ssh_target="${target%%:*}"
  node="${target##*:}"
  echo "=== ${node} ==="
  ssh -o BatchMode=yes "${ssh_target}" "cd /srv/homelab/${node} && docker compose down"
  ssh -o BatchMode=yes "${ssh_target}" "sudo poweroff"
done
```

### 3. Confirmar que cada nodo ha terminado de apagarse antes de tocar nada físico

```bash
for ip in 192.168.1.170 192.168.1.171 192.168.1.172 192.168.1.173 192.168.1.174; do
  echo -n "${ip}: "
  timeout 2 ping -c 1 "${ip}" >/dev/null 2>&1 && echo "todavía responde" || echo "apagado"
done
```

⚠️ No desconectes la alimentación de un nodo mientras siga respondiendo a `ping` — significa que el sistema operativo aún no ha terminado de apagarse (SonarQube en `pi-sonar` en particular puede tardar unos segundos más que el resto en pararse limpio, motor Java/Elasticsearch de por medio).

Con los cinco nodos sin respuesta, ya es seguro hacer la intervención física.

## Encendido

### 1. Alimentación física

Reconecta la alimentación de los cinco nodos. Las Raspberry Pi 5 (`pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils`) arrancan solas en cuanto reciben alimentación por USB-C, sin necesidad de pulsar nada. `retaco` (PC mini) puede o no arrancar solo según su propio ajuste de BIOS "Restore AC Power Loss"/similar — si no arranca sola a los 30-60 segundos de reconectar la alimentación, pulsa su botón de encendido físico.

### 2. `retaco` primero — obligatorio

```bash
ssh u-data@192.168.1.174 "cd /srv/homelab/retaco && docker compose up -d"

# Esperar a que postgres-main esté "healthy" (healthcheck pg_isready,
# start_period 30s) antes de continuar:
ssh u-data@192.168.1.174 "cd /srv/homelab/retaco && docker compose ps"
```

No sigas al siguiente paso hasta ver `postgres-main` como `healthy` en esa salida.

### 3. `pi-dns` segundo — obligatorio

```bash
ssh u-dns@192.168.1.170 "cd /srv/homelab/pi-dns && docker compose up -d"
ssh u-dns@192.168.1.170 "cd /srv/homelab/pi-dns && docker compose ps"
```

`nginx` espera solo internamente a `pihole` y `apikey-service` (ambos `depends_on: condition: service_healthy` dentro del propio `docker-compose.yml` de `pi-dns`) — Compose gestiona ese orden interno solo. Lo único que tenías que garantizar tú era que `retaco` ya estuviera arriba (paso 2), porque `apikey-service` necesita alcanzar su base de datos ahí para pasar su propio healthcheck.

Comprueba también que el subnet router de Tailscale se ha reconectado solo (usa el estado persistido, no hace falta volver a autenticar):

```bash
ssh u-dns@192.168.1.170 "docker exec tailscale tailscale status"
```

### 4. Resto de nodos — cualquier orden, incluso en paralelo

```bash
ssh u-obs@192.168.1.171   "cd /srv/homelab/pi-obs   && docker compose up -d"
ssh u-sonar@192.168.1.172 "cd /srv/homelab/pi-sonar  && docker compose up -d"
ssh u-utils@192.168.1.173 "cd /srv/homelab/pi-utils  && docker compose up -d"
```

⚠️ `pi-sonar`/SonarQube tarda ~120 segundos en arrancar (calentamiento de la JVM) — no te alarmes si `docker compose ps` lo muestra `starting` un rato.

⚠️ **Visto en vivo tras un apagado/encendido físico completo**: SonarQube puede quedarse en `starting` indefinidamente (no solo los ~120s normales) si `systemd-resolved` en `pi-sonar` arranca atascado en un DNS secundario y no resuelve `postgresql.home.arpa` (alias del `postgres-main` en `retaco`) — síntoma en `docker logs sonarqube`: `java.net.UnknownHostException: postgresql.home.arpa`, con SonarQube reiniciando su proceso interno en bucle. La conexión TCP directa a `192.168.1.174:5432` funciona bien — es puramente un problema de DNS en `pi-sonar`, ya documentado en `docs/13-troubleshooting.md`. Solución:

```bash
ssh u-sonar@192.168.1.172 "resolvectl query postgresql.home.arpa"   # confirma el síntoma
ssh u-sonar@192.168.1.172 "sudo systemctl restart systemd-resolved"
ssh u-sonar@192.168.1.172 "cd /srv/homelab/pi-sonar && docker compose restart sonarqube"
```

### 5. `mole` — si se paró su Docker en el apagado

```bash
cd /srv/homelab/ryzen
docker compose -f docker-compose.observability.yml up -d   # métricas de host, sin coste de GPU

# Stack de IA — solo si lo necesitas ya, es a demanda:
docker compose pull   # importante tras un parón largo, ver docs/07-instalacion-ryzen.md
docker compose up -d
```

## Verificación final

⚠️ **`check-health.sh` inspecciona contenedores Docker y endpoints en `127.0.0.1` — solo tiene sentido ejecutado *localmente en cada nodo*, no desde `mole` apuntando a otro nodo por nombre.** Ejecutado así, `docker inspect` mira el Docker de `mole` (donde esos contenedores no existen → falsos `[FAIL]`) y `127.0.0.1` es el propio `mole`, no el nodo real — visto en vivo: un `for node in ...; do bash check-health.sh "${node}"; done` lanzado desde `mole` da negativos falsos en todos los nodos remotos (Pi-hole, Loki, Tempo, y todo `docker inspect`), aunque el clúster esté perfectamente sano. La forma correcta es por SSH:

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

Comprobaciones puntuales adicionales:

```bash
dig +short grafana.home.arpa @192.168.1.170     # DNS resuelve
curl -sk https://index.home.arpa -o /dev/null -w "HTTP %{http_code}\n"   # puerta de entrada HTTPS
```

Si algo no sale `healthy`/`200` a la primera, revisa el orden — el fallo más común es `apikey-service` en `pi-dns` reintentando conexión porque `retaco` no terminó de arrancar antes (se autocorrige solo en segundos, ver `docs/13-troubleshooting.md` si persiste).
