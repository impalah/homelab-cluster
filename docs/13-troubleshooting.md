# 13 — Resolución de problemas

## DNS y resolución de nombres

### Síntoma: `*.home.arpa` no resuelve

**Diagnóstico:**

```bash
dig openwebui.home.arpa @192.168.1.170
cat /etc/resolv.conf   # Debe mostrar: nameserver 192.168.1.170
ssh homelab@192.168.1.170 "docker compose -f /srv/homelab/pi-dns/docker-compose.yml ps pihole"
```

**Soluciones:**

1. Si `resolv.conf` no apunta a `192.168.1.170`:
   ```bash
   sudo tee /etc/resolv.conf <<'EOF'
   nameserver 192.168.1.170
   nameserver 1.1.1.1
   EOF
   ```
2. Si Pi-hole no está en marcha: `ssh homelab@192.168.1.170 "cd /srv/homelab/pi-dns && docker compose up -d"`.
3. Si Pi-hole está en marcha pero no resuelve `.home.arpa`: verificar los registros en **Settings → DNS Records** de Pi-hole.

---

### Síntoma: un cliente Linux no resuelve `*.home.arpa` aunque `pi-dns` ya está sano de nuevo

Tras un apagón/reinicio/recarga de `pi-dns` (incluso un `nginx -s reload`): el cliente estaba activo en ese instante, `systemd-resolved` marcó `192.168.1.170` como no disponible y pasó al DNS secundario — pero **no reintenta el primario solo**, aunque `pi-dns` ya esté operativo. No es exclusivo de un equipo concreto — se ha observado en varios nodos, incluidos Raspberry Pi.

**Ojo con los contenedores Docker del nodo afectado**: el DNS embebido (`127.0.0.11`) reenvía al resolver del host — si el host tiene este problema, **todos sus contenedores también dejan de resolver**, incluidas apps JVM (SonarQube), que lo manifiestan como `UnknownHostException` y suelen entrar en bucle de reinicio.

**Diagnóstico:**

```bash
resolvectl status enp6s0    # sustituir por la interfaz activa
resolvectl query grafana.home.arpa
```

**Solución:**

```bash
sudo systemctl restart systemd-resolved
```

Limpia la caché y el estado de selección de servidor. No hace falta tocar `nmcli`.

---

## nginx — proxy inverso

### Síntoma: `502 Bad Gateway` al acceder a un servicio

**Diagnóstico:**

```bash
ssh homelab@192.168.1.170 "docker exec nginx nginx -t"
ssh homelab@192.168.1.170 "docker compose -f /srv/homelab/pi-dns/docker-compose.yml logs --tail=50 nginx"
curl -s http://192.168.1.150:8080  # open-webui, por ejemplo
```

**Soluciones:**

1. Servicio de destino no está en marcha → arrancar el stack del nodo.
2. IP o puerto incorrectos → revisar `pi-dns/config/nginx/nginx.conf`.
3. **Puerto publicado solo en `127.0.0.1`** en el `docker-compose.yml` del nodo destino — nginx se ejecuta en otra máquina física, el servicio debe publicarse en todas las interfaces. Comprobar con `ss -tlnp | grep PUERTO`.
4. `docker exec nginx nginx -s reload` tras cambios.

### Síntoma: `401 Unauthorized` inesperado en un servicio protegido con apikey-service

**Diagnóstico:**

```bash
# ¿Falta la cabecera, o la key es incorrecta/revocada?
curl -sk -v https://ollama.home.arpa/api/tags -H "X-Api-Key: <key>" 2>&1 | grep -i "< HTTP"

# ¿La key existe y está activa?
curl -sk https://apikey.home.arpa/keys -H "Authorization: Bearer ${APIKEY_ADMIN_TOKEN}" | jq .
```

**Causas comunes:**
- Cabecera mal escrita (`X-Api-Key`, no `Api-Key` ni `X-API-KEY` — nginx/FastAPI son insensibles a mayúsculas en el nombre, pero un error tipográfico real no coincide).
- Key revocada (`revoked_at` no nulo en la respuesta de `GET /keys`).
- Confundir el mecanismo: Qdrant usa su **propia** auth nativa (cabecera `api-key`, sin `X-`), no `apikey-service`. Ver `docs/06-instalacion-pi1-dns.md`.

### Síntoma: cambios en `nginx.conf` no se aplican pese a `nginx -s reload`

**Causa:** si el fichero llegó por `rsync`/`scp` (que por defecto hacen rename atómico: escriben a un temporal y renombran), el bind mount de un fichero único del contenedor sigue apuntando al **inodo viejo** — Docker monta ese inodo concreto al crear el contenedor, no "el fichero en esa ruta". `nginx -s reload` relee el fichero que el contenedor todavía ve, que sigue siendo el antiguo.

**Diagnóstico:**

```bash
docker exec nginx cat /etc/nginx/nginx.conf | grep <algo-que-acabas-de-añadir>
# Si no aparece pese a que el fichero en el host sí lo tiene: es esto.
```

**Solución:**

```bash
docker compose up -d --force-recreate nginx
```

No basta con `reload` ni con `restart` — hace falta recrear el contenedor para que tome el inodo nuevo. Mismo problema aplica a cualquier otro servicio con un bind mount de fichero único (no de directorio) actualizado por `rsync`/`scp`.

### Síntoma: el navegador avisa de certificado no confiable

Esperado — certificado firmado por la CA interna del clúster, no una CA pública (`*.home.arpa` no es un dominio público). Añadir excepción en el navegador, `-k`/`--insecure` con `curl`, o instalar la CA (`docs/15-ca-interna.md`).

---

## SonarQube no arranca

**Causa más común:** `vm.max_map_count` insuficiente.

```bash
sysctl vm.max_map_count
sudo sysctl -w vm.max_map_count=524288
# Y en /etc/sysctl.d/99-homelab-sonar.conf para persistencia
```

**Causa secundaria:** permisos incorrectos: `sudo chown -R 1000:1000 /srv/homelab/pi-sonar/sonarqube/`.

---

## Ollama / vLLM — GPU no detectada o memoria insuficiente

### GPU no detectada

```bash
docker run --rm --gpus all nvidia/cuda:12.3.1-base-ubuntu22.04 nvidia-smi
docker exec ollama nvidia-smi
```

Si falla en el host: `sudo apt install -y nvidia-driver-535`. Si falla solo dentro del contenedor: `sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker`.

### `torch.OutOfMemoryError` al arrancar vLLM

Ver `docs/07-instalacion-ryzen.md` sección vLLM — causa típica en este clúster: la GPU 0 comparte VRAM con el escritorio (monitor conectado ahí), dejando menos margen real del que sugiere el tamaño nominal de la tarjeta. Bajar `VLLM_GPU_MEM_UTIL` no siempre basta si el fallo ocurre cargando pesos (no reservando KV-cache) — en ese caso hace falta un modelo más pequeño o liberar la GPU del todo.

### whisper-service — arranque lento o timeout

Modelo `large-v3` puede tardar 90–120s en cargar (`start_period: 90s` en el healthcheck).

```bash
docker compose logs -f whisper-service   # esperar "Application startup complete."
df -h /srv/homelab/ryzen/whisper/        # large-v3 requiere ~3 GB
docker exec whisper-service ls /root/.cache/whisper/
```

---

## PostgreSQL — conexión rechazada

### Síntoma: sonarqube (pi-sonar) no puede conectar a postgres-main (retaco)

`n8n-main` está co-localizado con `postgres-main` (mismo host, `retaco-net`) — `sonarqube` sigue conectando entre nodos mediante `postgresql.home.arpa:5432`, así que a los fallos habituales se suma el alcance de red/DNS entre nodos.

**Diagnóstico:**

```bash
ping -c1 192.168.1.174
nc -zv 192.168.1.174 5432
ssh pi-sonar "resolvectl query postgresql.home.arpa"
ssh retaco "cd /srv/homelab/retaco && docker compose ps postgres-main"
ssh pi-sonar "docker logs sonarqube --tail=50 2>&1 | grep -i jdbc"
```

**Soluciones:** `retaco` apagado → arrancarlo; `postgresql.home.arpa` no resuelve → reiniciar `systemd-resolved` en `pi-sonar`; `postgres-main` no healthy → ver sección siguiente; credenciales desincronizadas → `SONARQUBE_DB_PASSWORD` debe coincidir exactamente (`docs/05-instalacion-retaco.md`).

### DNS caído en varios nodos a la vez — `shared/scripts/fix-dns-resolver.sh`

Mismo síntoma que el de arriba (`systemd-resolved` cayendo al DNS secundario del netplan, `1.1.1.1`, en vez de `pi-dns`), pero comprobado y corregido en `pi-dns`, `pi-obs`, `pi-sonar`, `pi-utils` y `retaco` de una vez, por SSH desde `mole`:

```bash
bash shared/scripts/fix-dns-resolver.sh all       # todos
bash shared/scripts/fix-dns-resolver.sh pi-sonar  # uno solo
```

### Causa raíz real, identificada en vivo: ráfaga de DNS de un workflow de n8n satura Unbound

**Síntoma**: justo después de ejecutar el workflow **"RSS Fetch & Store"** en `n8n-main` (retaco), `retaco` deja de resolver `postgresql.home.arpa` — `resolvectl status` muestra `Current DNS Server: 1.1.1.1` en vez de `192.168.1.170`, aunque ambos siguen en la lista de `DNS Servers`.

**Diagnóstico confirmado** (no es network flakiness aleatoria):

```bash
# Log de n8n-main: errores de resolución DNS del propio Node.js
docker logs n8n-main --since 60m 2>&1 | grep -i "host not found\|GetAddrInfoReqWrap"

# Log de Pi-hole: cuántas consultas llegaron de retaco en el mismo segundo
# del fallo (ajustar la hora — recordar que el log de Pi-hole va en hora
# LOCAL y journalctl/docker logs del host suelen ir en UTC)
docker exec pihole grep 'Aug  1 14:30:58' /var/log/pihole/pihole.log | grep -c '192.168.1.174'
```

En el incidente real que motivó esto: **353 consultas DNS desde `retaco` en un único segundo** — el workflow resuelve decenas de dominios de feeds RSS (`raw.githubusercontent.com`, `huggingface.co`, `openai.com`, `hackernoon.com`, etc.) prácticamente a la vez. Unbound (`pi-dns`, una Raspberry Pi) tiene que hacer resolución recursiva completa para la mayoría — muchos sin caché la primera vez — y bajo ese pico alguna consulta se retrasa lo suficiente como para que `systemd-resolved` en `retaco` la dé por fallida y pase a `1.1.1.1`, quedándose ahí "pegado" (comportamiento conocido de `systemd-resolved`: no reintenta el servidor preferido solo tras un fallo, hay que forzarlo — de ahí `fix-dns-resolver.sh`).

**Mitigado (aplicado)**: `num-threads` de Unbound subido de 4 a 8 (con los `*-cache-slabs` a juego) — más margen para absorber picos de consultas simultáneas sin encolarse. Ver el comentario en `pi-dns/config/unbound/unbound.conf`. Esto reduce la probabilidad del fallo, pero **no ataca la causa real**.

**Arreglo real pendiente (fuera de este repo)**: limitar la concurrencia del propio workflow "RSS Fetch & Store" en n8n (batching/throttling del nodo que dispara las peticiones a cada feed), para que no genere cientos de resoluciones DNS en el mismo instante. Es un cambio en la definición del workflow, no en la infraestructura — se gestiona desde la propia interfaz o API de n8n, no desde este repo.

Hace una prueba **funcional** (resuelve un hostname `*.home.arpa` real y compara la IP con la esperada — no lee el campo "Current DNS Server" de `resolvectl status`, que ni siquiera aparece cuando `resolv.conf mode` es `stub`, el habitual en estos nodos, y da falsos positivos de fallo). Si no resuelve correctamente, reinicia `systemd-resolved` en ese nodo y reintenta.

### Síntoma: `postgres-main` "healthy" pero consultas fallan con `Permission denied`

**Causa:** el directorio de datos en el host perdió la propiedad correcta (`postgres:16-alpine` se ejecuta como **UID 70**). `pg_isready` solo comprueba que el servidor acepta conexiones, no que pueda leer sus ficheros — sigue "healthy" mientras las consultas reales fallan.

**Causa más probable:** re-ejecutar `prepare-host.sh <nodo>` en un nodo con `postgres-main` ya poblado, sin que ese directorio tuviera su excepción de `chown` explícita — pasó exactamente así con `retaco` al añadir `n8n-main`.

**Diagnóstico:**

```bash
docker exec postgres-main id postgres
docker exec postgres-main ls -la /var/lib/postgresql/data/pgdata | head -3
```

**Solución:**

```bash
sudo chown -R 70:70 /srv/homelab/<nodo>/postgres/data
docker compose restart postgres-main
```

**Prevención:** `prepare-host.sh` ya incluye esta excepción para `retaco`. Al añadir Postgres (u otro servicio con UID propio) a un nodo nuevo, añadir su excepción **antes** de re-ejecutar el script ahí.

---

## Cortafuegos — `ufw` e `iptables-persistent` se pisan entre sí

**Síntoma:** al instalar `iptables-persistent` (necesario para `toggle-direct-access.sh`, `docs/17-firewall-acceso-directo.md`), `apt` desinstala `ufw` sin avisar explícitamente en el resumen (o viceversa, si se instala `ufw` después).

**Causa confirmada en este clúster** (los 5 nodos con Docker, no es teórico): ambos paquetes entran en conflicto en Ubuntu/Debian. `setup-firewall.sh` resuelve esto purgando `ufw` explícitamente antes de instalar `iptables-persistent` — no se puede tener ambos a la vez de forma fiable, y `ufw` no aporta nada al mecanismo real (que usa la cadena `DOCKER-USER` directamente, no reglas de `ufw`).

**Si aparece de nuevo:** volver a ejecutar `bash shared/scripts/setup-firewall.sh <nodo>` — es idempotente y deja el estado correcto (`ufw` purgado, `iptables-persistent` instalado).

### Síntoma: el bloqueo de `toggle-direct-access.sh off` parece no funcionar

**Causa casi segura:** se probó desde el **mismo nodo** que se acaba de cerrar. Tráfico "de una máquina a su propia IP de LAN" puede tomar un atajo de enrutado local que no atraviesa la cadena `FORWARD`/`DOCKER-USER` — confirmado en vivo (0 paquetes contados en las reglas). Probar siempre desde **otro** nodo: `sudo iptables -L DOCKER-USER -n -v` para ver los contadores reales. Detalle completo: `docs/17-firewall-acceso-directo.md`.

---

## Pi-hole

### Puerto 53 en uso

```bash
ss -tulpn | grep ':53'
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved
sudo rm /etc/resolv.conf
echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf
docker compose up -d pihole
```

### Variables de entorno de v5 ignoradas en silencio (v6)

`pihole/pihole:latest` es v6 — `WEBPASSWORD`/`DNSMASQ_LISTENING` (v5) ya no dan error, simplemente se ignoran.

**Síntoma: la contraseña de `.env` no funciona:**

```bash
docker logs pihole 2>&1 | grep -i password
# "No password set..., assigning random password" confirma que WEBPASSWORD fue ignorada
```

Solución inmediata: `docker exec pihole pihole setpassword 'TU_CONTRASEÑA'`. Solución de fondo: usar `FTLCONF_webserver_api_password` (ya aplicado en este repo).

**Síntoma: resuelve en `127.0.0.1` pero no responde desde la LAN:**

```bash
docker logs pihole 2>&1 | grep -i "non-local network"
```

Causa: `dns.listeningMode` en `LOCAL` por defecto — solo acepta consultas de la red Docker interna, no de la LAN real. Solución de fondo: `FTLCONF_dns_listeningMode: ALL` (ya aplicado).

### Registro DNS añadido por API desaparece tras reiniciar `pihole`

La API confirma el cambio al momento, pero la escritura a disco de `pihole.toml` puede no ser síncrona — reiniciar el contenedor en esa ventana pierde el cambio sin aviso.

```bash
ssh pi-dns "docker exec pihole grep -A25 'hosts = \[' /etc/pihole/pihole.toml"
dig +short <hostname>.home.arpa @192.168.1.170
```

Solución: reaplicar (`load-dns-records.sh`) y esperar unos segundos antes de reiniciar el contenedor, verificando en disco.

### Bloquea anuncios en Linux pero no en macOS/Windows

DNS del sistema bien configurado, pero navegador/sistema resolviendo por un canal que no pasa por Pi-hole:

1. **DNS-over-HTTPS del navegador** (Chrome/Edge): `chrome://settings/security` → **Usar DNS seguro** → "Con el proveedor de red actual".
2. **iCloud Private Relay** (macOS/iOS): Ajustes → ID de Apple → iCloud → Private Relay.
3. **DNS manual puesto a mano**, ignorando el DHCP del router.

```bash
scutil --dns | grep -A 3 "resolver #1"   # macOS
```

---

## Vaultwarden

### Síntoma: la extensión de Bitwarden conecta y sincroniza, pero no muestra las contraseñas en el editor

En la consola del navegador aparece un error del tipo:

```
Uncaught Error: Error: invalid type: JsValue(Object({"fido2Credentials":[],"fields":[],"name":"2....",...})), expected a string
    at bitwarden_wasm_internal_bg.js
```

**Causa:** desajuste de protocolo entre los clientes oficiales de Bitwarden y la versión de Vaultwarden desplegada. Los clientes (extensión de navegador, app móvil, web vault) se actualizan solos y sin avisar; el servidor autoalojado no. A partir de los clientes `2026.7.0`, el proceso de sincronización usa un esquema nuevo que versiones de Vaultwarden anteriores a `1.37.0` no entienden del todo — el cliente, con su parser estricto en Rust/WASM, falla al deserializar la respuesta y se queda sin poder desencriptar el vault, aunque la sincronización en sí (lectura/escritura) siga funcionando. Caso real detectado en este clúster (2026-08): extensión de Chrome actualizada a un `2026.7.x`, servidor todavía en `vaultwarden/server:1.36.0`.

Existe también una causa alternativa, no descartable si el problema reaparece: un cifrado (login) creado mediante una herramienta de terceros —por ejemplo, insertado directamente vía API en vez de desde un cliente oficial— con el campo `name` guardado como texto plano en lugar de cadena cifrada. Un solo ítem así corrompe la sincronización completa del vault, no solo la suya. Se detecta buscando en la tabla `ciphers` de `db.sqlite3` cualquier campo que no tenga el formato `2.xxxx==|yyyy==|zzzz=` propio de una cadena cifrada de Bitwarden.

**Solución (probar primero, resuelve la mayoría de los casos):** actualizar la imagen de Vaultwarden.

```bash
bash /srv/homelab/shared/scripts/backup-vaultwarden.sh   # backup antes de tocar nada
```

En `pi-utils/docker-compose.yml`, cambiar la etiqueta de la imagen:

```yaml
vaultwarden:
  image: vaultwarden/server:1.37.0
```

```bash
ssh u-utils@192.168.1.173
cd /srv/homelab/pi-utils
docker compose pull vaultwarden
docker compose up -d vaultwarden
```

Tras el redeploy, cerrar sesión en la extensión del navegador y volver a iniciarla (no basta con recargar la ventana) — confirmado en vivo en este clúster.

**Si tras actualizar el problema persiste:** buscar un cifrado corrupto en la base de datos.

```bash
ssh u-utils@192.168.1.173
sudo apt install -y sqlite3
cd /srv/homelab/pi-utils && docker compose stop vaultwarden

sqlite3 /srv/homelab/pi-utils/vaultwarden/data/db.sqlite3
```

```sql
.headers on
.mode column
SELECT uuid, name, user_uuid, deleted_at FROM ciphers;
```

Localizar el `uuid` cuyo `name` no siga el formato `2.xxxx==|yyyy==|zzzz=` y borrarlo (un simple envío a la papelera no es suficiente, hay que eliminarlo de verdad):

```sql
DELETE FROM ciphers WHERE uuid = '<uuid-del-item-corrupto>';
.quit
```

```bash
docker compose up -d vaultwarden
```

---

## Grafana — datasource no conecta

```bash
docker exec grafana wget -qO- http://prometheus:9090/-/healthy
docker exec grafana wget -qO- http://loki:3100/ready
docker exec grafana wget -qO- http://tempo:3200/ready
docker network inspect pi-obs-net   # si no resuelven
```

---

## Tras apagar y encender el clúster: servicios que no arrancan solos

### 1. `depends_on` no se respeta en un arranque automático

Solo ordena el arranque con `docker compose up` explícito — el reinicio automático tras reboot del host (`restart: unless-stopped`) no pasa por `docker compose`, cada contenedor arranca independiente, ignorando el grafo de dependencias.

**Solución, siempre, tras cualquier reboot:**

```bash
cd /srv/homelab/<nodo>
docker compose up -d
```

### 2. nginx no arranca si `pihole` no resuelve en ese instante exacto

Ya corregido de raíz: el upstream de `pihole.home.arpa` usa resolución diferida (`resolver 127.0.0.11` + variable), no falla aunque `pihole` tarde.

### 3. Colisión de IP fija en `pi-dns-net`

Ya corregido de raíz: todos los contenedores de esa red tienen IP fija explícita.

### 4. `/etc/resolv.conf` de pi-dns apuntando a `1.1.1.1` en vez de a sí mismo

Ver `docs/06-instalacion-pi1-dns.md` sección 6.1 — paso manual fácil de pasar por alto.

### Procedimiento recomendado de apagado/encendido

- **Apagar:** el orden no importa mucho.
- **Encender:** `pi-dns` primero, siempre con `docker compose up -d` explícito (nunca confiar solo en el arranque automático), luego el resto en cualquier orden.
- **Verificar:** `check-health.sh <nodo>` en cada uno.

---

## Raspberry Pi — baja tensión (undervoltage)

### Síntoma: un nodo Raspberry Pi se apaga o se cuelga sin motivo aparente

```bash
sudo journalctl --list-boots
sudo journalctl -b 0 --no-pager | grep 'Undervoltage detected'
sudo journalctl -b -1 -u systemd --no-pager | grep -iE 'poweroff|Shutting down|System Power Off'
```

**Causa:** el kernel registra `Undervoltage detected!` cuando la fuente no entrega los 5V estables que exige la Pi 5. Caso real detectado en este clúster (2026-07-22): `pi-dns` con 348 avisos en menos de una hora, corte real (no apagado ordenado). Resto de nodos limpios salvo `pi-sonar` (22 avisos, episodio único, no reapareció).

**Solución:** cargador oficial Pi 5 (27W USB-C PD), cable USB-C de calidad (5A, con chip e-marker), sin alargadores/hubs entre cargador y Pi, periféricos USB alimentados aparte.

**Revisión periódica:**

```bash
for host in "u-dns@192.168.1.170" "u-obs@192.168.1.171" "u-sonar@192.168.1.172" "u-utils@192.168.1.173"; do
  echo "=== ${host} ==="
  ssh "${host}" "sudo journalctl -b 0 --no-pager | grep -c 'Undervoltage detected'"
done
```

### Aviso SSH "This power supply is not capable of supplying 5A..."

No es lo mismo que `Undervoltage detected!` — dos comprobaciones independientes de `pemmican-cli`:

1. **Caída de tensión real** — aviso serio, no silenciar nunca.
2. **Negociación de 5A** — solo limita la corriente en los puertos USB de la propia Pi; sin periféricos USB conectados, no tiene efecto práctico.

Silenciar solo el punto 2, tras confirmar que no hay avisos de baja tensión activos:

```bash
ssh u-dns@192.168.1.170 "sudo mkdir -p /etc/xdg/pemmican && sudo touch /etc/xdg/pemmican/max_current.inhibit"
```

Revertir: `sudo rm /etc/xdg/pemmican/max_current.inhibit`.

---

## Comandos de diagnóstico general

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker compose logs --tail=20 2>&1 | grep -E "(ERROR|WARN|error|warn|fatal)"
docker events --since 1h
ping -c 3 192.168.1.170
traceroute 192.168.1.171
nmap -p 80,443,53,9000,3000,5678 192.168.1.170
```
