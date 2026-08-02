# 18 — Tailscale: acceso remoto autenticado al clúster

## Qué resuelve

Acceso a todo el clúster desde fuera de la LAN, autenticado (solo dispositivos
que hayan iniciado sesión en el tailnet con la cuenta autorizada), sin abrir
ningún puerto en el router de casa. Un dispositivo remoto conectado a
Tailscale llega a cualquier IP de `192.168.1.0/24` y resuelve `*.home.arpa`
exactamente igual que si estuviera en la LAN.

## Arquitectura

```
Dispositivo remoto (móvil/portátil, con Tailscale)
  │  túnel WireGuard cifrado, autenticado por cuenta Tailscale
  ▼
pi-dns (192.168.1.170) — subnet router
  ├─ anuncia la ruta 192.168.1.0/24 al resto del tailnet
  └─ Pi-hole + Unbound (ya existían) — resuelven *.home.arpa
```

`pi-dns` hace de único punto de entrada remoto porque ya es el nodo DNS/proxy
del clúster (`docs/06-instalacion-pi1-dns.md`) — coherente con "resolver
`*.home.arpa`": las consultas DNS del tailnet llegan al mismo nodo que ya las
resuelve, sin saltos extra. Nada se instala en el resto de nodos — llegan a
través de la ruta anunciada, igual que cualquier otro tráfico de la LAN.

**Split DNS** (configurado en el panel de Tailscale, no en este repo): un
nameserver personalizado, restringido al dominio `home.arpa`, apuntando a
`192.168.1.170`. Solo las consultas de `*.home.arpa` se enrutan por el
tailnet — el resto del tráfico DNS del dispositivo remoto sigue su camino
normal (no es "forzar todo el DNS", es "split").

⚠️ Un dispositivo remoto necesita también confiar en la CA interna del
clúster para que las conexiones HTTPS a `*.home.arpa` no den aviso de
certificado — exactamente el mismo procedimiento que en cualquier equipo de
la LAN, ver `docs/15-ca-interna.md`. Tailscale resuelve el *acceso*, no el
*certificado*.

## Instalación

### 1. Contenedor en pi-dns

Servicio `tailscale` en `pi-dns/docker-compose.yml`, imagen oficial
`tailscale/tailscale`, `network_mode: host` (un subnet router necesita la
interfaz de red real del host, no la red bridge de Docker).

```bash
cd /srv/homelab/pi-dns
cp .env.example .env   # TS_AUTHKEY, ver sección 3
docker compose up -d tailscale
```

Variables relevantes (ver comentarios en el propio `docker-compose.yml`):

| Variable | Valor | Por qué |
|---|---|---|
| `TS_USERSPACE` | `false` | Sin esto tailscaled cae a modo userspace, que no puede enrutar tráfico ajeno — inútil para un subnet router. |
| `TS_EXTRA_ARGS` | `--advertise-routes=192.168.1.0/24 --accept-dns=false` | Anuncia la LAN; `--accept-dns=false` porque este nodo YA es el servidor DNS del clúster — dejar que Tailscale reescriba su propio `resolv.conf` rompería Pi-hole/Unbound. |
| `TS_STATE_DIR` | `/var/lib/tailscale` (con volumen persistente) | Sin esto, cada reinicio del contenedor genera una identidad de nodo nueva y hay que volver a autenticar. |

⚠️ **`/dev/net/tun` va en `devices:`, no en `volumes:`** — con `volumes:` el
contenedor no ve un nodo TUN real y tailscaled cae solo a
`--tun=userspace-networking` (mismo problema que el punto anterior). Pasó de
verdad en el primer despliegue.

### 2. IP forwarding y módulos de kernel (una vez, en el host)

```bash
# Forwarding IPv4 + IPv6 — necesario para que el subnet router enrute tráfico ajeno
cat <<'EOF' | sudo tee /etc/sysctl.d/99-tailscale.conf
net.ipv4.ip_forward = 1
net.ipv6.conf.all.forwarding = 1
net.ipv4.conf.all.src_valid_mark = 1
EOF
sudo sysctl -p /etc/sysctl.d/99-tailscale.conf

# Módulos de kernel para iptables (filter/nat, v4 y v6)
sudo modprobe ip_tables iptable_filter iptable_nat ip6_tables ip6table_filter ip6table_nat
cat <<'EOF' | sudo tee /etc/modules-load.d/tailscale.conf
ip_tables
iptable_filter
iptable_nat
ip6_tables
ip6table_filter
ip6table_nat
EOF
```

⚠️ **Por qué hace falta esto último**: el `iptables` (legacy) dentro del
contenedor no puede hacer `modprobe` él solo — sin `/lib/modules` montado
(`volumes: - /lib/modules:/lib/modules:ro` en el compose) falla con
`modprobe: can't change directory to '/lib/modules'`; con el volumen montado
pero sin los módulos ya cargados en el host, falla con
`modprobe: can't load module ip_tables ...: Operation not permitted` (cargar
módulos requiere `CAP_SYS_MODULE`, que deliberadamente **no** se le da al
contenedor — demasiado privilegio). La solución limpia es cargar los módulos
una vez en el host (visibles para el contenedor por compartir kernel, sin
necesidad de que el contenedor tenga permiso para cargarlos él mismo).
Sin este paso, `tailscale status` muestra un "Health check" avisando de que
la tabla `filter` no existe, y las reglas NAT/forwarding del subnet router no
funcionan aunque el nodo aparezca "online".

También se vio (y se corrigió) un aviso de
`failed to enable src_valid_mark: ... read-only file system` — mismo motivo
(el contenedor no puede tocar ese sysctl aunque comparta namespace de red con
el host por `network_mode: host`) — se fija desde fuera, en el host.

### 3. Autenticación

**Manual, en el panel de Tailscale** (`https://login.tailscale.com/admin/settings/keys`
→ *Generate auth key*):
- **Reusable: ON** — si el volumen de estado se pierde alguna vez, el
  contenedor puede volver a autenticarse solo con la misma key, sin
  intervención manual.
- **Ephemeral: OFF** — si quedara en ON, el nodo desaparecería del tailnet en
  cuanto el contenedor se reiniciara.
- Caduca a los 90 días por defecto — pasada esa fecha, si hace falta
  re-autenticar, generar una key nueva y actualizar `TS_AUTHKEY` en `.env`.

Copiar la key generada (`tskey-auth-...`) a `TS_AUTHKEY` en
`/srv/homelab/pi-dns/.env` (nunca en `.env.example`, nunca en el repo).

⚠️ **El inicio de sesión interactivo por URL (sin auth key) no funciona con
este contenedor** — se probó primero y falló: el script de arranque
(`containerboot`) mata el proceso de inicio de sesión a los ~60 segundos
(`tailscale up failed: signal: killed`) si no se ha completado, y Docker
reinicia el contenedor con una identidad de nodo nueva (nueva URL de inicio
de sesión) cada vez — un inicio de sesión por navegador nunca llega a
tiempo. La auth key evita esto por completo (inicio de sesión no
interactivo, casi instantáneo).

⚠️ Si el panel redirige siempre a la pantalla de "añade tu primer
dispositivo" (`/admin/welcome`) en vez de dejar llegar a *Settings → Keys*,
entrar directo a la URL de Keys de arriba suele saltarse esa redirección.

### 4. Aprobar la subnet route (manual, panel)

`https://login.tailscale.com/admin/machines` → nodo `pi-dns` → `···` →
*Edit route settings* → activar `192.168.1.0/24`. Tailscale exige un click
humano para aprobar rutas nuevas — no se puede hacer por API/CLI sin un
token de administración aparte, es intencional (una ruta aprobada
automáticamente sería una forma fácil de que un nodo comprometido se
anunciara como gateway de una red que no le corresponde).

Verificación desde el propio nodo:

```bash
docker exec tailscale tailscale status --json | python3 -c "
import json, sys
d = json.load(sys.stdin)['Self']
print('AllowedIPs:', d['AllowedIPs'])   # debe incluir 192.168.1.0/24
"
```

### 5. Split DNS (manual, panel)

`https://login.tailscale.com/admin/dns` → *Nameservers* → *Add nameserver* →
*Custom* → `192.168.1.170` → activar **Restrict to domain** → `home.arpa` →
guardar. **No** activar "Override local DNS" — el objetivo es que solo
`*.home.arpa` vaya por este nameserver, el resto del tráfico DNS del
dispositivo remoto sigue su camino normal.

### 6. (Recomendado) Desactivar caducidad de clave del nodo

`https://login.tailscale.com/admin/machines` → clic en el **nombre** del
nodo (`pi-dns-1`), no en el menú `···` de la fila (ahí no aparece la opción)
→ en la ficha de detalle del dispositivo, junto a "Key expiry" → *Disable*.
Por defecto las claves de nodo caducan a los ~180 días — para un subnet
router permanente (no un dispositivo personal), conviene desactivarlo; si
no, en 6 meses se desconecta solo del tailnet sin aviso previo, cortando el
acceso remoto hasta re-autenticar a mano.

## Uso desde un dispositivo cliente

1. Instalar la app oficial de Tailscale (móvil, portátil) e iniciar sesión
   con la cuenta autorizada.
2. Instalar la CA interna del clúster en ese dispositivo — `docs/15-ca-interna.md`
   (mismo procedimiento que cualquier equipo de la LAN).
3. Con Tailscale activo, cualquier `https://*.home.arpa` funciona igual que
   estando en casa — probado de verdad con datos móviles (fuera de la LAN),
   `index.home.arpa` resuelve y carga.

## Verificación

```bash
# En pi-dns
docker exec tailscale tailscale status          # el propio nodo, "online", ruta anunciada
docker inspect tailscale --format='RestartCount: {{.RestartCount}}'   # 0 = estable, sin crash-loop

# Desde un dispositivo remoto conectado a Tailscale (fuera de la LAN)
nslookup markitdown.home.arpa                    # debe devolver una IP 192.168.1.x
curl -sk https://index.home.arpa -o /dev/null -w "HTTP %{http_code}\n"
```

## Seguridad — decisiones tomadas y pendientes

- **Sin ACL personalizada por ahora** — cualquier dispositivo autenticado en
  el tailnet llega a todo el clúster (comportamiento por defecto de
  Tailscale). Suficiente para un tailnet personal de un único usuario; si
  en el futuro se añaden más cuentas/dispositivos al tailnet, revisar si
  conviene una política de ACL (tags, grupos) para restringir por
  dispositivo/usuario — no bloqueante, se puede añadir sin rehacer nada de
  lo anterior.
- **Tráfico remoto y el firewall `DOCKER-USER`** (`docs/17-firewall-acceso-directo.md`):
  el tráfico que llega a otros nodos a través de la ruta anunciada por
  `pi-dns` sale NAT'eado con la IP LAN de `pi-dns` (comportamiento por
  defecto de Tailscale, `snat=true`) — indistinguible del tráfico legítimo
  que ya generaba `nginx` proxificando peticiones. Si algún nodo tiene el
  acceso directo por IP y puerto restringido a "solo pi-dns"
  (`toggle-direct-access.sh <nodo> off`), el tráfico remoto por Tailscale
  sigue funcionando igual — es exactamente el comportamiento esperado (que
  Tailscale se sienta como estar en la LAN, pasando por pi-dns como de
  costumbre), no una forma de saltarse esa protección.
- **Sin puerto abierto en el router** — Tailscale usa NAT traversal
  (UDP 41641 saliente, con retransmisión mediante relés DERP de Tailscale si el
  tráfico directo no es posible). Si la conexión parece lenta/retransmitida,
  se puede abrir opcionalmente el puerto UDP 41641 hacia `192.168.1.170` en
  el router para favorecer conexión directa — no es necesario para que
  funcione, solo para rendimiento.

## Resolución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| El contenedor reinicia solo cada ~60s, cada vez con una URL de inicio de sesión distinta | Inicio de sesión interactivo sin auth key — `containerboot` lo mata a los 60s | Usar `TS_AUTHKEY` (sección 3), no inicio de sesión por URL |
| `tailscale status` muestra un bloque "Health check" quejándose de la tabla `filter`/`ip6tables` | Faltan módulos de kernel o `/lib/modules` no está montado | Sección 2 de este documento |
| `failed to enable src_valid_mark: ... read-only file system` | Sysctl no aplicable desde dentro del contenedor | `net.ipv4.conf.all.src_valid_mark=1` en el host (sección 2) |
| Dispositivo remoto no resuelve `*.home.arpa` | Split DNS no configurado, o "Restrict to domain" no activado | Sección 5 |
| DNS resuelve pero no conecta | Subnet route no aprobada en el panel | Sección 4 |
| Aviso de certificado no confiable en el navegador remoto | Esperado — falta instalar la CA interna en ese dispositivo | `docs/15-ca-interna.md` |
