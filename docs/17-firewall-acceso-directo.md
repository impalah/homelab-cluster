# 17 — Cortafuegos: activar y desactivar el acceso directo por IP y puerto

## El problema que resuelve

Todos los servicios HTTP expuestos mediante `*.home.arpa` (nginx en `pi-dns`)
también son alcanzables **directamente por IP y puerto** en su nodo real —
`https://ollama.home.arpa` y `http://192.168.1.150:11434` llegan al mismo
sitio. Esto es necesario para que nginx, que se ejecuta en *otro* nodo, pueda
alcanzarlos — pero significa que cualquiera en la LAN puede saltarse
`apikey-service` (`docs/06-instalacion-pi1-dns.md`) usando la IP directa en vez del nombre de host.

Este documento cubre cómo cerrar ese acceso directo cuando se quiera, sin
tocar nginx ni los servicios en sí: **solo pi-dns puede alcanzar esos
puertos**, todo el resto del tráfico tiene que pasar por
`https://*.home.arpa` como está pensado.

## ⚠️ Por qué "ufw deny `<puerto>`" NO funciona con Docker

Este es el motivo por el que este documento no es solo "instala ufw y ya":

Docker inserta sus propias reglas `DNAT` directamente en las cadenas
`FORWARD`/`PREROUTING` de `iptables` para enrutar el tráfico de un puerto
publicado (`ports: "11434:11434"`) hacia el contenedor. Ese tráfico
**nunca atraviesa la cadena `INPUT`**, que es donde vive `ufw`. Resultado:
`sudo ufw deny 11434` no tiene ningún efecto sobre un puerto publicado por
Docker — sigue abierto a toda la LAN exactamente igual, aunque `ufw`
diga "denied".

La solución oficial de Docker (documentada por el propio proyecto) es usar
la cadena **`DOCKER-USER`**: un punto de enganche que Docker crea
automáticamente y que garantiza no tocar nunca — cualquier regla que se
añada ahí se evalúa *antes* que las reglas `DNAT`/`ACCEPT` que Docker
gestiona, y sobrevive a reinicios del propio Docker (no a un reinicio del
host, para eso hace falta `iptables-persistent`, ver más abajo).

Por eso `toggle-direct-access.sh` gestiona `DOCKER-USER` directamente con
`iptables`, no con comandos `ufw`. **`ufw` no se instala en este clúster
para esto** — ver el aviso en la siguiente sección, es un conflicto de
paquetes real, no una elección de diseño.

## Instalación — `setup-firewall.sh`

Una vez por nodo (idempotente, seguro de re-ejecutar):

```bash
cd /srv/homelab/shared/scripts
bash setup-firewall.sh <nodo>      # ryzen | retaco | pi-obs | pi-sonar | pi-utils
bash setup-firewall.sh all         # los cinco de una vez
```

Qué hace en cada nodo:

1. **Purga `ufw` si está instalado.** Descubierto en vivo en este clúster: los paquetes `ufw` e `iptables-persistent` se pisan entre sí en Ubuntu/Debian — instalar uno desinstala el otro. Como `ufw` no filtra los puertos de Docker de todos modos (ver más arriba), y lo que sí hace falta es que las reglas de `DOCKER-USER` sobrevivan a un reinicio, se prioriza `iptables-persistent` y se retira `ufw` en vez de perseguir una coexistencia que el propio empaquetado no permite. Ver `docs/13-troubleshooting.md`.
2. Instala `iptables-persistent` (paquete estándar Debian/Ubuntu, mismo comando en Raspberry Pi OS y Ubuntu Server).
3. Comprueba que la cadena `DOCKER-USER` existe (la crea Docker al arrancar el daemon).

`pi-dns` no necesita este script — no tiene ningún puerto gestionado por
`toggle-direct-access.sh` (es el origen permitido, no un destino a proteger).

## El script de alternancia — `toggle-direct-access.sh`

```bash
bash toggle-direct-access.sh <nodo|all> <on|off|status>
```

| Modo | Efecto |
|---|---|
| `status` | Muestra el estado actual de cada puerto gestionado, sin cambiar nada |
| `off` | Solo `192.168.1.170` (pi-dns) puede alcanzar esos puertos — el resto de la LAN recibe conexión rechazada |
| `on` | Vuelve al estado actual/por defecto — abierto a toda la LAN |

Ejemplos:

```bash
bash toggle-direct-access.sh ryzen off     # cierra ollama/whisper/vllm/comfyui/open-webui en ryzen
bash toggle-direct-access.sh all status    # ver el estado de los 5 nodos
bash toggle-direct-access.sh all on        # reabre todo
```

### Puertos gestionados por nodo

| Nodo | Puertos | Servicios |
|---|---|---|
| ryzen | 8080, 11434, 9800, 8010, 8188 | open-webui, ollama, whisper-service, vllm, comfyui |
| retaco | 5678, 6333, 5000, 8003, 8004 | n8n-main, qdrant, registry, epub2pdf-service, pdf2chunks-service |
| pi-obs | 3000, 9090 | grafana, prometheus |
| pi-sonar | 9000 | sonarqube |
| pi-utils | 1200, 8001, 5679, 9000, 8222 | rsshub, markitdown-service, n8n-aux, portainer, vaultwarden |

### Qué queda deliberadamente FUERA

`node-exporter` (9100), `cadvisor` (8081), `portainer-agent` (9001) y
`postgres-main` (5432, en retaco) **no** se gestionan aquí — ninguno pasa
por nginx, así que "solo pi-dns" los dejaría inalcanzables para quien de
verdad los necesita entre nodos (Prometheus, en pi-obs, recopilando las
métricas de node-exporter/cadvisor de todos los nodos; Portainer, en
pi-utils, hablando con cada portainer-agent; postgres-exporter y
SonarQube conectando a `postgres-main`). Esas integraciones ya funcionaban
por IP directa antes de este documento y siguen sin verse afectadas — es
tráfico legítimo entre nodos, y no supone saltarse nginx.

## Verificar que funciona

⚠️ **Probar desde OTRO nodo, no desde el mismo que acabas de cerrar.**
Tráfico "de una máquina a su propia IP de LAN" puede tomar un atajo de
enrutado local que no atraviesa la cadena `FORWARD`/`DOCKER-USER` — probado
en vivo: `curl` desde `ryzen` hacia `192.168.1.150:11434` seguía
respondiendo tras `off` (0 paquetes en las reglas, ni ACCEPT ni DROP se
llegaron a evaluar), mientras que el mismo `curl` lanzado desde `retaco`
sí se bloqueó correctamente (3 paquetes contados en la regla DROP). El
bloqueo es real para tráfico genuino entre nodos, que es el caso que
importa — solo el auto-test "a sí mismo" da un falso negativo.

```bash
# Desde OTRO nodo de la LAN (no el que vas a cerrar):
curl -s --max-time 3 http://192.168.1.150:11434/api/tags   # responde, 200

bash toggle-direct-access.sh ryzen off

# Repetido desde ese mismo otro nodo: ahora falla
curl -s --max-time 3 http://192.168.1.150:11434/api/tags   # timeout

# El nombre de host mediante pi-dns sigue funcionando igual que siempre, desde donde sea
curl -sk https://ollama.home.arpa/api/tags -H "X-Api-Key: <tu-key>"   # responde, 200

# Ver los contadores de paquetes de cada regla (para confirmar que de
# verdad se está evaluando el tráfico, no solo que "no responde"):
sudo iptables -L DOCKER-USER -n --line-numbers -v
```

## Notas

- **El tráfico remoto mediante Tailscale (`docs/18-tailscale.md`) no se ve afectado por este mecanismo** —
  llega con NAT aplicado a la IP LAN de `pi-dns` (comportamiento por defecto del
  subnet router), indistinguible del tráfico legítimo que ya generaba
  `nginx`. Con `off` activado en cualquier nodo, un dispositivo Tailscale
  sigue llegando igual — es lo esperado (Tailscale debe sentirse como estar
  en la LAN, pasando por `pi-dns` como de costumbre), no una forma nueva de saltarse la protección.
- Este mecanismo es independiente de `apikey-service` (`docs/06-instalacion-pi1-dns.md`) — son dos
  capas distintas. Con `off` activado, ni siquiera hace falta la API key
  para que el salto por IP deje de ser un problema, porque ese salto ya
  no existe; la API key sigue protegiendo la vía correcta
  (`*.home.arpa`), que es la única que queda disponible.
- Idempotente: ejecutar `off` dos veces seguidas no duplica reglas
  (comprueba con `iptables -C` antes de insertar); igual con `on`.
- Si algún día `docker compose down && up -d` recrea un contenedor y el
  puerto sigue publicado igual, las reglas de `DOCKER-USER` no se ven
  afectadas — no dependen del contenedor en sí, solo del puerto del host.
