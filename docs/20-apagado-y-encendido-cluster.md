# 20 — Apagado y encendido ordenado del clúster (mantenimiento físico)

## Qué resuelve

Procedimiento para apagar de forma segura la mayor parte del clúster (por ejemplo, para una intervención física: mover hardware, limpiar, cambiar cableado) y volver a encenderlo sin corromper datos ni dejar servicios en un estado a medias. Cubre los seis nodos apagables: `pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils`, `retaco` y `pinchi`.

**Este es el procedimiento de apagado MANUAL.** Desde la mejora 5 (`docs/33-nut-sai.md`) existe además un apagado AUTOMÁTICO real ante batería crítica del SAI — `upsmon` en los 6 nodos + `ryzen` ejecuta `poweroff` limpio por su cuenta, sin seguir ningún orden entre nodos (ver esa sección más abajo, sigue aplicando igual). Ninguno de los 6 nodos tiene Wake-on-LAN configurado (solo `ryzen` lo tiene, `docs/19-wake-on-lan.md`), así que tras un apagado automático real hace falta el mismo paso 1 de "Encendido" de más abajo (alimentación física/botón) antes de continuar con el orden de arranque habitual.

**Actualizado el 2026-08-26** tras la migración a Docker Swarm (mejora 33, `docs/31-docker-swarm.md`) y el cutover de DNS de ese mismo día — la versión anterior de este documento es de antes de que existiera `pinchi` y de que Traefik sirviera tráfico real. Si vuelves a leer esto en el futuro y la Fase 4 de la mejora 33 (mover `postgres-main`/`authentik`/`vaultwarden`/etc. al swarm) ya está hecha, revisa si el paso "arrancar `retaco` primero" sigue teniendo el mismo motivo o ha cambiado.

`ryzen` (`mole`) se trata aparte: normalmente se queda **encendido** (es un PC de sobremesa, no una Raspberry Pi con tarjeta SD delicada) con su propio Docker parado, para poder usarlo como punto de control por SSH durante la intervención — de hecho, si estás leyendo esto ejecutando comandos desde el propio Claude Code, es muy probable que ya estés en `ryzen`. Si alguna vez hay que apagarlo también físicamente, sigue el mismo patrón que los demás (parar Docker, `sudo poweroff`, esperar a que deje de responder al ping) — para volver a encenderlo hace falta acceso físico o Wake-on-LAN desde otro nodo, ver `docs/19-wake-on-lan.md`.

## Qué ha cambiado con Docker Swarm — léelo antes de improvisar

- **`retaco`, `pi-obs`, `pi-sonar`, `pi-utils` y `pinchi` son los 5 nodos del swarm** (todos manager, quórum Raft). `pi-dns` y `ryzen` se quedan fuera del swarm por completo (mejoras 37/39) — siguen siendo Docker Compose puro, sin cambios de fondo respecto al procedimiento anterior.
- **Docker Swarm se auto-repara solo** al reiniciar los 5 nodos — no hace falta ningún comando especial de swarm para "reformar el quórum": cada manager persiste su estado Raft en disco (`/var/lib/docker/swarm/`) y, en cuanto `dockerd` arranca y los 5 nodos vuelven a verse entre sí por la red (puertos 2377/7946/4789, ya abiertos de forma persistente, `docker-swarm/init/setup-swarm-firewall.sh`), el clúster Swarm se recompone y **reprograma solo** todos los servicios (`traefik`, `apikey-service` copia swarm, `markitdown-service`, `node-exporter`/`cadvisor` globales, `portainer-agent`) sin que tengas que hacer `docker compose up -d` ni `docker stack deploy` en ninguno de los 5 — eso solo hace falta si cambias algo, no para un simple reinicio.
- **Ahora mismo (2026-08-26), la mayoría del tráfico HTTP real del clúster (28 hostnames, incluido `*.404labo.net`) entra por Traefik en `pinchi` (192.168.1.175)**, no por `nginx` en `pi-dns` — el cutover de DNS de la mejora 33 ya está hecho (`docs/31-docker-swarm.md`). `nginx` en `pi-dns` sigue desplegado y funcional como vía de rollback, pero **nada apunta ahí por DNS salvo** `apikey.home.arpa`, `old.index.home.arpa`, `pihole.home.arpa` (excepciones deliberadas, fuera de Traefik todavía). Esto significa que, aunque Swarm se auto-repare, **si `pinchi` en concreto tarda en volver, todo lo que resuelve a esa IP da timeout** aunque las réplicas de Traefik en los otros 4 nodos estén perfectamente sanas — nadie más escucha en esa IP. Prioriza que `pinchi` vuelva pronto al encender.
- **`retaco` sigue siendo el nodo crítico a arrancar primero**, y ahora por más motivos que antes: aloja `postgres-main` (BD de `apikey-service`, `authentik`, `n8n-main`, `sonarqube`...) Y `authentik-server` (el forward-auth que protege `prometheus.home.arpa` en Traefik). Ninguno de los dos está migrado al swarm todavía (Fase 4 de la mejora 33, pendiente) — siguen siendo Compose clásico en `retaco`, con el mismo `docker compose up -d` de siempre.
- **`pi-obs`, `pi-sonar`, `pi-utils` tienen DOS cosas corriendo a la vez** tras la migración: son nodos del swarm (se reprograman solos, no toques nada) **y además siguen con su propio `docker-compose.yml` clásico** para lo que todavía no se ha migrado (Grafana/Prometheus/Loki/ Tempo en `pi-obs`; SonarQube/Bifrost en `pi-sonar`; Capataz/Vaultwarden/RSSHub/n8n-aux/etc. en `pi-utils`) — ese Compose clásico **sí** hay que levantarlo a mano igual que siempre, el swarm no lo hace por ti. `pinchi` es distinto: no tiene `docker-compose.yml` propio, todo lo que corre ahí es Swarm puro — no necesita ningún `docker compose up -d`.
- **Gotcha real, encontrado en vivo el mismo día del cutover** (`docs/31-docker-swarm.md`, tercer incidente de la sub-fase 3b): en un arranque en frío, `dockerd` puede reservar un puerto para la routing mesh de Traefik (`mode: global`, publica en LOS 5 NODOS) **antes** de que el contenedor clásico de ese mismo nodo que necesita ese puerto llegue a arrancar — el clásico falla con `address already in use` y no se recupera solo. Ya se corrigió el caso conocido (dashboard de Traefik movido de 8090 a 18090, que chocaba con `capataz-frontend` en `pi-utils`), pero **si mañana algo se queda en `Restarting`/`Exited` tras el encendido, sospecha primero de un choque de puertos** (`sudo ss -tlnp | grep <puerto>` en ese nodo) antes de asumir que es un fallo de la aplicación.
- **Segundo gotcha real, mismo día**: un contenedor clásico que falló su primer arranque (por el choque de puertos de arriba, o por lo que sea) puede quedarse reintentando sobre sí mismo en un estado inconsistente incluso después de arreglar la causa raíz — `docker compose restart` no basta. Si ves algo en bucle de reinicio sin motivo aparente tras solucionar lo obvio, prueba `docker compose up -d --force-recreate <servicio>` antes de investigar más a fondo.

## Por qué importa el orden

- **Al apagar**: no hace falta un orden estricto entre nodos — cada `docker compose down`/parada de Swarm es local. Lo que sí es crítico, igual que antes de Swarm, es **no cortar la alimentación en frío**: siempre `sudo poweroff` limpio antes de desconectar. Las Raspberry Pi arrancan desde tarjeta SD, sensibles a corrupción si se corta la alimentación a medio escribir; `retaco`/`pinchi` tienen SSD, más tolerantes pero con el mismo riesgo — ahora además para el estado Raft de Swarm, no solo para `postgres-main`.
- **Al encender**: `retaco` primero sigue siendo obligatorio (postgres-main + authentik). El resto de nodos del swarm (`pi-obs`, `pi-sonar`, `pi-utils`, `pinchi`) pueden encenderse en cualquier orden entre ellos — Swarm no exige un orden concreto entre managers, solo que todos puedan verse entre sí eventualmente. `pi-dns` sigue sin depender de nada del swarm para arrancar su propio Compose clásico, pero su `apikey-service` local sí necesita `retaco` arriba para pasar su healthcheck, igual que antes.

## Apagado

Todo lo siguiente se ejecuta desde `mole` (`ryzen`), que se queda encendida — usa los mismos usuarios SSH por IP de `shared/scripts/` (`u-data`, `u-dns`, `u-obs`, `u-sonar`, `u-utils`, `u-forge`).

### 1. Parar el Docker de `mole` (opcional, según lo que vayas a hacer)

```bash
cd /srv/homelab/ryzen
docker compose down
docker compose -f docker-compose.observability.yml down
```

### 2. Parar el Compose clásico y apagar el sistema operativo de cada nodo

En los nodos que son también miembros del swarm (`pi-obs`, `pi-sonar`, `pi-utils`, `retaco`, `pinchi`) **no hace falta** `docker stack rm` de nada ni sacar el nodo del swarm — simplemente `sudo poweroff` para el `Compose` clásico que exista en ese nodo, el swarm se para solo con `dockerd`. `pinchi` no tiene Compose clásico propio, solo se apaga.

Orden sugerido — el inverso al de instalación, por costumbre y simetría con `docs/01-topologia.md`, aunque para el apagado en sí no es obligatorio (sí lo es no saltarse el `sudo poweroff` limpio en cada uno):

```bash
for target in \
  "u-forge@192.168.1.175:pinchi:no-compose" \
  "u-utils@192.168.1.173:pi-utils" \
  "u-sonar@192.168.1.172:pi-sonar" \
  "u-obs@192.168.1.171:pi-obs" \
  "u-dns@192.168.1.170:pi-dns" \
  "u-data@192.168.1.174:retaco"
do
  ssh_target="${target%%:*}"
  rest="${target#*:}"
  node="${rest%%:*}"
  echo "=== ${node} ==="
  if [ "${rest}" != "${node}" ]; then
    # pinchi: sin docker-compose.yml propio, solo apagar
    ssh -o BatchMode=yes "${ssh_target}" "sudo poweroff"
  else
    ssh -o BatchMode=yes "${ssh_target}" "cd /srv/homelab/${node} && docker compose down"
    ssh -o BatchMode=yes "${ssh_target}" "sudo poweroff"
  fi
done
```

### 3. Confirmar que cada nodo ha terminado de apagarse antes de tocar nada físico

```bash
for ip in 192.168.1.170 192.168.1.171 192.168.1.172 192.168.1.173 192.168.1.174 192.168.1.175; do
  echo -n "${ip}: "
  timeout 2 ping -c 1 "${ip}" >/dev/null 2>&1 && echo "todavía responde" || echo "apagado"
done
```

⚠️ No desconectes la alimentación de un nodo mientras siga respondiendo a `ping` — significa que el sistema operativo aún no ha terminado de apagarse (SonarQube en `pi-sonar` en particular puede tardar unos segundos más que el resto en pararse limpio, motor Java/Elasticsearch de por medio).

Con los seis nodos sin respuesta, ya es seguro hacer la intervención física.

## Encendido

### 1. Alimentación física

Reconecta la alimentación de los seis nodos. Las Raspberry Pi 5 (`pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils`) arrancan solas en cuanto reciben alimentación por USB-C, sin necesidad de pulsar nada. `retaco` y `pinchi` (PCs mini) pueden o no arrancar solos según su propio ajuste de BIOS "Restore AC Power Loss"/similar — si alguno no arranca solo a los 30-60 segundos de reconectar la alimentación, pulsa su botón de encendido físico.

### 2. `retaco` primero — obligatorio

```bash
ssh u-data@192.168.1.174 "cd /srv/homelab/retaco && docker compose up -d"

# Esperar a que postgres-main esté "healthy" (healthcheck pg_isready,
# start_period 30s) antes de continuar:
ssh u-data@192.168.1.174 "cd /srv/homelab/retaco && docker compose ps"
```

No sigas al siguiente paso hasta ver `postgres-main` (y, si puedes esperar un poco más, `authentik-server`) como `healthy` en esa salida — ahora alimentan tanto al `apikey-service` de `pi-dns` como al forward-auth de `prometheus.home.arpa` en Traefik.

### 3. `pi-dns` — obligatorio antes de dar el clúster por operativo

```bash
ssh u-dns@192.168.1.170 "cd /srv/homelab/pi-dns && docker compose up -d"
ssh u-dns@192.168.1.170 "cd /srv/homelab/pi-dns && docker compose ps"
```

`pi-dns` es quien resuelve **todo** `*.home.arpa`/`*.404labo.net` para el resto del clúster (incluidos los propios nodos del swarm entre sí, si usan nombre en vez de IP) — sin él arriba, nada resuelve nombres, aunque Traefik/Swarm estén perfectamente sanos. `nginx` espera solo internamente a `pihole` y `apikey-service` (`depends_on: condition: service_healthy` dentro del propio `docker-compose.yml`) — Compose gestiona ese orden interno solo, lo único que tenías que garantizar tú era `retaco` arriba (paso 2).

Comprueba también que el subnet router de Tailscale se ha reconectado solo (usa el estado persistido, no hace falta volver a autenticar):

```bash
ssh u-dns@192.168.1.170 "docker exec tailscale tailscale status"
```

### 4. `pinchi` y el resto de nodos del swarm — cualquier orden, incluso en paralelo

`pinchi` no tiene `docker-compose.yml` propio — basta con que arranque y su Docker se una de nuevo al swarm solo (persiste su identidad, no hace falta re-hacer `docker swarm join`). Los otros tres (`pi-obs`, `pi-sonar`, `pi-utils`) sí necesitan su Compose clásico a mano, **además** de reincorporarse solos al swarm:

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

⚠️ **Vigila específicamente `capataz-frontend` en `pi-utils`** (sirve `index.home.arpa`/ `home.404labo.net`) — es el que se vio afectado en vivo por el choque de puertos con el dashboard de Traefik (ya corregido, puerto movido a 18090) y por el contenedor atascado que necesitó `--force-recreate` (ver "Qué ha cambiado con Docker Swarm" arriba). Si tras este paso `docker compose ps` en `pi-utils` lo muestra `Exited`/reiniciando sin parar:

```bash
ssh u-utils@192.168.1.173 "sudo ss -tlnp | grep ':8090'"   # ¿algo más ya tiene el puerto?
ssh u-utils@192.168.1.173 "cd /srv/homelab/pi-utils && docker compose up -d --force-recreate capataz-frontend"
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

### Swarm — primero, antes que nada de aplicación

```bash
ssh u-forge@192.168.1.175 "docker node ls"
```

Espera ver los 5 nodos (`pi-obs`, `pi-sonar`, `pi-utils`, `pinchi`, `retaco`) en `Ready`/`Active`, y **exactamente uno** con `MANAGER STATUS` = `Leader` (da igual cuál — Raft elige uno solo, no tiene por qué ser `pinchi` aunque fue el nodo de bootstrap original). Si alguno aparece `Down` o `Unreachable` más de un minuto después de que respondiera al ping, revisa el firewall de control de Swarm en ese nodo (`docker-swarm/init/setup-swarm-firewall.sh`, puertos 2377/7946/4789) antes de asumir que es un problema de aplicación.

```bash
ssh u-forge@192.168.1.175 "docker service ls"
```

Espera réplicas al completo en todos: `traefik_traefik` `5/5`, `common_node-exporter` `5/5`, `common_cadvisor` `5/5`, `portainer-agent_agent` `5/5`, `apikey-service_apikey-service` `1/1`, `markitdown_markitdown-service` `1/1`. Si alguno tarda en converger, dale un par de minutos — Swarm reprograma solo, no hace falta intervenir salvo que se quede atascado bastante más tiempo.

### Aplicación — igual que antes, más las rutas nuevas de Traefik

⚠️ **`check-health.sh` inspecciona contenedores Docker y endpoints en `127.0.0.1` — solo tiene sentido ejecutado *localmente en cada nodo*, no desde `mole` apuntando a otro nodo por nombre**, y **todavía no conoce `pinchi`** (pendiente extenderlo, `docs/31-docker-swarm.md`). Ejecutado mal, `docker inspect` mira el Docker de `mole` (donde esos contenedores no existen → falsos `[FAIL]`) y `127.0.0.1` es el propio `mole`, no el nodo real. La forma correcta es por SSH:

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

Comprobaciones puntuales adicionales — el destino real ahora es `pinchi` (192.168.1.175), no `pi-dns`, para la mayoría de hostnames:

```bash
dig +short grafana.home.arpa @192.168.1.170        # debe resolver a 192.168.1.175
curl -sk https://index.home.arpa -o /dev/null -w "HTTP %{http_code}\n"           # 200, vía Traefik/pinchi
curl -sk https://markitdown.home.arpa -o /dev/null -w "HTTP %{http_code}\n"      # 401 (sin API key, esperado)
curl -sk https://home.404labo.net -o /dev/null -w "HTTP %{http_code}\n"          # 200, cert real Let's Encrypt
curl -sk https://apikey.home.arpa/health -o /dev/null -w "HTTP %{http_code}\n"   # 200, vía nginx/pi-dns (excepción)
```

Si algo no sale `healthy`/`200` a la primera:
- Si es un servicio de **Compose clásico** (postgres, authentik, sonarqube, capataz...): revisa el orden — el fallo más común sigue siendo `apikey-service` reintentando conexión porque `retaco` no terminó de arrancar antes (se autocorrige solo en segundos).
- Si es algo servido por **Traefik** (la mayoría de hostnames hoy): revisa primero `docker node ls`/`docker service ls` arriba antes que la aplicación en sí — muchas veces el problema real está en que el swarm todavía no ha terminado de reprogramar esa réplica, no en el servicio.
