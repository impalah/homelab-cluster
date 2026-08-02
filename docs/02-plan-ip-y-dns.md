# 02 — Plan de IPs y DNS

## IPs fijas

| Nodo | IP |
|---|---|
| Router | 192.168.1.1 |
| ryzen.home.arpa | 192.168.1.150 |
| retaco.home.arpa | 192.168.1.174 |
| pi-dns.home.arpa | 192.168.1.170 |
| pi-obs.home.arpa | 192.168.1.171 |
| pi-sonar.home.arpa | 192.168.1.172 |
| pi-utils.home.arpa | 192.168.1.173 |
| ketekasko.home.arpa (NAS UGREEN, fuera del clúster Docker) | 192.168.1.180 |

> La IP del NAS se configura directamente en el propio dispositivo (panel de UGOS Pro), no mediante Netplan ni reserva DHCP del router — ver `docs/21-configuracion-nas-ugreen.md`.

## Registros de servicios (`*.home.arpa`)

**No se duplican aquí a propósito.** La tabla completa y actualizada de todos los nombres de host de cada servicio, con el nodo al que apuntan y el mecanismo empleado (proxy de nginx, alias directo, o protección mediante `apikey-service`), vive en un único sitio: **`shared/dns/dns-records.md`**. Es también el fichero que utiliza `shared/scripts/load-dns-records.sh` para aplicar los registros reales en Pi-hole; mantenerlo en dos sitios a la vez (aquí y allí) garantizaría que acabaran divergiendo tarde o temprano.

## Configuración de IP fija en Ubuntu (Netplan)

El fichero es `/etc/netplan/00-installer-config.yaml` (o `01-netcfg.yaml`, según la instalación). Hay que ajustar el valor de `interface` según el hardware de cada nodo (`eth0`, `enp3s0`, etc.):

```yaml
network:
  version: 2
  ethernets:
    eth0:
      dhcp4: false
      addresses:
        - 192.168.1.150/24   # Cambiar según el nodo
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses:
          - 192.168.1.170    # Pi-hole primario
          - 192.168.1.1      # Router como alternativa de respaldo
        search:
          - home.arpa
```

```bash
sudo netplan apply
```

> Existe una alternativa igual de válida, y que de hecho se usa en varios nodos de este clúster: reservar la IP por dirección MAC en el propio router, dejando el nodo con DHCP normal. Consulta la sección 4 de `docs/03-instalacion-base-ubuntu-raspi.md` para saber cuándo conviene usar una u otra.

## Configurar el router para que use Pi-hole como DNS

En el panel del router (normalmente en `192.168.1.1`), dentro de la configuración de DHCP, hay que establecer lo siguiente:

- DNS primario: `192.168.1.170`
- DNS secundario: `192.168.1.1` (o dejarlo vacío)

Si el router no permite cambiar el DNS del DHCP, hay que configurar un DNS estático en cada nodo, tal como se indica en la sección de Netplan anterior.

## Alternativa temporal: el fichero `/etc/hosts`

Si Pi-hole no está disponible durante el arranque inicial, se puede añadir manualmente, en el fichero `/etc/hosts` del nodo, lo siguiente:

```
192.168.1.150  ryzen.home.arpa
192.168.1.174  retaco.home.arpa
192.168.1.170  pi-dns.home.arpa
192.168.1.171  pi-obs.home.arpa
192.168.1.172  pi-sonar.home.arpa
192.168.1.173  pi-utils.home.arpa
192.168.1.180  ketekasko.home.arpa
```

(Los nombres de host de cada servicio, como `ollama.home.arpa`, también se pueden añadir aquí apuntando a `192.168.1.170` — consulta `shared/dns/dns-records.md` para ver la lista completa, si hace falta.)

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

En el resto de los nodos no hace falta deshabilitar `systemd-resolved`. Ahora bien, si alguna vez un nodo cliente deja de resolver `*.home.arpa` después de una interrupción breve de `pi-dns`, el problema y su solución son casi siempre los mismos: `systemd-resolved` se queda atascado en el DNS secundario — consulta `docs/13-troubleshooting.md`.
