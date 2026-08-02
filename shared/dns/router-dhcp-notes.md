# Configuración del router — DHCP y DNS

## Objetivo

Asegurarse de que todos los dispositivos de la red doméstica usen `pi-dns` como servidor DNS primario, de modo que puedan resolver `*.home.arpa` sin ninguna configuración adicional en cada dispositivo.

---

## Configuración del servidor DHCP del router

### Paso 1: Acceder al panel de administración del router

La IP del router suele ser `192.168.1.1`. Abrir en el navegador:

```
http://192.168.1.1
```

### Paso 2: Localizar la sección DHCP

Buscar en el menú: `LAN` → `DHCP Server` o `Red local` → `Configuración DHCP`

### Paso 3: Cambiar los servidores DNS

| Campo | Valor |
|---|---|
| DNS primario | `192.168.1.170` |
| DNS secundario | `1.1.1.1` |

> El DNS secundario `1.1.1.1` actúa como alternativa de respaldo automática si `pi-dns` está caído, pero en ese caso los nombres de host `*.home.arpa` no resolverán. Esto es el comportamiento esperado.

### Paso 4: Guardar y aplicar cambios

Los dispositivos que renueven su concesión DHCP recibirán automáticamente el nuevo DNS. Para aplicar de inmediato en un dispositivo concreto:

```bash
# Linux
sudo dhclient -r && sudo dhclient

# macOS
sudo ipconfig set en0 DHCP

# Windows (PowerShell)
ipconfig /release; ipconfig /renew
```

---

## Asignaciones DHCP estáticas (reservas por MAC)

Para garantizar que los nodos del clúster siempre reciban la misma IP, añadir reservas DHCP:

| Nombre de host | Dirección MAC | IP asignada |
|---|---|---|
| ryzen | `xx:xx:xx:xx:xx:xx` | `192.168.1.150` |
| pi-dns | `xx:xx:xx:xx:xx:xx` | `192.168.1.170` |
| pi-obs | `xx:xx:xx:xx:xx:xx` | `192.168.1.171` |
| pi-sonar | `xx:xx:xx:xx:xx:xx` | `192.168.1.172` |
| pi-utils | `xx:xx:xx:xx:xx:xx` | `192.168.1.173` |

> Sustituir los valores `xx:xx:xx:xx:xx:xx` por las MAC reales de cada nodo.
> Obtener MACs: `ip link show eth0 | grep ether`

---

## Verificación desde un cliente

Tras aplicar la configuración, verificar desde cualquier dispositivo de la red:

```bash
# Ver servidor DNS asignado
cat /etc/resolv.conf
# Debe mostrar: nameserver 192.168.1.170

# Probar resolución de nombre interno
nslookup grafana.home.arpa
# Respuesta esperada: Address: 192.168.1.170

# Probar resolución externa (verifica que Unbound funciona)
nslookup github.com
```

---

## Modelo de router compatible

Esta guía aplica a cualquier router doméstico estándar (ASUS, TP-Link, Mikrotik, OpenWrt, etc.). Los nombres de menú varían pero la lógica es idéntica: cambiar DNS primario en la configuración DHCP del servidor.

Para routers con OpenWrt:

```
# mediante SSH
uci set dhcp.lan.dhcp_option='6,192.168.1.170,1.1.1.1'
uci commit dhcp
/etc/init.d/dnsmasq restart
```
