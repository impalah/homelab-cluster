# 02 — Plan de IPs y DNS

## IPs fijas

| Nodo | IP |
|---|---|
| Router | 192.168.10.1 |
| ryzen.404labo.net | 192.168.10.10 |
| retaco.404labo.net | 192.168.10.7 |
| pi-dns.404labo.net | 192.168.10.2 |
| pi-obs.404labo.net | 192.168.10.4 | (Pi sin servicios desde 2026-10-08) |
| miugarita.404labo.net / observability.404labo.net | 192.168.10.9 |
| pi-sonar.404labo.net | 192.168.10.5 |
| pi-dns2.404labo.net | 192.168.10.3 |
| pinchi.404labo.net | 192.168.10.8 |
| miugarita.404labo.net | 192.168.10.9 |
| ketekasko.404labo.net (NAS UGREEN, fuera del clúster Docker) | 192.168.10.6 |

> La IP del NAS se configura directamente en el propio dispositivo (panel de UGOS Pro), no mediante Netplan ni reserva DHCP del router — ver `docs/21-configuracion-nas-ugreen.md`.
>
> **Ningún nodo del clúster Docker tiene IP fija configurada localmente** (Netplan/NetworkManager) — todas las IPs de la tabla de arriba (salvo el NAS y el router) las asigna el DHCP del router Cudy R700 mediante una reserva por dirección MAC, dejando el nodo en DHCP normal. Ver la nota al final de la siguiente sección.

## Registros de servicios (`*.404labo.net`)

**No se duplican aquí a propósito.** La tabla completa y actualizada de todos los nombres de host de cada servicio, con el nodo al que apuntan y el mecanismo empleado (proxy de nginx, alias directo, o protección mediante `apikey-service`), vive en un único sitio: **`shared/dns/dns-records.md`**. Es también el fichero que utiliza `shared/scripts/load-dns-records.sh` para aplicar los registros reales en Pi-hole; mantenerlo en dos sitios a la vez (aquí y allí) garantizaría que acabaran divergiendo tarde o temprano.

## Cómo se fija la IP en la práctica: reserva DHCP por MAC en el router

**Este es el mecanismo que usa realmente cada nodo del clúster hoy**, desde la migración de red al router Cudy R700 (2026-09-28) — el nodo se deja en DHCP normal (Netplan sin tocar, `dhcp4: true`), y es el propio router el que le asigna siempre la misma IP en función de su dirección MAC (panel de administración del Cudy R700, DHCP → reserva/IP-MAC binding). Consulta la sección 4 de `docs/03-instalacion-base-ubuntu-raspi.md` para el procedimiento paso a paso, y `docs/39-instalacion-miugarita.md` para un ejemplo completo de nodo dado de alta ya con este mecanismo desde el principio.

Ventaja frente a fijar la IP en el propio nodo: dar de alta o reinstalar un nodo no requiere tocar ningún fichero de red en él — basta con que su MAC ya tenga reserva en el router.

### Alternativa histórica, ya no usada: IP estática por Netplan

Antes de la migración de red, la IP se fijaba directamente en cada nodo mediante Netplan (`/etc/netplan/00-installer-config.yaml` o `01-netcfg.yaml`, según la instalación, ajustando `interface` al hardware de cada nodo — `eth0`, `enp3s0`, etc.):

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.10.10/24   # Cambiar según el nodo
      routes:
        - to: default
          via: 192.168.10.1
      nameservers:
        addresses:
          - 192.168.10.2    # Pi-hole primario
          - 192.168.10.1      # Router como alternativa de respaldo
        search:
          - 404labo.net
```

```bash
sudo netplan apply
```

Se conserva aquí como referencia histórica (algún nodo provisionado antes de la migración puede seguir teniendo este bloque sin revertir, `docs/30-instalacion-pinchi.md`) — no es el procedimiento a seguir para un nodo nuevo.

## Configurar el router para que use Pi-hole como DNS

En el panel del router (normalmente en `192.168.10.1`), dentro de la configuración de DHCP, hay que establecer lo siguiente:

- DNS primario: `192.168.10.2`
- DNS secundario: `192.168.10.1` (o dejarlo vacío)

Si el router no permite cambiar el DNS del DHCP, hay que configurar un DNS estático en cada nodo, tal como se indica en la sección de Netplan anterior.

## Alternativa temporal: el fichero `/etc/hosts`

Si Pi-hole no está disponible durante el arranque inicial, se puede añadir manualmente, en el fichero `/etc/hosts` del nodo, lo siguiente:

```
192.168.10.10  ryzen.404labo.net
192.168.10.7  retaco.404labo.net
192.168.10.2  pi-dns.404labo.net
192.168.10.4  pi-obs.404labo.net
192.168.10.5  pi-sonar.404labo.net
192.168.10.3  pi-dns2.404labo.net
192.168.10.8  pinchi.404labo.net
192.168.10.9  miugarita.404labo.net
192.168.10.6  ketekasko.404labo.net
```

(Los nombres de host de cada servicio, como `ollama.404labo.net`, también se pueden añadir aquí apuntando a `192.168.10.2` — consulta `shared/dns/dns-records.md` para ver la lista completa, si hace falta.)

## Nota sobre `systemd-resolved` y el conflicto con el puerto 53

Ubuntu 24.04 usa `systemd-resolved`, que ocupa el puerto 53 de forma local. Pi-hole, dentro de Docker, necesita ese mismo puerto — esto solo afecta a `pi-dns`, el único nodo donde se ejecuta Pi-hole:

```bash
# En pi-dns, antes de arrancar Pi-hole
sudo systemctl stop systemd-resolved
sudo systemctl disable systemd-resolved

# DNS temporal mientras Pi-hole todavía no está en marcha
echo "nameserver 1.1.1.1" | sudo tee /etc/resolv.conf

# Una vez que Pi-hole haya arrancado, apuntar a él
echo "nameserver 127.0.0.1" | sudo tee /etc/resolv.conf
```

En el resto de los nodos no hace falta deshabilitar `systemd-resolved`. Ahora bien, si alguna vez un nodo cliente deja de resolver `*.404labo.net` después de una interrupción breve de `pi-dns`, el problema y su solución son casi siempre los mismos: `systemd-resolved` se queda atascado en el DNS secundario — consulta `docs/13-troubleshooting.md`.
