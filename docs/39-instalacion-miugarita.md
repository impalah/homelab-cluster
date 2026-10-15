# 39 — Instalación: miugarita (192.168.10.9)

Fecha: 2026-09-29

## Rol del nodo

`miugarita` es el **sexto nodo del Swarm**, incorporado directamente como manager/worker del clúster ya existente — a diferencia de `pinchi` (`docs/30-instalacion-pinchi.md`), que se dio de alta primero con solo el sistema base y se unió al Swarm mucho después, este nodo se aprovisiona y se une en el mismo pase. PC x86_64 (AMD Ryzen 5 3500U, 8 hilos, 12 GB RAM, NVMe 468 GB), Ubuntu Server 26.04 LTS ("Resolute Raccoon").

Todavía sin rol de aplicación decidido — como `pinchi` en su momento, este documento se amplía cuando se decida qué aloja.

## Requisitos previos

- Ubuntu Server 26.04 LTS, x86_64.
- **Sin IP estática** — la IP la asigna el DHCP del router Cudy R700 mediante una reserva por MAC (`shared/dns/router-dhcp-notes.md`), igual que el resto de nodos del clúster desde la migración de red del 2026-09-28. Netplan se deja en modo DHCP puro; no se toca la configuración de red del nodo. La reserva fija la IP en `192.168.10.9` de forma predecible sin necesidad de tocar nada en el propio nodo.

⚠️ **Ningún nodo del clúster tiene IP fija configurada localmente** (Netplan/NetworkManager) — la predictibilidad de la IP viene de la reserva DHCP por MAC en el router, no de un `addresses:` estático en el nodo. `docs/30-instalacion-pinchi.md` describía en su momento una IP fija por Netplan porque así se hizo entonces (antes de la migración de red); eso ya no es el procedimiento vigente para ningún nodo, incluido `pinchi` — ver la nota correspondiente en ese documento.

---

## 1. Preparación del sistema base

Estado inicial: solo el usuario `linus` (personal, contraseña), SSH activado, sin ningún paquete adicional.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git htop iotop lsof net-tools unzip jq
```

Interfaz de red: `eno1` (confirmar con `ip -4 addr show` antes de asumirlo). IP asignada por DHCP: `192.168.10.9/24`, gateway `192.168.10.1` — no se toca `/etc/netplan/`, sigue en `dhcp4: true` tal cual la deja el instalador.

### 1.1 Usuario de administración — `admin`, no un usuario dedicado por nodo

**Primer nodo del clúster dado de alta directamente con el modelo de `docs/38-acceso-ssh-nodos.md`** (usuario único `admin` en todos los nodos, clave `ed25519` distinta por nodo almacenada en Infisical) — a diferencia del resto de nodos (`u-data`, `u-dns`, `u-obs`, `u-sonar`, `u-utils`, `u-forge`), que siguen con el patrón antiguo de usuario arbitrario por nodo hasta que se ejecute la migración pendiente (mejora 52). Seguido literalmente el procedimiento de `docs/38` sección 3.4/3.1/4/5.6, sin desviaciones:

```bash
# En miugarita, con acceso inicial linus/contraseña:
sudo adduser --disabled-password --gecos '' admin
sudo usermod -aG sudo admin
```

Par de claves generado en el puesto del operador (nunca en el nodo destino), pública copiada a `/home/admin/.ssh/authorized_keys`, `sudo` sin contraseña en `/etc/sudoers.d/admin` — pasos idénticos a `docs/38` 3.4.2 a 3.4.4, no repetidos aquí.

Verificado: `ssh admin@192.168.10.9 sudo whoami` → `root`, sin pedir contraseña.

#### ⚠️ Mismo gotcha de cloud-init que `pinchi` (`docs/30`)

`/etc/ssh/sshd_config.d/50-cloud-init.conf` trae `PasswordAuthentication yes` explícito, procesado antes que el `sshd_config` principal — un `sed` sobre el fichero principal no tiene efecto. Solución: drop-in propio con prioridad alfabética anterior, exactamente como fija `docs/38` sección 4:

```bash
sudo bash -c 'printf "PasswordAuthentication no\nPermitRootLogin no\n" > /etc/ssh/sshd_config.d/00-homelab.conf'
sudo systemctl restart ssh
```

Verificado en vivo: `admin` sigue entrando por clave tras el reinicio; un intento con `-o PreferredAuthentications=password` se rechaza con `Permission denied (publickey)`.

**`linus` no se ha bloqueado ni eliminado** — mismo criterio que `pinchi` (`docs/30`, sección 1.2): es la cuenta personal del operador, no la cuenta administrativa del clúster. Con `PasswordAuthentication no` ya no sirve para SSH salvo que se le instale una clave propia.

### 1.2 Clave SSH almacenada — Infisical (`ssh-access`) + Vaultwarden

Siguiendo `docs/38` sección 5.6 (alta de un nodo nuevo) al pie de la letra:

1. Proyecto Infisical **`ssh-access`** creado (no existía todavía en el clúster — primer uso real de este mecanismo, hasta ahora solo estaba descrito en `docs/38` como pendiente).
2. Secretos en `/ssh-access/miugarita/` (entorno `prod`): `PRIVATE_KEY`, `PUBLIC_KEY`, `FINGERPRINT` (`SHA256:AWwC5XS3Z10s29Qd52Iwfnu0xqhgIwW4RgB7deZb52U`).
3. Copia cifrada de respaldo en Vaultwarden (`vaultwarden.404labo.net`, carpeta `Homelab Cluster`, elemento "SSH admin@miugarita (docs/38)", tipo nativo "Clave SSH") — respaldo de emergencia si Infisical/`retaco` no es alcanzable, `docs/38` sección 5.3.
4. Copia local de la clave privada borrada del puesto del operador tras subirla — solo vive en Infisical y en el respaldo de Vaultwarden.

## 2. Docker Engine

```bash
sudo bash /srv/homelab/shared/scripts/install-docker-ubuntu.sh
```

Mismo script que el resto de nodos (`docs/30` sección 2). Ubuntu 26.04 ("resolute") ya tiene paquetes propios en el repositorio oficial de Docker (`docker-ce` 29.8.1) — confirmado en vivo, sin necesidad de forzar una suite anterior. Añade automáticamente `admin` al grupo `docker`.

## 3. Cortafuegos de control de Swarm

`docker-swarm/init/setup-swarm-firewall.sh` restringe el tráfico de control (TCP 2377, TCP+UDP 7946, UDP 4789) a solo los nodos del clúster. **Paso que no puede saltarse antes de unir el nodo al Swarm** — sin él, `docker swarm join` se queda colgado indefinidamente contra el DROP por defecto del resto de nodos (encontrado en vivo al dar de alta este nodo: el `join` no devolvía ni error ni éxito, simplemente no terminaba nunca, hasta añadir la IP de `miugarita` al script y reaplicarlo en los 6 nodos).

```bash
# Prerrequisito: iptables-persistent
bash shared/scripts/setup-firewall.sh miugarita

# Reglas de control de Swarm en los 6 nodos (incluye la propia miugarita como origen permitido)
bash docker-swarm/init/setup-swarm-firewall.sh apply
```

## 4. Unión al Swarm

```bash
# Desde un manager existente (retaco):
docker swarm join-token worker -q

# En miugarita:
sudo docker swarm join --token <token> 192.168.10.7:2377
```

Unida como **worker** (mismo criterio que `pi-obs`/`pi-sonar`/`pi-utils`/`pinchi` — `retaco` es el único manager real tras el incidente de recuperación de Raft documentado en `docs/31-docker-swarm.md`). `mode: global` de `traefik`/`portainer-agent`/`common_node-exporter`/`common_cadvisor` la detectó automáticamente y desplegó una réplica aquí sin ninguna acción adicional.

## 5. Preparar directorios de datos

```bash
sudo bash /srv/homelab/shared/scripts/prepare-host.sh miugarita
```

Mismo estado que `pinchi` en su momento: solo `/srv/homelab/miugarita/` vacío, sin subcarpetas de datos — no hay servicios de aplicación decididos todavía. Árbol `shared/` completo sincronizado a `/srv/homelab/shared/` en este nodo, mismo convenio que el resto.

## Estado final de este pase

| Elemento | Estado |
|---|---|
| IP | ✅ `192.168.10.9/24`, DHCP + reserva por MAC en el router (sin IP fija en el nodo) |
| Paquetes base | ✅ |
| Usuario `admin` (modelo `docs/38`) | ✅ sudo sin contraseña, clave SSH propia, login por contraseña deshabilitado |
| Clave SSH en Infisical + Vaultwarden | ✅ `/ssh-access/miugarita/` (prod) + respaldo cifrado |
| Docker Engine + Compose | ✅ instalado, `admin` en el grupo `docker` |
| Cortafuegos de control de Swarm | ✅ aplicado en los 6 nodos |
| Docker Swarm | ✅ unida como worker |
| Servicios `mode: global` (traefik, portainer-agent, node-exporter, cadvisor) | ✅ desplegados automáticamente |
| DNS (`miugarita.404labo.net`) | ⏳ pendiente, ver más abajo |
| Servicios de aplicación propios | ❌ ninguno todavía — pendiente de decidir qué aloja este nodo |
| `miugarita/docker-compose.yml` | ❌ no existe todavía — no hace falta mientras no aloje nada fuera de Swarm |

## Pendiente

- Añadir `miugarita.404labo.net` → `192.168.10.9` a `shared/dns/dns-records.md` y aplicarlo con `shared/scripts/load-dns-records.sh`.
- Decidir qué servicios aloja `miugarita`.
- Añadir el nodo a los mapas de `shared/scripts/check-health.sh`, `toggle-direct-access.sh` y equivalentes en cuanto empiece a exponer servicios HTTP.
- Actualizar `shared/scripts/prepare-host.sh` con el caso completo de este nodo en cuanto se decida qué aloja.
- ~~Migrar el resto de nodos al modelo de usuario `admin` + Infisical de `docs/38`~~ — hecho el 2026-10-08 (mejora 52): los 8 nodos están alineados con el procedimiento vigente.
