# 38 — Acceso SSH a los nodos del clúster: procedimiento estándar

Este documento fija el procedimiento único para dar acceso administrativo por SSH a cualquier nodo del clúster — instalación/configuración en Ubuntu Server, Ubuntu Desktop y Alpine Linux (incluido `ryzen`), y el sistema de almacenamiento y obtención de claves que usan tanto una sesión de terminal a pelo como Ansible. No sustituye a las guías de instalación por nodo (`docs/03`, `docs/05` a `docs/10`, `docs/30`) — las consolida en un único procedimiento reutilizable, para no repetir esta parte en cada guía nueva ni improvisarla distinto cada vez.

---

## 1. Objetivo y alcance

Todo nodo del clúster — **incluido `ryzen`, que hoy se administra en local por ser el propio puesto de trabajo** — debe tener:

1. **Un único usuario administrativo, `admin`, con el mismo nombre en los 7 nodos** — decisión explícita (2026-09-15): frente al modelo anterior (un usuario distinto y arbitrario por nodo, que obligaba a recordar o consultar una tabla), se prioriza la predictibilidad — conectar a cualquier nodo es siempre `ssh admin@<ip>`, sin tener que saber de antemano qué usuario tiene ese nodo en concreto.
2. Ese usuario en los grupos `sudo` (`wheel` en Alpine) y `docker`.
3. Acceso únicamente por **clave SSH**, nunca por contraseña.
4. `PasswordAuthentication no` y `PermitRootLogin no` en el `sshd` real (no solo en el fichero que parezca el correcto — ver el aviso de `cloud-init` más abajo).

**El nombre de usuario compartido NO reduce el aislamiento real entre nodos** — ese aislamiento sigue viviendo en la clave SSH, que es **distinta por nodo** (sección 5). Que la cuenta se llame igual en todos lados es solo una cuestión de nombre; lo que de verdad separa un nodo de otro (y lo que hay que revocar si un nodo se ve comprometido) es su propia clave privada, nunca compartida entre nodos.

Esto permite controlar cualquier nodo indistintamente por SSH a pelo, por Ansible (mejora 6, backlog) o por automatizaciones de Capataz (`docs/28-capataz-consola-automatizacion.md`), con el mismo modelo de acceso en los tres casos.

`ryzen` se incluye a propósito aunque hoy el operador ya esté físicamente sentado delante — la razón es que Ansible/Capataz necesitan poder llegar a él igual que a cualquier otro nodo (mejora 48, Cockpit+libvirt con arranque/parada por Ansible) sin depender de que alguien esté logueado en el escritorio.

---

## 2. Estado actual (auditado 2026-09-15, con honestidad)

Lo que ya existe y funciona, documentado en `docs/01-topologia.md` ("Acceso SSH a los nodos"):

| Nodo | Usuario actual | Grupos |
|---|---|---|
| `retaco` | `u-data` | `sudo`, `docker` |
| `pi-dns` | `u-dns` | `sudo`, `docker` |
| `pi-obs` | `u-obs` | `sudo`, `docker` |
| `pi-sonar` | `u-sonar` | `sudo`, `docker` |
| `pi-utils` | `u-utils` | `sudo`, `docker` |
| `pinchi` | `u-forge` | `sudo`, `docker` |

Dos cosas que el estado actual **no** cumple frente al modelo objetivo de este documento (sección 1):

1. **Usuarios distintos y arbitrarios por nodo** — ninguno se puede deducir del nombre del nodo (`u-data` para `retaco`, `u-forge` para `pinchi`...), hay que consultar esta tabla cada vez. Es justo lo que este documento corrige (usuario único `admin`).
2. **Una única clave privada compartida** (verificado en el propio `~/.ssh/` de `ryzen`: solo existe `id_ed25519`, autorizada en los 6 nodos) — la misma clave abre los 6 usuarios distintos. Si esa clave se filtrara, comprometería los 6 nodos a la vez, no solo uno. El modelo objetivo (sección 5) usa una clave `ed25519` distinta por nodo.

Ninguna de las dos es bloqueante para seguir operando mientras se aplica la migración — es exactamente el trabajo pendiente descrito en la **mejora 52** (`docs/22-mejoras-futuras.md`).

`ryzen` no tiene hoy ningún usuario de administración dedicado (se opera como `linus`, el usuario personal del puesto) ni `sshd` habilitado para acceso entrante — lo que este documento resuelve, punto 3.2.

---

## 3. Instalación y configuración por sistema operativo

### 3.1 Ubuntu Server (`retaco`, `pinchi`, `pi-dns`/`pi-obs`/`pi-sonar`/`pi-utils`)

Paquetes necesarios — normalmente ya presentes en una instalación estándar de Ubuntu Server, comprobar antes de asumir:

```bash
sudo apt-get update -qq
sudo apt-get install -y openssh-server sudo
sudo systemctl enable --now ssh
```

El resto de pasos (usuario `admin`, clave, `sudoers`, endurecimiento de `sshd`) es común a los tres sistemas operativos — ver el punto 4.

⚠️ **Gotcha real, ya encontrado en `pinchi` (`docs/30-instalacion-pinchi.md`), no visto en las Raspberry Pi (instaladas de otra forma)**: un nodo provisionado vía *cloud-init* trae `/etc/ssh/sshd_config.d/50-cloud-init.conf` con `PasswordAuthentication yes` explícito — como `sshd` procesa los `Include` de `sshd_config.d/*.conf` **antes** que la directiva equivalente del `sshd_config` principal y se queda con el primer valor visto por directiva, un `sed` normal sobre `sshd_config` no tiene ningún efecto ahí, el login por contraseña sigue activo aunque el fichero principal diga lo contrario. **Antes de aplicar el endurecimiento del punto 4 en cualquier nodo nuevo, comprobar `ls /etc/ssh/sshd_config.d/` — si hay algo con prioridad alfabética anterior fijando `PasswordAuthentication yes`, hace falta un drop-in propio que se procese antes (ver sección 4), no basta con editar el fichero principal.**

### 3.2 Ubuntu Desktop (`ryzen`)

A diferencia de Ubuntu Server, una instalación de Desktop **no trae el servidor SSH instalado por defecto** (solo el cliente) — hay que instalarlo explícitamente:

```bash
sudo apt-get update -qq
sudo apt-get install -y openssh-server
sudo systemctl enable --now ssh
```

`sudo` ya viene instalado en Desktop (el primer usuario creado en el instalador ya es sudoer) — pero eso no sustituye la cuenta `admin` que pide este procedimiento; se crea aparte, igual que en el resto de nodos (punto 3.4). El usuario personal del puesto (`linus`) sigue existiendo para uso de escritorio normal, sin tocarlo.

`ryzen` usa NetworkManager en vez de Netplan para la red — irrelevante para este documento (no toca la configuración de red, solo SSH), pero es la diferencia real frente a Ubuntu Server que sí importaría si algún día se automatiza algo de red aquí.

⚠️ `ryzen` es el único nodo que se apaga habitualmente (Wake-on-LAN, `docs/19-wake-on-lan.md`) — el servidor SSH no sirve de nada si el equipo está dormido; cualquier automatización que necesite entrar por SSH debe despertarlo primero con `shared/scripts/wake-mole.sh` y esperar a que responda, exactamente igual que ya hace cualquier operación manual hoy.

### 3.3 Alpine Linux (futuro — mejora 51, todavía no desplegado en ningún nodo)

Alpine no trae `sudo` por defecto (solo el `su` de BusyBox) y `openssh` puede no estar en el perfil mínimo elegido en `setup-alpine` — instalar explícitamente:

```sh
apk update
apk add openssh sudo bash
rc-update add sshd default
rc-service sshd start
```

`bash` es un añadido deliberado, no opcional: todos los scripts de `shared/scripts/` de este repo usan `#!/usr/bin/env bash` y construcciones que no son POSIX puro (`declare -A`, `[[ ]]`...) — sin `bash` instalado, ninguno de ellos funciona en un nodo Alpine, solo lo estrictamente POSIX. Ver mejora 51 (`docs/22-mejoras-futuras.md`) para el resto de paquetes que hacen falta más allá de SSH (Docker, `iptables`...).

Alpine usa **OpenRC**, no `systemd` — `rc-update add <servicio> default` es el equivalente a `systemctl enable`, `rc-service <servicio> start/restart` al equivalente de `systemctl start/restart`. Se usa en el resto de esta guía sin repetir la equivalencia cada vez.

### 3.4 Procedimiento común, una vez instalados los paquetes (los tres sistemas operativos)

El usuario es siempre literalmente `admin` — no hay ningún nombre que sustituir por nodo, solo la IP cambia. Antes de crear la cuenta, comprobar que no exista ya con otro propósito (`id admin` — poco probable, pero barato de comprobar):

**1. Crear el usuario, sin contraseña utilizable:**

Ubuntu (Server o Desktop):
```bash
sudo adduser --disabled-password --gecos '' admin
sudo usermod -aG sudo,docker admin
```

Alpine:
```sh
adduser -D admin
addgroup admin wheel     # wheel es el grupo sudo-equivalente en Alpine
addgroup admin docker
echo '%wheel ALL=(ALL) ALL' | tee /etc/sudoers.d/wheel   # solo la primera vez, si no existe ya
```

**2. Generar el par de claves EN EL PUESTO DEL OPERADOR** (nunca en el nodo destino — la privada no debe generarse ni quedarse nunca en la máquina a la que da acceso). El nombre de fichero local lleva el **nodo**, no el usuario (el usuario ya es siempre `admin`; lo que distingue una clave de otra es a qué nodo pertenece):

```bash
ssh-keygen -t ed25519 -C "admin@<nodo>.404labo.net" -f ~/claves-temporales/<nodo>-id_ed25519 -N ""
```

(La ausencia de passphrase aquí es intencional solo para este paso de generación local — la clave privada no vive en disco después de este procedimiento, ver sección 5; si se prefiere mantenerla también como copia local protegida, usar una passphrase real y un `ssh-agent`.)

**3. Copiar solo la clave PÚBLICA al nodo** (acceso inicial por contraseña/consola física, el único momento en que se usa):

```bash
mkdir -p /home/admin/.ssh
echo "<contenido de <nodo>-id_ed25519.pub>" > /home/admin/.ssh/authorized_keys
chmod 700 /home/admin/.ssh
chmod 600 /home/admin/.ssh/authorized_keys
chown -R admin:admin /home/admin/.ssh
```

**4. `sudo` sin contraseña, en su propio fichero — nunca editando `/etc/sudoers` a mano:**

```bash
echo "admin ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/admin > /dev/null
sudo chmod 0440 /etc/sudoers.d/admin
sudo visudo -c   # valida sintaxis antes de cerrar la sesión — un error aquí puede dejar sudo inutilizable
```

**5. Verificar el acceso por clave antes de tocar `sshd_config`:**

```bash
ssh admin@<ip> sudo whoami   # debe responder "root" sin pedir contraseña
```

**Sobre un nodo ya existente con un usuario dedicado antiguo** (`u-data`, `u-dns`...) — no renombrar la cuenta vieja in situ. Crear `admin` como cuenta nueva siguiendo los pasos de arriba, verificar que funciona de punta a punta (incluido el endurecimiento de la sección 4), y **solo entonces** retirar la cuenta antigua (`sudo deluser --remove-home <usuario-antiguo>` en Ubuntu, `deluser <usuario-antiguo>` en Alpine, más su fichero en `/etc/sudoers.d/`). Nunca al revés — quitar la cuenta vieja antes de confirmar que la nueva funciona puede dejar el nodo sin ningún acceso administrativo.

---

## 4. Endurecimiento de `sshd` (los tres sistemas operativos)

Solo después de verificar el punto 3.4.5 — deshabilitar contraseña antes de tener clave funcionando deja el nodo inaccesible.

```bash
sudo mkdir -p /etc/ssh/sshd_config.d
printf 'PasswordAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/00-homelab.conf > /dev/null
sudo systemctl restart ssh    # Alpine: rc-service sshd restart
```

Se usa siempre un drop-in propio (`00-homelab.conf`, ordena antes que cualquier otro por convención de nombre), nunca un `sed` sobre el `sshd_config` principal — evita repetir el problema real ya encontrado en `pinchi` (punto 3.1) si algún día otro mecanismo de aprovisionamiento (cloud-init, `setup-alpine`, lo que sea) añade su propio drop-in con prioridad mayor.

Verificación final:

```bash
ssh admin@<ip> sudo whoami                       # sigue funcionando por clave
ssh -o PreferredAuthentications=password admin@<ip>   # debe rechazar: "Permission denied (publickey)"
```

---

## 5. Sistema de almacenamiento seguro y obtención de claves

### 5.1 Por qué una clave distinta por nodo, aunque el usuario sea el mismo

El estado actual (sección 2) usa una sola clave para los 6 nodos — cómodo, pero un único punto de fallo: comprometer esa clave (portátil robado, backup mal protegido, fuga de un script) da acceso a todo el clúster de golpe. El modelo de este documento es **una clave `ed25519` distinta por nodo**, generada en el paso 3.4.2 — así, revocar el acceso a un nodo (borrar su `authorized_keys` + su secreto en el almacén) no afecta al resto, y una fuga puntual queda acotada a un solo nodo. Que el usuario `admin` se llame igual en todos lados (sección 1) no cambia esto — la clave, no el nombre de usuario, es la frontera real de seguridad entre nodos.

### 5.2 Dónde viven las claves privadas: Infisical

El clúster ya tiene un gestor de secretos propio, `infisical.404labo.net` (`docs/26-infisical-secretos.md`), usado hoy para credenciales de servicios — se reutiliza el mismo mecanismo para las claves SSH de administración, en vez de inventar un almacén nuevo:

- Proyecto Infisical dedicado: **`ssh-access`** (nuevo, separado de los proyectos por servicio como `forgejo` — esto es acceso a infraestructura, no un secreto de aplicación).
- Una carpeta por nodo, entorno `prod`: `/ssh-access/<nodo>/`, con el secreto `PRIVATE_KEY` (el contenido completo de la clave privada, multilínea — Infisical ya almacena secretos así, mismo tipo de dato que un `.pem`). El usuario al que pertenece (`admin`, siempre) no hace falta guardarlo aparte — es constante.
- Metadatos opcionales en la misma carpeta, útiles para auditoría sin tener que descifrar nada: `PUBLIC_KEY`, `FINGERPRINT` (`ssh-keygen -lf`).

La clave privada **no vive en ningún fichero de este repositorio ni en ningún `.env`** — coherente con la norma ya existente del proyecto ("Secrets are always `CHANGE_ME` placeholders...", `CLAUDE.md`).

### 5.3 Respaldo fuera de banda: Vaultwarden

Infisical vive en `retaco` (`docker-swarm/stacks/infisical/`) — si `retaco` está caído, Infisical no responde, y con él, ningún acceso SSH quedaría disponible por esta vía (problema de huevo y gallina para poder entrar precisamente a arreglar `retaco`). Mitigación: una copia de cada clave privada, cifrada, en **Vaultwarden** (`vaultwarden.404labo.net`, ya vive en `pinchi` — nodo distinto, ver `README.md`), como acceso de emergencia manual (humano, no automatizado) cuando Infisical no es alcanzable. Es el mismo patrón ya usado en este clúster para otras credenciales de "romper el cristal" (p. ej. las credenciales del registry Docker, citadas en `CLAUDE.md`).

### 5.4 Procedimiento de conexión — terminal a pelo

Nunca escribir la clave privada en disco en texto plano de forma persistente — se carga directamente en `ssh-agent`, en memoria, y se descarta al cerrar la sesión:

```bash
eval "$(ssh-agent -s)"
infisical secrets get PRIVATE_KEY --plain --projectId=<id-proyecto-ssh-access> --env=prod --path=/ssh-access/<nodo>/ | ssh-add -
ssh admin@<ip>
```

Con la clave ya en el agente, `ssh` la usa automáticamente (sin `-i`) mientras dure la sesión del agente — conectar a varios nodos en la misma sesión de trabajo solo necesita repetir el `ssh-add` una vez por nodo, no en cada `ssh`. Como el usuario es siempre `admin`, lo único que cambia entre nodos al conectar es la IP.

Este flujo requiere estar autenticado contra Infisical (`infisical login`, sesión personal del operador — no una identidad de máquina, es un humano tecleando el comando). Empaquetar esto en un script (`shared/scripts/ssh-node.sh <nodo>` propuesto, no implementado todavía — ver mejora 52) es el paso natural siguiente para que sea un solo comando en vez de tres — ese script puede resolver `<nodo>` → IP internamente (mismo mapa que ya usa `shared/scripts/toggle-direct-access.sh`), de forma que ni siquiera haga falta recordar la IP, solo el nombre corto del nodo.

### 5.5 Aplicable a Ansible, sin cambios en el mecanismo

Ansible usa por defecto el mismo `ssh-agent` del sistema que cualquier `ssh` de terminal — no hace falta `ansible_ssh_private_key_file` apuntando a un fichero en disco. Con el usuario unificado, el inventario se simplifica: **`ansible_user=admin` puede fijarse una sola vez a nivel de grupo**, en vez de repetirlo por host:

```ini
# inventory.ini (ejemplo, mejora 6 todavía no iniciada)
[cluster:vars]
ansible_user=admin

[cluster]
retaco    ansible_host=192.168.1.174
pi-dns    ansible_host=192.168.1.170
pi-obs    ansible_host=192.168.1.171
pi-sonar  ansible_host=192.168.1.172
pi-utils  ansible_host=192.168.1.173
pinchi    ansible_host=192.168.1.175
ryzen     ansible_host=192.168.1.150
```

Antes de `ansible-playbook`, cargar en el agente las claves de todos los nodos objetivo (mismo `ssh-add` del punto 5.4, una vez por nodo — o todas de golpe con un bucle sobre las carpetas de `/ssh-access/` en Infisical). Un `ansible-playbook -i inventory.ini site.yml --limit pi-obs` solo necesita tener cargada la clave de `pi-obs` en ese momento, no las siete.

### 5.6 Alta de un nodo nuevo (bootstrap) — resumen del flujo completo

1. Generar el par de claves en el puesto del operador (3.4.2).
2. Copiar solo la pública al nodo, por el acceso inicial (contraseña o consola física) — 3.4.3.
3. Verificar acceso por clave (3.4.5) y endurecer `sshd` (sección 4).
4. Subir la clave **privada** a Infisical (`infisical secrets set PRIVATE_KEY --path=/ssh-access/<nodo>/ ...`, desde un fichero local, `--file` o `--plain` con el contenido).
5. Guardar una copia cifrada en Vaultwarden (5.3).
6. Borrar la copia local de la clave privada del puesto del operador (`shred` o equivalente) — a partir de aquí solo vive en Infisical y en el respaldo de Vaultwarden.

### 5.7 El caso de Capataz — mecanismo propio, ya existente, no este

Capataz (`docs/28-capataz-consola-automatizacion.md`) ya tiene su propio flujo para lanzar automatizaciones (Ansible incluido) contra los nodos: un recurso `runner_ssh_private_key` cifrado en Postgres (catálogo v2, "conectores y recursos", ver el propio documento), independiente de Infisical. **Debe seguir el mismo principio de separación que el resto de este documento**: la clave que usa `capataz-runner` tiene que ser su propia clave dedicada, distinta de la de cualquier operador humano y distinta por nodo — nunca la clave personal de un operador reutilizada ahí. Este documento no sustituye ese mecanismo, lo complementa: Infisical es para acceso humano/Ansible manual, el recurso de Capataz es para lo que Capataz dispara por sí solo. Si `capataz-runner` conecta como `admin` (la cuenta unificada) o como una cuenta de servicio aparte (p. ej. `capataz`) es una decisión pendiente, no resuelta en este documento — usar una cuenta de servicio propia es más trazable en logs (`last`/`journalctl` muestran quién hizo qué) a cambio de un usuario más que gestionar.

### 5.8 Rotación y revocación

Rotar una clave: generar un par nuevo, añadir la pública nueva a `authorized_keys` del nodo (sin borrar la vieja todavía), verificar acceso con la nueva, **entonces** borrar la entrada vieja de `authorized_keys` y sobrescribir el secreto en Infisical (`infisical secrets set` sobre el mismo `PRIVATE_KEY` ya rota la versión). Revocar (nodo comprometido, baja de un colaborador con acceso): borrar la entrada de `authorized_keys` del nodo afectado inmediatamente — eso corta el acceso ya, borrar el secreto de Infisical/Vaultwarden es limpieza, no la acción que realmente protege.

---

## 6. Checklist de verificación (nodo nuevo o reinstalado)

- [ ] Usuario `admin` creado, sin contraseña utilizable, en grupos `sudo`/`wheel` + `docker`.
- [ ] Clave `ed25519` propia de este nodo, generada fuera del propio nodo.
- [ ] `ssh admin@<ip> sudo whoami` → `root`, sin pedir contraseña.
- [ ] `ssh -o PreferredAuthentications=password admin@<ip>` → rechazado.
- [ ] Comprobado `/etc/ssh/sshd_config.d/` por si algo con prioridad mayor reabre `PasswordAuthentication` (gotcha de cloud-init, sección 3.1).
- [ ] Clave privada subida a Infisical (`/ssh-access/<nodo>/`), copia cifrada en Vaultwarden, copia local borrada.
- [ ] Si el nodo tenía un usuario dedicado antiguo, retirado **solo después** de verificar `admin` de punta a punta (sección 3.4).
- [ ] Fila actualizada en la tabla de `docs/01-topologia.md` ("Acceso SSH a los nodos") y, si aplica, en el mapa `NODE_SSH` de `shared/scripts/toggle-direct-access.sh` y equivalentes.

---

## 7. Trabajo pendiente

Este documento fija el procedimiento a seguir de aquí en adelante — no implica que ya esté aplicado en el clúster real. Ver **mejora 52** (`docs/22-mejoras-futuras.md`) para el trabajo concreto que queda: crear el proyecto `ssh-access` en Infisical, dar de alta `admin` en los 7 nodos (incluido `ryzen`, que hoy no tiene ninguna cuenta de administración dedicada), retirar los 6 usuarios antiguos una vez verificado el nuevo acceso, y escribir `shared/scripts/ssh-node.sh` (el envoltorio del punto 5.4, hoy solo descrito como comandos sueltos).
