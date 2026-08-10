# 21 — NAS UGREEN NASync DH2300 (`ketekasko`)

## Qué es

Dispositivo adicional en la LAN, **no forma parte del clúster Docker** — no tiene `docker-compose.yml` ni directorio de nodo en este repo, es un NAS con su propio sistema operativo (**UGOS Pro**, el OS propio de UGREEN para su gama NASync).

| | |
|---|---|
| Modelo | UGREEN NASync DH2300 |
| Nombre de host | `ketekasko` |
| IP fija | `192.168.1.180` (configurada en el propio NAS, no en `pi-dns`) |
| Almacenamiento | 2 discos en RAID 1, volumen de 3.6 TB |
| SO | UGOS Pro |
| Acceso | SSH activado en el propio NAS |

## Alta en la red del clúster

`ketekasko.home.arpa` se añadió como **alias DNS directo** (mismo patrón que `postgresql.home.arpa`, ver `shared/dns/dns-records.md`) — no pasa por `nginx`/`pi-dns`, porque UGOS Pro sirve su propia interfaz con su propio certificado TLS en el puerto `9443` (no el 443 que usa `nginx`), así que un alias directo a la IP es más simple que meterlo detrás del proxy inverso.

```bash
# Registro añadido a shared/dns/dns-records.md y shared/scripts/load-dns-records.sh
# ("192.168.1.180 ketekasko.home.arpa"), aplicado con:
ssh u-dns@192.168.1.170 'cd /srv/homelab/shared/scripts && set -a; source /srv/homelab/pi-dns/.env; set +a; PIHOLE_URL=https://pihole.home.arpa PIHOLE_PASSWORD="$PIHOLE_PASSWORD" bash load-dns-records.sh'
```

También se añadió una tarjeta en el panel `index.home.arpa` (`pi-dns/config/nginx/html/index.html`), con icono descargado localmente desde [dashboardicons.com](https://dashboardicons.com/icons/ugreen-nas) (proyecto `homarr-labs/dashboard-icons`) — enlaza directamente a `https://ketekasko.home.arpa:9443`.

## Activar SMB (Mac/Windows)

`Panel de control → Servicios de archivos → SMB` → activar el servicio → Aplicar. Estándar, sin particularidades.

## Activar NFS y forzar NFSv4

La GUI de UGOS Pro **limita el protocolo máximo a NFSv3** — no hay selector de v4 en la interfaz. Para NFSv4 hace falta editar la configuración por SSH.

### 1. Activar el servicio NFS en la GUI

`Panel de control → Servicios de archivos → NFS` → activar el checkbox → Aplicar.

### 2. Forzar NFSv4 mediante SSH

Dos ficheros a editar, en el propio NAS por SSH:

**`/etc/nfs.conf`** — fichero estándar de `nfs-utils` (Linux por debajo de UGOS Pro), sección `[nfsd]`. Por defecto trae `vers4`/`vers4.0`/`vers4.1`/`vers4.2` todos en `n`:

```bash
sudo sed -i -E \
  -e 's/^(vers4[[:space:]]*=[[:space:]]*)n$/\1y/' \
  -e 's/^(vers4\.0[[:space:]]*=[[:space:]]*)n$/\1y/' \
  -e 's/^(vers4\.1[[:space:]]*=[[:space:]]*)n$/\1y/' \
  -e 's/^(vers4\.2[[:space:]]*=[[:space:]]*)n$/\1y/' \
  /etc/nfs.conf

grep '^vers' /etc/nfs.conf   # verificar: vers2/3/4/4.0/4.1/4.2 deben quedar en "= y"
```

**`/etc/nfs.json`** — fichero propio de UGOS Pro que la GUI usa para **regenerar** `nfs.conf` al pulsar "Aplicar" en la pantalla de NFS del Panel de control. Si no se edita también este fichero, la próxima vez que se toque esa pantalla puede sobrescribir `nfs.conf` de vuelta a NFSv3. Su esquema no está documentado públicamente — el campo relevante encontrado en este NAS:

```bash
sudo cat /etc/nfs.json
# {
#   "enableNfsServer": true,
#   "maximumNFSProtocol": "NFSv3",
#   ...
# }

sudo sed -i 's/"maximumNFSProtocol": "NFSv3"/"maximumNFSProtocol": "NFSv4"/' /etc/nfs.json
sudo cat /etc/nfs.json   # confirmar "maximumNFSProtocol": "NFSv4"
```

⚠️ Tras editar ambos ficheros, **evitar volver a tocar la pantalla de NFS del Panel de control** salvo que se compruebe después (mediante `/proc/fs/nfsd/versions`, ver abajo) que sigue en v4 — no está confirmado al 100% que `maximumNFSProtocol` sea el único campo que gobierna la regeneración, solo que es el más plausible por nombre y por ser el que cambia de `NFSv3` a lo que sea que se seleccione en la GUI.

### 3. Reiniciar el servicio

```bash
sudo systemctl restart nfs-kernel-server   # comprobar el nombre real con: systemctl list-units | grep -i nfs
```

### 4. Verificar que NFSv4 está realmente sirviendo

```bash
cat /proc/fs/nfsd/versions
```

Salida real obtenida en `ketekasko`:

```
+3 +4 +4.1 +4.2
```

Lectura: `+3` (NFSv3 sigue activo, compatibilidad), `+4` (NFSv4 activo — esto ya cubre la versión base 4.0, el kernel no siempre lista `4.0` como entrada aparte), `+4.1`/`+4.2` (subversiones activas). No aparece `2` porque este build de `nfsd` no trae compilado NFSv2, sin relación con lo configurado aquí. Sin ningún `-` (deshabilitado) en la lista → correcto.

### ⚠️ NFSv4 se negocia pero el montaje falla — pseudo-root no expuesto

Con el servicio ya en v4 (confirmado arriba), montar por v4 falla igualmente:

```
mount.nfs4: mounting ketekasko.home.arpa:/nfs-data failed, reason given by server: No such file or directory
mount.nfs4: mounting ketekasko.home.arpa:/volume1/nfs-data failed, reason given by server: No such file or directory
```

Probado tanto con la ruta "bonita" (`/nfs-data`) como con la ruta real del export (`/volume1/nfs-data`, confirmada con `showmount -e ketekasko.home.arpa`) — ambas fallan igual. **Causa**: NFSv4 usa un "pseudo-filesystem root" (normalmente un export especial con `fsid=0`) al que los clientes montan de forma relativa; sin ese export raíz configurado en el servidor, cualquier ruta v4 da `No such file or directory` aunque el export exista y esté bien permisado — confirmado montando la misma ruta con NFSv3 (que no usa pseudo-root, monta rutas reales directamente): monta sin problema y la escritura como `root` funciona (sin squash, tal como se configuró). Es decir, el export en sí está bien — es un hueco específico de v4 en cómo UGOS Pro genera `/etc/exports` desde la GUI (pensado para v3), no algo que dependa de `nfs.conf`/`nfs.json`.

**Decisión tomada**: usar NFSv3 para el uso real (funciona perfectamente para bind mounts de Docker/Forgejo en esta LAN de confianza) y dejar NFSv4 como pendiente — arreglarlo del todo requeriría añadir a mano un export `fsid=0` en `/etc/exports` del NAS por SSH, sin garantía de que UGOS Pro no lo sobrescriba igual que hace con `nfs.conf`/`nfs.json`. Ver `docs/22-mejoras-futuras.md` si se retoma más adelante.

## Montar desde un cliente Linux

Requiere el paquete `nfs-common` (trae el programa auxiliar `mount.nfs`/`mount.nfs4` — sin él, `mount -t nfs`/`nfs4` falla con "opción incorrecta"):

```bash
sudo apt-get install -y nfs-common
```

⚠️ Usar la **ruta real del export**, no el nombre de la carpeta a secas — confírmala con `showmount -e ketekasko.home.arpa` (en este caso, `/volume1/nfs-data`, no `/nfs-data`).

```bash
sudo mkdir -p /mnt/nfs-data
sudo mount -t nfs -o vers=3 ketekasko.home.arpa:/volume1/nfs-data /mnt/nfs-data
```

Persistente mediante `/etc/fstab` en el cliente:

```
ketekasko.home.arpa:/volume1/nfs-data /mnt/nfs-data nfs vers=3,defaults,_netdev 0 0
```

### Clientes montados hoy

| Nodo | Punto de montaje | Uso |
|---|---|---|
| `retaco` | `/mnt/nfs-data` | `/data/input`/`/data/output` de `epub2pdf-service` y `pdf2chunks-service` (subcarpetas `epub2pdf/`, `pdf2chunks/`) — ver `docs/05-instalacion-retaco.md` sección 5.4 |

⚠️ **`stat`/`ls` sobre el punto de montaje como usuario sin privilegios pueden devolver "Permiso denegado" o `mode 0000` de forma intermitente**, pese a que el export tiene permisos abiertos y root squash desactivado — observado en vivo montando desde `retaco`. El acceso como `root` (por `sudo`, o el propio proceso `root` dentro de un contenedor Docker) siempre funciona con normalidad, verificado con lectura y escritura reales — no bloquea el caso de uso real (contenedores que escriben como root, ver sección "Esquema de carpetas de este NAS" más arriba). No investigado a fondo el motivo exacto; probablemente una peculiaridad de cómo UGOS Pro calcula o cachea los atributos NFSv3, no un problema de permisos real.

## Esquema de carpetas de este NAS

Volumen total 3.6 TB (RAID 1), repartido en dos carpetas compartidas:

| Carpeta | Protocolo | Cuota | Uso |
|---|---|---|---|
| `nfs-data` | NFS (v3 — ver aviso de v4 arriba) | 1.5 TB | Bind mounts de Docker/contenedores, apps tipo Forgejo |
| `media` | SMB | resto (~2.1 TB) | Acceso desde Mac/Windows |

**`nfs-data`** — `Propiedades → pestaña "Permiso NFS"`:
- Host/red permitida: `192.168.1.0/24`
- Privilegio: Lectura/Escritura
- Squash de root: **desactivado** — decisión consciente para que procesos dentro de contenedores que escriban como `root` lo hagan también como `root` en el NAS, sin mapear a un usuario sin privilegios (evita fallos de permisos opacos en bind mounts de Docker). Contrapartida asumida: cualquier `root` en la LAN `192.168.1.0/24` tiene control total sobre esta carpeta — aceptable en esta LAN de confianza, no expuesta a Tailscale/internet.
- No requiere usuario del NAS — NFS con `AUTH_SYS` controla acceso por IP/red, no por cuenta.

**`media`** — SMB sí requiere una cuenta de usuario del NAS (`Panel de control → Usuario → Crear`) con permiso de Lectura/Escritura asignado en `Propiedades → pestaña "Permiso"` de la carpeta — sin acceso anónimo/invitado, coherente con el resto del clúster (todo autenticado).

### Esquema de usuarios (confirmado en uso)

`linus` era originalmente la cuenta de administración del NAS (la del primer acceso, en la configuración inicial) — reutilizarla también para montar `media` por SMB habría expuesto credenciales de administrador completo en cualquier dispositivo/app que las guardara, solo para acceder a una carpeta de medios. Esquema aplicado en su lugar:

1. Cuenta de administración **nueva y separada**, creada y verificada (inicio de sesión + acceso al Panel de control completo) antes de tocar nada más.
2. `linus` **degradado a usuario normal** (`Panel de control → Usuario` — quitar el rol/grupo de administrador) — degradar la cuenta no concede permisos de carpeta automáticamente, son independientes.
3. `linus` con Lectura/Escritura explícita sobre `media` (`Propiedades de "media" → pestaña "Permiso"`).

Así, la cuenta que queda guardada en portátiles/apps para el día a día (`linus`) no tiene ningún privilegio de administración del NAS, aunque se filtre su contraseña — la cuenta de administración solo se usa puntualmente, de forma manual.

## Conectar a `media` (SMB) desde cada sistema

Probado y funcionando en macOS y Windows.

**macOS:**
1. Finder → menú `Ir → Conectar al servidor…` (o `⌘K`)
2. Dirección del servidor: `smb://ketekasko.home.arpa/media`
3. Conectar → usuario/contraseña de la cuenta con permiso sobre `media` (`linus`, ya degradado a usuario normal)

**Windows:**
1. Explorador de archivos → barra de direcciones: `\\ketekasko.home.arpa\media`
2. Si pide credenciales: mismo usuario/contraseña que en macOS
3. Para que quede como unidad fija: clic derecho en "Este equipo" → `Conectar a unidad de red` → misma ruta, marcar "Conectar de nuevo al iniciar sesión"

## Carpetas compartidas — ¿una para SMB y otra para NFS, o la misma?

En UGOS Pro, una misma carpeta compartida tiene **pestañas de permisos independientes por protocolo** en sus propiedades (`Archivos → carpeta → Propiedades → pestaña "Permiso NFS"`, y otra para SMB) — se puede compartir **una única carpeta con ambos protocolos a la vez**, no hace falta duplicarla.

**Recomendación**: para uso doméstico normal (documentos, backups, medios), una sola carpeta con ambos protocolos activados es lo habitual y más simple. Dos puntos a vigilar si se comparte así:

- **UID/GID consistentes** — SMB usa su propio modelo de usuarios; NFS (sobre todo v3) se basa en UID/GID Unix. Si un fichero se crea desde SMB y el UID resultante no coincide con el usuario Linux que lo ve por NFS, aparecen permisos incoherentes o propietario `nobody`. NFSv4 lo mitiga algo (usa identidades `usuario@dominio`), pero conviene revisar el mapeo de identidades (`/etc/idmapd.conf` en los clientes Linux) si aparece ese síntoma.
- **Escritura concurrente real** (mismo fichero editado desde SMB y NFS a la vez) — el bloqueo de ficheros no es 100% intercambiable entre ambos protocolos. Para uso normal (cada máquina trabaja con sus propios ficheros) no es problema; para algo que escriba activamente desde ambos lados a la vez (p. ej. una base de datos en fichero), mejor separar carpetas o protocolos.

## Fuentes consultadas

- [UGREEN NAS Apps & Software | UGOS Pro, Docker & VM Support](https://ai.ugreen.com/pages/solution-software)
- [Mounting NFS Share From UGREEN NAS to a Linux Machine](https://dzakiy.me/mounting-nfs-share-from-ugreen-nas-to-a-linux-machine)
- [How to Connect Kodi to Your UGREEN NAS (SMB, NFS, WebDAV Guide)](https://nas.ugreen.com/blogs/how-to/connect-kodi-to-ugreen-nas)
