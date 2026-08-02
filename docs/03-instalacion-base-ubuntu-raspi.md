# 03 — Instalación base Ubuntu Server en Raspberry Pi 5

## Imagen recomendada

Ubuntu Server 24.04 LTS para Raspberry Pi (arm64):  
https://ubuntu.com/download/raspberry-pi

Se graba con Raspberry Pi Imager o con balenaEtcher.

## Aprovisionar varias tarjetas SD con acceso SSH por usuario y contraseña

Al grabar la imagen con Raspberry Pi Imager es posible (y por defecto, en algunas configuraciones, ocurre) que el SSH quede activado **solo con autenticación por clave pública**. Si al conectar aparece:

```
ssh ubuntu@192.168.1.120
ubuntu@192.168.1.120: Permission denied (publickey).
```

significa que el `sshd` de esa Pi solo ofrece `publickey` (se puede comprobar con `ssh -v ubuntu@<ip>` — la línea `Authentications that can continue:` no incluirá `password`). No es un problema de contraseña incorrecta: el inicio de sesión por contraseña está deshabilitado a nivel de configuración, normalmente porque al personalizar la imagen se eligió "Allow public-key authentication only" en vez de "Use password authentication", o se inyectó una clave pública que no es la del equipo desde el que se conecta.

Para montar varias Pis seguidas sin tener que enchufar monitor/teclado a cada una, hay dos formas de garantizar que el primer arranque acepte login por usuario/contraseña:

### Opción A — Personalizar con Raspberry Pi Imager (recomendada, más rápida)

Antes de pulsar "Escribir" en Raspberry Pi Imager, abrir el diálogo de personalización con `Ctrl+Shift+X` (o el icono del engranaje):

1. Pestaña **General**: establecer hostname, usuario (`ubuntu` u otro) y contraseña.
2. Pestaña **Servicios** → activar **"Enable SSH"** → seleccionar **"Use password authentication"** (no "Allow public-key authentication only").
3. Guardar y grabar la imagen con normalidad.

Imager recuerda la última configuración usada, así que para las siguientes tarjetas solo hay que reabrir el diálogo y cambiar el hostname/IP de cada nodo. Con esto, `ssh ubuntu@<ip>` funciona con la contraseña indicada nada más arrancar la Pi, sin acceso físico.

### Opción B — Editar `user-data` manualmente en la partición boot

Útil si no se usa el diálogo de personalización de Imager (por ejemplo, si se graba con `dd` o con balenaEtcher), o si se quiere automatizar el proceso mediante scripts para las 4 tarjetas a la vez.

Tras grabar la imagen sin personalizar, la tarjeta expone una partición FAT llamada `system-boot` con los ficheros de `cloud-init`. Hay que montarla en el PC de gestión:

```bash
# Sustituir /dev/sdX1 por la partición boot real
lsblk
sudo mount /dev/sdX1 /mnt
```

Editar el fichero `/mnt/user-data`:

```bash
sudo nano /mnt/user-data
```

Asegurarse de que contenga estas claves (añadirlas si faltan o corregirlas si están en `false`):

```yaml
#cloud-config
hostname: pi-nodo1   # ajustar por nodo
ssh_pwauth: true
chpasswd:
  expire: true
  list:
    - ubuntu:ubuntu
```

`ssh_pwauth: true` es la clave que garantiza que `sshd` arranque con `PasswordAuthentication yes`; si está en `false` (o ausente y sobrescrita por otra personalización previa), solo se ofrecerá `publickey`. El bloque `chpasswd` fuerza el cambio de contraseña en el primer login, igual que se describe en el paso 1.

Por último, desmontar la partición y arrancar la Pi:

```bash
sudo umount /mnt
```

Para las 4 tarjetas se puede automatizar montando, editando `user-data` con `sed`/`yq` (cambiando solo hostname/IP) y desmontando en un bucle, en vez de repetir el diálogo de Imager cada vez.

### Después del aprovisionamiento

El acceso por usuario y contraseña es cómodo para el montaje inicial, pero menos seguro que el acceso mediante claves SSH. Una vez que las 4 Pi estén accesibles y configuradas, hay que aplicar el paso [1b](#1b-recomendado-sustituir-ubuntu-por-un-usuario-propio) de este manual: crear un usuario propio, copiar la clave SSH y deshabilitar `PasswordAuthentication` (`PasswordAuthentication no`) en cada nodo.

## Configuración inicial (igual en todas las Pis)

### 1. Primer arranque

Hay que conectar por SSH con el usuario por defecto (`ubuntu`/`ubuntu`). En el primer inicio de sesión, Ubuntu Server obliga a cambiar la contraseña de inmediato (pide la actual y luego la nueva dos veces). Si por algún motivo no se solicita automáticamente, se puede forzar con:

```bash
passwd
```

### 1b. (Recomendado) Sustituir `ubuntu` por un usuario propio

El usuario `ubuntu` es el nombre por defecto en todas las imágenes de Ubuntu Server, lo que lo convierte en el primer objetivo de cualquier intento de fuerza bruta por SSH contra el puerto expuesto. Usar un nombre de usuario distinto no sustituye a una buena configuración de SSH (claves, sin login por contraseña, fail2ban, etc.), pero reduce el ruido de ataques automatizados y evita depender de un nombre de cuenta público y predecible.

Pasos para crear un usuario sudoer equivalente y retirar `ubuntu`:

```bash
# 1. Crear el nuevo usuario (sustituir "miusuario" por el nombre elegido)
sudo adduser miusuario

# 2. Añadirlo al grupo sudo (privilegios equivalentes a "ubuntu")
sudo usermod -aG sudo miusuario

# 3. Añadirlo también al grupo docker si ya se instaló Docker (ver paso 5)
sudo usermod -aG docker miusuario

# 4. Copiar la clave pública SSH del PC de gestión al nuevo usuario. Ejecutar desde el PC de gestión
ssh-copy-id miusuario@192.168.1.170

# 5. Verificar en OTRA terminal (sin cerrar la sesión actual) que se puede
#    entrar con el nuevo usuario y hacer sudo correctamente
ssh miusuario@192.168.1.170
sudo whoami   # debe devolver "root"
```

#### Opcional: sudo sin pedir contraseña (NOPASSWD)

Por defecto, aunque `miusuario` esté en el grupo `sudo`, cada `sudo <comando>` pedirá su contraseña (la caché dura unos minutos y luego vuelve a pedirla). Para que no la pida nunca, crear un fichero dedicado en `/etc/sudoers.d/` — nunca editar `/etc/sudoers` directamente a mano:

```bash
sudo visudo -f /etc/sudoers.d/miusuario
```

Añadir esta línea (sustituir `miusuario` por el nombre real) y guardar:

```
miusuario ALL=(ALL) NOPASSWD:ALL
```

`visudo` valida la sintaxis antes de guardar, así que si hay un error avisa y no permite escribir un fichero roto — evita el riesgo de dejar `sudo` inutilizable para todo el sistema.

Para aplicarlo igual en las 4 tarjetas sin entrar en el editor interactivo cada vez, se puede hacer de forma no interactiva y validar después:

```bash
echo "miusuario ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/miusuario > /dev/null
sudo chmod 0440 /etc/sudoers.d/miusuario
sudo visudo -c   # valida la sintaxis de /etc/sudoers y de todo /etc/sudoers.d/
```

Si `visudo -c` reporta un error, corregir o borrar `/etc/sudoers.d/miusuario` inmediatamente antes de cerrar la sesión.

> ⚠️ Esto hace que cualquier proceso que se ejecute como `miusuario` pueda usar `sudo` sin ningún tipo de confirmación. Es cómodo para scripts de aprovisionamiento, pero reduce la protección que da sudo si la sesión o una clave SSH de ese usuario se ven comprometidas. Si se prefiere algo más acotado, se puede limitar `NOPASSWD` a comandos concretos en vez de `ALL` (p. ej. `miusuario ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/systemctl`).

Una vez confirmado que `miusuario` funciona correctamente, hay que bloquear el usuario `ubuntu` (sin borrarlo, para no perder su `$HOME` ni el historial):

```bash
sudo passwd -l ubuntu          # bloquea la contraseña; ya no se puede usar para iniciar sesión
sudo usermod -s /usr/sbin/nologin ubuntu   # opcional: impide abrir una shell aunque se use la clave SSH
```

Si se prefiere eliminarlo por completo una vez migrado todo:

```bash
sudo deluser --remove-home ubuntu
```

Como recomendación adicional, conviene deshabilitar el inicio de sesión por contraseña en SSH (dejando solo el acceso por claves) editando `/etc/ssh/sshd_config`:

```bash
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sudo systemctl restart ssh
```

> ⚠️ No cierres la sesión SSH actual hasta haber verificado el acceso con el nuevo usuario y su clave — si algo falla, te quedarías fuera del equipo, sin acceso por contraseña.

### 2. Actualizar el sistema

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget git vim htop iotop net-tools
```

#### Resolución de problemas: `Waiting for cache lock ... held by process (unattended-upgr)`

Si al ejecutar `apt update`/`apt upgrade` aparece:

```
Waiting for cache lock: Could not get lock /var/lib/dpkg/lock-frontend. It is held by process 2577 (unattended-upgr)
```

no es nada que hayas lanzado tú: es **`unattended-upgrades`**, el servicio que Ubuntu Server activa por defecto para instalar solo las actualizaciones de seguridad tras el arranque (mediante los temporizadores `apt-daily.timer` y `apt-daily-upgrade.timer`). Mientras se ejecuta, retiene el bloqueo de `dpkg`/`apt`, y cualquier comando manual choca con él.

**No lo mates con `kill -9`**: si se interrumpe a mitad de una instalación, puede dejar el sistema de paquetes en un estado inconsistente. Lo más seguro es esperar a que termine por sí solo (unos minutos, algo más en el primer arranque tras grabar la imagen):

```bash
ps aux | grep unattended-upgr
sudo tail -f /var/log/unattended-upgrades/unattended-upgrades.log
```

Para esperar automáticamente a que suelte el bloqueo antes de continuar:

```bash
sudo systemd-run --property="After=apt-daily.service apt-daily-upgrade.service" --wait /bin/true
sudo apt update && sudo apt upgrade -y
```

Si se prefiere tener control total sobre cuándo se actualizan las Pis del clúster (recomendable para evitar reinicios o cambios inesperados en mitad de una sesión de trabajo), se pueden desactivar las actualizaciones automáticas:

```bash
sudo systemctl disable --now apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service
```

### 2b. Configurar teclado español

> ℹ️ Esto solo afecta al **teclado físico conectado a la Pi** (consola local con monitor/teclado). Si te conectas por SSH, la distribución de teclado la decide el terminal de tu PC de gestión (`mole`), no la Pi — este paso no cambia nada en las sesiones SSH.

Modo interactivo:

```bash
sudo dpkg-reconfigure keyboard-configuration
```

Elegir `Generic 105-key PC` (o el modelo que corresponda) → `Spanish` → variante `Spanish` (la estándar de España). Al terminar, aplicar sin reiniciar:

```bash
sudo setupcon
```

Modo no interactivo (útil para replicar en las 4 tarjetas sin pasar por el asistente):

```bash
sudo sed -i 's/^XKBLAYOUT=.*/XKBLAYOUT="es"/' /etc/default/keyboard
sudo sed -i 's/^XKBVARIANT=.*/XKBVARIANT=""/' /etc/default/keyboard
sudo dpkg-reconfigure -f noninteractive keyboard-configuration
sudo setupcon
```

Para probar el layout en la sesión de consola actual sin tocar la configuración persistente:

```bash
sudo loadkeys es
```

### 3. Configurar hostname

```bash
# Ejemplo para pi-dns, ajustar según el nodo
sudo hostnamectl set-hostname pi-dns
echo "127.0.1.1 pi-dns.home.arpa pi-dns" | sudo tee -a /etc/hosts
```

### 4. Fijar la IP del nodo

Hay dos formas de conseguir que un nodo tenga siempre la misma IP. Cuál usar depende de si el DHCP de la red lo controla el propio router o no.

#### Si el router ya actúa como servidor DHCP (caso habitual, y el recomendado)

**No** hay que configurar una IP estática en el netplan de la Pi. Se deja en DHCP (la configuración por defecto de la imagen; no hace falta tocar nada en `/etc/netplan/`) y, en su lugar, se crea una **reserva DHCP por dirección MAC** en el router, para que le entregue siempre la misma IP a ese nodo.

El motivo es el siguiente: si se fija la IP a la vez en la Pi (mediante netplan) y en el router (dentro de un rango DHCP que incluye esa misma IP), el router puede acabar asignándosela a otro dispositivo mientras la Pi la sigue usando por su cuenta, lo que provoca un conflicto de IP difícil de diagnosticar. Con la reserva DHCP hay un único sitio (el router) que decide y reparte las IP, sin duplicidad.

Pasos a seguir:

```bash
# Obtener la dirección MAC de la interfaz de red de la Pi
ip link show eth0
```

Hay que dar de alta esa MAC en la sección de reservas DHCP, "static leases" o "IP estáticas" del router (el nombre exacto depende del fabricante), asignándole la IP deseada (por ejemplo, `192.168.1.170` para pi-dns). La Pi seguirá pidiendo IP por DHCP con normalidad; el router le entregará siempre la misma.

No hace falta reiniciar la Pi para que el cambio se aplique: basta con que renueve la concesión de DHCP (`sudo dhclient -r eth0 && sudo dhclient eth0`), o, si se prefiere, con reiniciar la Pi directamente.

#### Si no se controla el router (el DHCP lo gestiona otra persona, o se prefiere que el nodo no dependa de él)

Hay que configurar una IP estática directamente en netplan:

```bash
sudo nano /etc/netplan/00-installer-config.yaml
```

Contenido (ajustar IP y hostname según nodo):

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.1.170/24   # Cambiar según el nodo
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses:
          - 192.168.1.170
          - 192.168.1.1
        search:
          - home.arpa
```

```bash
sudo netplan apply
```

⚠️ Si se usa esta opción, la IP elegida debe quedar **fuera** del rango que reparte el DHCP del router (o excluirse explícitamente en su configuración), para evitar que se la asigne también a otro dispositivo.

### 5. Crear directorio base

```bash
sudo mkdir -p /srv/homelab
sudo chown $USER:$USER /srv/homelab
```

### 6. Copiar los archivos del nodo correspondiente

El script de instalación de Docker del paso siguiente vive en `shared/scripts/`, dentro del repositorio, y no en la carpeta de cada nodo — por eso hay que copiar **ambas** carpetas a la Pi antes de instalar Docker:

```bash
# Desde el PC de gestión, con el repositorio clonado localmente
rsync -av homelab-cluster/shared/ miusuario@192.168.1.170:/srv/homelab/shared/
rsync -av homelab-cluster/pi-dns/ miusuario@192.168.1.170:/srv/homelab/pi-dns/
```

(Hay que sustituir `pi-dns/` por la carpeta del nodo correspondiente —igual en origen y en destino— y la IP y el usuario según la Pi de que se trate. La barra final en `homelab-cluster/pi-dns/` es importante: `rsync` copia el *contenido* de esa carpeta dentro del destino, por lo que el destino debe repetir el nombre del nodo — por ejemplo, `/srv/homelab/pi-obs/` para el nodo `pi-obs`.)

> ⚠️ `shared/scripts/`, `shared/env/` y `shared/dns/` son una **copia local** en cada Pi, no un recurso compartido en red. Si se corrige o se actualiza algo en la carpeta `shared/` del repositorio (como `prepare-host.sh` o `install-docker-ubuntu.sh`), hay que repetir el `rsync -av homelab-cluster/shared/ ...` en **cada nodo** que vaya a usar ese script, antes de ejecutarlo — el cambio no llega por sí solo.

### 7. Instalar Docker

```bash
sudo bash /srv/homelab/shared/scripts/install-docker-ubuntu.sh
```

O manualmente:

```bash
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

echo "deb [arch=arm64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] \
  https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list

sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

### 8. Ajustes del kernel para SonarQube (solo pi-sonar)

```bash
# Requerido por Elasticsearch (motor interno de SonarQube)
echo "vm.max_map_count=524288" | sudo tee /etc/sysctl.d/99-sonarqube.conf
echo "fs.file-max=131072" | sudo tee -a /etc/sysctl.d/99-sonarqube.conf
sudo sysctl -p /etc/sysctl.d/99-sonarqube.conf
```

## Notas para la Raspberry Pi 5

- El firmware de la Pi 5 ya admite el arranque por USB o NVMe; se recomienda usar NVMe en pi-sonar.
- La RAM de 8 GB es suficiente para todos los stacks, excepto para SonarQube, que puede necesitar memoria de intercambio (swap):

```bash
# Añadir 4 GB de swap (solo en pi-sonar, si hiciera falta)
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```
