# 30 — Instalación: pinchi (192.168.1.175)

Fecha: 2026-08-22

## Rol del nodo

`pinchi` es un nodo **nuevo**, incorporado al clúster con solo el sistema base provisionado — todavía no aloja ningún servicio. PC GMKtec NucBox G10 Pro, x86_64, Ubuntu Server 26.04 LTS.

Este documento cubre únicamente la preparación del sistema base (siguiendo el mismo patrón que `docs/05-instalacion-retaco.md`) y la creación del usuario de administración dedicado. Cuando se decida qué aplicaciones va a alojar, este documento se amplía con esas secciones — no reescribir desde cero.

## Requisitos previos

- Ubuntu Server 26.04 LTS, x86_64
- IP estática: `192.168.1.175`

---

## 1. Preparación del sistema base

Estado inicial: solo el usuario `linus` (creado a mano en la instalación de Ubuntu, con contraseña), SSH activado.

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git htop iotop lsof net-tools unzip jq
```

### 1.1 IP estática (Netplan)

La interfaz de red es `eno1` (no `eth0` como en `retaco`/`pi-*`) — confirmar con `ip -4 addr show` antes de asumir el nombre. El fichero generado por el instalador (`/etc/netplan/00-installer-config.yaml`) ya fija la interfaz por MAC (`match: macaddress:`); se conserva ese bloque al pasar a IP estática:

```yaml
network:
  version: 2
  renderer: networkd
  ethernets:
    eno1:
      match:
        macaddress: 84:47:09:8e:bc:e7
      set-name: eno1
      dhcp4: false
      addresses:
        - 192.168.1.175/24
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses:
          - 192.168.1.170
          - 1.1.1.1
        search:
          - home.arpa
```

```bash
sudo netplan apply
```

La IP fijada coincide con la que ya tenía asignada por DHCP — sin corte de conectividad real, solo deja de depender del servidor DHCP del router.

### 1.2 Usuario de administración dedicado — `u-forge`, no `linus`

Mismo patrón que el resto de nodos (`docs/03-instalacion-base-ubuntu-raspi.md`, sección "1b. Sustituir `ubuntu` por un usuario propio") — `linus` es la cuenta personal usada para el aprovisionamiento inicial, no la que queda para acceso remoto/automatización en curso:

```bash
sudo adduser --disabled-password --gecos '' u-forge
sudo usermod -aG sudo u-forge
```

Clave SSH copiada a mano (sin contraseña en `u-forge` para autenticar por password, `ssh-copy-id` no aplica — la clave se deposita directamente en `~u-forge/.ssh/authorized_keys` vía `sudo` desde `linus`):

```bash
mkdir -p /home/u-forge/.ssh
echo "<clave pública>" > /home/u-forge/.ssh/authorized_keys
chmod 700 /home/u-forge/.ssh
chmod 600 /home/u-forge/.ssh/authorized_keys
chown -R u-forge:u-forge /home/u-forge/.ssh
```

Sudo sin contraseña (`/etc/sudoers.d/`, nunca editar `/etc/sudoers` a mano):

```bash
echo "u-forge ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/u-forge > /dev/null
sudo chmod 0440 /etc/sudoers.d/u-forge
sudo visudo -c
```

Verificado: `ssh u-forge@192.168.1.175 sudo whoami` → `root`, sin pedir contraseña.

#### ⚠️ Deshabilitar login por contraseña — el drop-in de cloud-init manda, no el `sshd_config` principal

Igual que en el resto de nodos, conviene deshabilitar `PasswordAuthentication` en SSH una vez `u-forge` funciona por clave. **Gotcha real encontrado en este nodo** (no visto en las Raspberry Pi, instaladas de otra forma): existe `/etc/ssh/sshd_config.d/50-cloud-init.conf` con `PasswordAuthentication yes` explícito, incluido vía `Include /etc/ssh/sshd_config.d/*.conf` **antes** de la directiva equivalente del `sshd_config` principal — OpenSSH usa el primer valor que encuentra para cada directiva, así que un `sed` normal sobre `sshd_config` (el patrón que documenta `docs/03`) no tiene ningún efecto aquí, se sigue permitiendo login por contraseña aunque el fichero principal diga lo contrario.

**Solución**: un drop-in propio que se procese *antes* alfabéticamente que `50-cloud-init.conf`:

```bash
echo 'PasswordAuthentication no' | sudo tee /etc/ssh/sshd_config.d/00-homelab.conf > /dev/null
sudo sshd -t   # validar sintaxis antes de reiniciar
sudo systemctl restart ssh
```

Verificado en vivo: tras el reinicio, `u-forge` sigue entrando por clave sin problema; un intento de login por contraseña (`linus` incluido, que no tiene ninguna clave instalada) se rechaza con `Permission denied (publickey)`.

**`linus` no se ha bloqueado ni eliminado** — a diferencia del patrón `passwd -l ubuntu` de `docs/03` (pensado para la cuenta genérica por defecto de las imágenes cloud), `linus` es la cuenta personal del operador, replicada como bootstrap en cada máquina nueva (mismo caso ya visto en el NAS UGREEN, `docs/21`). Con `PasswordAuthentication no` ya no es utilizable para SSH salvo que se le instale una clave propia — decisión de si bloquearla del todo dejada abierta, no forzada aquí.

## 2. Docker Engine

```bash
sudo bash /srv/homelab/shared/scripts/install-docker-ubuntu.sh
```

Añade automáticamente al usuario que ejecuta el script (`u-forge`) al grupo `docker`. Verificado: `docker ps`/`docker compose version` funcionan sin `sudo` en una sesión SSH nueva.

### 2.1 Preparado para Docker Swarm — sin inicializar todavía

Docker Swarm viene integrado en el propio motor (`docker-ce`), no hace falta instalar nada aparte — confirmado con `docker info --format '{{.Swarm.LocalNodeState}}'` → `inactive` (soporta Swarm, no está unido a ninguno). **Deliberadamente no se ejecuta `docker swarm init`/`join` en este pase** — la migración a Swarm (mejora 33, `docs/22-mejoras-futuras.md`) sigue siendo una decisión de arquitectura pendiente para todo el clúster, no algo que se ejecute nodo a nodo de forma aislada.

## 3. Preparar directorios de datos

```bash
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pinchi
```

Crea solo `/srv/homelab/pinchi/` (vacío) y `/srv/homelab/backups/pinchi/` — sin subcarpetas de datos todavía, porque no hay servicios decididos. Cuando se decida qué corre aquí, añadir el caso completo en `prepare-host.sh` (mismo patrón que `retaco`/`pi-utils`: `create_dir` por cada volumen + `chown` específico si el UID del contenedor no coincide con el del usuario que despliega).

También se sincronizó el árbol `shared/` completo (`scripts/`, `env/`, `dns/`) a `/srv/homelab/shared/` en este nodo — mismo convenio que el resto (`docs/19-wake-on-lan.md` documenta el mismo patrón para `wake-mole.sh`).

## 4. DNS

`pinchi.home.arpa` → `192.168.1.175`, añadido a `shared/dns/dns-records.md` y `shared/scripts/load-dns-records.sh`, aplicado en Pi-hole. Resuelve correctamente tanto desde la LAN como desde el propio nodo (`getent hosts pinchi.home.arpa`).

## Estado final de este pase

| Elemento | Estado |
|---|---|
| IP estática | ✅ `192.168.1.175/24`, vía Netplan |
| Paquetes base | ✅ |
| Usuario `u-forge` | ✅ sudo sin contraseña, clave SSH, login por contraseña deshabilitado |
| Docker Engine + Compose | ✅ instalado, `u-forge` en el grupo `docker` |
| Docker Swarm | ⏳ soportado por el motor, sin inicializar/unir (pendiente mejora 33) |
| DNS (`pinchi.home.arpa`) | ✅ |
| Servicios de aplicación | ❌ ninguno todavía — pendiente de decidir qué aloja este nodo |
| `pinchi/docker-compose.yml` | ❌ no existe todavía, ver `pinchi/README.md` |

## Pendiente

- Decidir qué servicios aloja `pinchi` (el nombre de usuario `u-forge` sugiere Forgejo, mejora 7 de `docs/22-mejoras-futuras.md`, pero no está confirmado formalmente).
- Actualizar `shared/scripts/prepare-host.sh` con el caso completo de este nodo en cuanto se decida.
- Crear `pinchi/docker-compose.yml`/`.env.example` siguiendo el mismo patrón que el resto de nodos.
- Firewall (`shared/scripts/setup-firewall.sh`, `docs/17-firewall-acceso-directo.md`) — no aplicado todavía en este pase, igual que no se aplica hasta que un nodo empieza a exponer servicios HTTP reales.
- Cuenta SSH dedicada `capataz_automation` (si Capataz llega a gestionar este nodo también, `docs/28-capataz-consola-automatizacion.md`).
- El resto de scripts de `shared/scripts/` (`check-health.sh`, `update-stack.sh`, `toggle-direct-access.sh`, `setup-firewall.sh`...) todavía no conocen `pinchi` — normal mientras no haya `docker-compose.yml` ni servicios HTTP que comprobar, pero hay que añadirlo a sus mapas de nodos (`NODE_SSH` y similares) en cuanto empiece a alojar algo.
