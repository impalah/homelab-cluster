# Configuración del Cudy R700 como router principal
## Dictamen
El montaje es factible. El Cudy R700 puede convertirse en el **gateway, firewall, servidor DHCP, DNS local y NAT de la LAN del homelab**, mientras usa el router de fibra como WAN principal y un router 5G con salida Ethernet como WAN secundaria. El fabricante especifica un puerto GbE WAN fijo, tres puertos GbE configurables como WAN/LAN, un puerto GbE LAN fijo, hasta cuatro WAN, balanceo de carga y respaldo de enlace.[^1][^2]

El punto delicado no es el failover, sino mantener el WiFi del router del ISP en una red situada **aguas arriba** del Cudy y permitir que sus clientes inicien conexiones hacia la LAN protegida. Se puede hacer si el router del ISP admite una ruta estática y se crean reglas explícitas en el firewall del Cudy; si no admite rutas estáticas, sólo quedarán apaños como redirecciones de puertos. La arquitectura más limpia es colocar también el WiFi detrás del Cudy mediante un punto de acceso independiente.
## Cableado propuesto
```text
                       Internet
                           │
                ONT/router de fibra ISP
                 LAN: 192.168.1.1/24
                           │
                           │ LAN del ISP
                           ▼
                WAN fijo del Cudy R700
                WAN1: 192.168.1.2/24
                           │
       ┌───────────────────┴───────────────────┐
       │          Cudy R700                    │
       │ LAN/gateway: 192.168.10.1/24          │
       │ DHCP + DNS + firewall + NAT           │
       └───────────────────┬───────────────────┘
                           │ puerto LAN fijo
                           ▼
                  TP-Link TL-SG116
                           │
              Raspberry Pi + mini-PC + AP

Router 5G ─── Ethernet ─── WAN/LAN configurable del Cudy
                         WAN2: DHCP
```

La conexión física recomendada es:

| Puerto R700 | Conexión | Función |
|---|---|---|
| WAN fijo | Puerto LAN del router de fibra | WAN1 principal |
| Primer WAN/LAN configurable | Puerto LAN del router 5G | WAN2 de respaldo |
| LAN fijo | TP-Link TL-SG116 | Toda la LAN del homelab |
| Otros WAN/LAN | Inicialmente sin usar o configurados como LAN | Administración o ampliación |

El R700 tiene exactamente esa distribución física: un WAN, tres WAN/LAN y un LAN, todos Gigabit. El TL-SG116 es un switch no gestionado, por lo que extenderá una sola LAN sin VLAN; para segmentar gestión, servidores, IoT e invitados habría que sustituirlo o añadir un switch gestionable.[^1][^3]
## Direccionamiento
Las dos redes deben ser diferentes y no solaparse:

| Red | Subred de ejemplo | Gateway/DHCP |
|---|---|---|
| WiFi y LAN del router ISP | `192.168.1.0/24` | Router ISP: `192.168.1.1` |
| WAN1 del Cudy | `192.168.1.2`, reservada por MAC o estática | Router ISP |
| LAN del Cudy | `192.168.10.0/24` | Cudy: `192.168.10.1` |
| Pool DHCP del homelab | `192.168.10.100–192.168.10.199` | Cudy |
| Infraestructura reservada | `192.168.10.2–192.168.10.99` | Reservas DHCP o IP fijas |

El Cudy trae normalmente `192.168.10.1` como dirección de administración y permite configurar el servidor DHCP y las reservas IP/MAC. Sólo debe existir un servidor DHCP por dominio de broadcast; en la LAN del TL-SG116 será el Cudy, mientras el router del ISP puede seguir sirviendo DHCP exclusivamente en su propia red `192.168.1.0/24`.[^4][^5][^6]
## Configuración básica
### Router del ISP
1. Mantener inicialmente el router ISP en modo router; no hace falta ponerlo en bridge para validar el montaje.
2. Cambiar su LAN a `192.168.1.1/24` si fuese necesario.
3. Reservar `192.168.1.2` para la MAC del WAN del Cudy.
4. Desactivar UPnP si no es necesario.
5. Opcionalmente configurar el Cudy como DMZ host sólo cuando se necesiten conexiones entrantes desde Internet; no es necesario para navegación saliente.

Con este primer montaje habrá doble NAT: Cudy traduce `192.168.10.0/24` hacia `192.168.1.2`, y el router ISP vuelve a traducir hacia la IP pública. Es perfectamente válido para navegación, repositorios, Docker y conexiones salientes, aunque complica publicar servicios y algunos protocolos. El R700 soporta NAT, port forwarding, DMZ, firewall y hasta 25.000 sesiones concurrentes según el fabricante.[^1][^7]
### Cudy R700
Conectar inicialmente un portátil al puerto LAN fijo y acceder a `http://192.168.10.1` o `http://cudy.net`; la documentación de puesta en marcha usa esa dirección y la interfaz web. Cambiar inmediatamente la contraseña predeterminada.[^5][^6]

En firmware Cudy:

```text
General Settings → WAN Mode
  WAN fijo      = WAN1
  WAN/LAN #1    = WAN2
  Resto         = LAN

General Settings → WAN Settings
  WAN1 protocol = DHCP
  WAN2 protocol = DHCP

Network / LAN
  Router IP     = 192.168.10.1/24
  DHCP          = Enabled
  Pool          = 192.168.10.100–199
  Lease         = 24 h
```

Cudy documenta que el servidor DHCP está habilitado por defecto, permite configurar pool, DNS, lease time y reservas IP/MAC. Los nodos del Swarm deberían recibir reservas DHCP, no depender de direcciones dinámicas cambiantes.[^8][^9]
## Failover fibra–5G
El R700 admite `Load Balance` y `Link Backup`; el datasheet enumera respaldo programado y por fallo, además de detección en línea. Para usar 5G sólo como respaldo, no debe configurarse balanceo con igual métrica.[^1][^10]
### Interfaces WAN
1. Ir a `General Settings → WAN Mode` y convertir un puerto WAN/LAN en WAN2.
2. Conectar el router 5G por Ethernet y dejar WAN2 como cliente DHCP.
3. Verificar en estado que WAN1 y WAN2 obtienen dirección, gateway y DNS.
4. Configurar objetivos de salud que comprueben Internet real, no sólo el gateway inmediato.

La guía práctica específica del R700 establece WAN1 con métrica 1 y WAN2 con métrica 2. Con igual peso, la menor métrica recibe el tráfico mientras está disponible; si WAN1 cae, WAN2 asume el 100%, y al recuperarse WAN1 vuelve a ser prioritaria.[^11][^12]

```text
General Settings → Load Balancing → Member
  WAN1: metric 1, weight 3
  WAN2: metric 2, weight 3
```
### Detección de caída
No basta con detectar que el cable sigue conectado: el router del ISP puede responder localmente aunque la fibra esté muerta. Debe activarse `Online Detection` o la comprobación de cada interfaz contra destinos externos fiables. La documentación Cudy permite seleccionar un objetivo manual como `8.8.8.8` para determinar si una WAN está realmente en línea.[^13]

Como punto de partida:

```text
WAN1 tracking: 1.1.1.1 y 9.9.9.9
WAN2 tracking: 8.8.8.8 y 208.67.222.222
Ping interval: 3–5 s
Fallos para declarar DOWN: 2–3
Éxitos para recuperar: 3–5
```

Una guía de configuración Cudy propone intervalo de 3 segundos y dos fallos, lo que produce una conmutación teórica próxima a 6 segundos. Para un homelab puede ser más prudente exigir tres fallos y evitar bailar la yenka entre WAN por una pérdida transitoria.[^12]

La conmutación conserva la LAN, pero las sesiones activas hacia Internet suelen romperse porque cambia la dirección pública. Las conexiones nuevas saldrán por 5G; SSH, VPN o descargas existentes tendrán que reconectar. Además, muchos operadores móviles usan CGNAT, por lo que el backup 5G puede servir para salida, pero no necesariamente para publicar servicios entrantes.
## Automatización
### Firmware Cudy
El firmware de fábrica ya ofrece automatización funcional:

- Failover y failback mediante métricas y monitorización WAN.[^11][^12]
- Detección en línea contra un host configurable.[^13]
- Reinicio programado.[^14]
- Gestión web local y, opcionalmente, remota por HTTPS con restricción de IP.[^14]
- Wake-on-LAN para equipos registrados.[^9]

No conviene publicar la interfaz web directamente en Internet. Para administración remota es preferible usar el servidor WireGuard del R700 y entrar por VPN; el equipo soporta WireGuard, OpenVPN, IPsec, L2TP y ZeroTier.[^1][^2]

No se ha encontrado una API HTTP pública y estable específica del firmware Cudy R700. La interfaz está basada en LuCI —el emulador oficial carga LuCI—, pero automatizar pulsaciones o endpoints internos de la GUI sería frágil y dependiente de versión. Para automatización reproducible mediante SSH, UCI, scripts, cron, mwan3 y Ansible, la opción sólida es instalar OpenWrt comunitario.[^15][^16]
### OpenWrt oficial
El R700 está soportado oficialmente desde OpenWrt 24.10.5, con imagen `sysupgrade` para el objetivo `ramips/mt7621`; dispone de 16 MB de flash, 128 MB de RAM, CPU dual-core a 880 MHz y cinco puertos Gigabit. Ese hardware basta para routing, DHCP, firewall y mwan3, pero la flash es escasa: no conviene convertirlo en árbol de Navidad instalando IDS, grandes listas de adblock y media docena de VPN simultáneas.[^17]

La migración requiere precaución:

1. Confirmar que es **R700 v1.0** y hacer copia de la configuración.
2. Descargar desde Cudy el firmware intermedio firmado específico del modelo.
3. Flashear primero el intermedio porque U-Boot está bloqueado.
4. Instalar después la imagen oficial OpenWrt 24.10.5 o posterior para `cudy_r700`.
5. No conservar configuración al pasar desde el firmware del fabricante.
6. Verificar checksum y mantener preparado el procedimiento TFTP de recuperación.

La necesidad del firmware intermedio y la recuperación TFTP están documentadas tanto por Cudy como por el soporte incorporado a OpenWrt. OpenWrt advierte que el proceso `sysupgrade` sólo debe hacerse con una imagen exacta para el dispositivo y verificando su SHA-256.[^18][^19][^20][^21]

Con OpenWrt completo, la administración queda disponible por:

```bash
ssh root@192.168.10.1
uci show network
uci show firewall
uci show dhcp
ubus call system board
```

Las configuraciones viven principalmente en `/etc/config/network`, `/etc/config/firewall` y `/etc/config/dhcp`. Las rutas estáticas se gestionan mediante secciones `config route` y UCI. Puede usarse Ansible sobre SSH, scripts idempotentes con UCI y `mwan3` para failover avanzado.[^22]
## Acceso desde el WiFi ISP
### Problema
Por defecto, un equipo de `192.168.10.0/24` podrá iniciar conexiones hacia `192.168.1.0/24`, porque sale por la WAN del Cudy. En sentido contrario, un cliente WiFi del ISP no sabrá dónde está `192.168.10.0/24` y, aunque lo supiera, el firewall Cudy bloqueará por defecto conexiones nuevas de WAN a LAN.[^23][^24]
### Solución enrutada
En el router del ISP hay que crear:

```text
Destino: 192.168.10.0
Máscara/prefijo: 255.255.255.0 o /24
Gateway: 192.168.1.2
Interfaz: LAN
```

La IP WAN del Cudy debe ser fija porque actúa como siguiente salto. OpenWrt documenta exactamente este patrón: subredes no solapadas, dirección upstream fija, ruta estática en el router principal y forwarding desde la red upstream hacia la LAN secundaria.[^25]

En el Cudy se debe crear una regla limitada, no abrir toda la WAN a lo bruto:

```text
Origen: WAN1 / 192.168.1.0/24
Destino: LAN / hosts concretos del homelab
Servicios: ICMP, SSH 22, HTTPS 443 y los estrictamente necesarios
Acción: ACCEPT
```

Con OpenWrt, conceptualmente:

```uci
config rule
    option name 'ISP-WiFi-to-Homelab'
    option src 'wan'
    option dest 'lan'
    option src_ip '192.168.1.0/24'
    list dest_ip '192.168.10.10'
    list proto 'tcp'
    list dest_port '22 443'
    option target 'ACCEPT'
```

OpenWrt confirma que, además de la ruta estática upstream, hay que permitir explícitamente `wan → lan`; puede restringirse por IP, puerto y protocolo. Para mantener la navegación sencilla mientras se usa el router ISP, puede dejarse el masquerading/NAT de WAN habilitado y comprobar el acceso enrutado; si se busca routing totalmente transparente, se desactiva masquerading, pero entonces el router ISP debe enrutar y hacer NAT correctamente para la subred `192.168.10.0/24`.[^26][^27][^24][^25]
### Si el ISP no admite rutas
Si el firmware ISP no permite rutas estáticas, los clientes de su WiFi no podrán descubrir ni acceder libremente a toda la LAN Cudy. Las alternativas son:

- Redirigir puertos concretos en el Cudy hacia servicios concretos, accediendo a `192.168.1.2:puerto`.
- Conectar un punto de acceso WiFi dedicado al TL-SG116 y migrar a él todos los clientes.
- Usar otro router antiguo como AP: DHCP desactivado, IP fija en `192.168.10.0/24` y conexión LAN-a-LAN con el switch.
- Instalar Tailscale o ZeroTier en clientes y servidores, aunque añade una capa overlay innecesaria para tráfico puramente local.
## Arquitectura recomendada
La opción más limpia es esta:

```text
Fibra/ONT → router ISP en bridge o DMZ → WAN1 Cudy
                                         │
                              Cudy: gateway/DHCP/firewall
                                         │
                                    TL-SG116
                                  ┌──────┴──────┐
                            cluster cableado   AP WiFi
```

El WiFi del router ISP debería dejar de usarse y el punto de acceso debería vivir detrás del Cudy. Así todos los clientes pertenecen a la LAN administrada por el Cudy, desaparece el problema WAN→LAN y existe una única autoridad de DHCP, firewall y nombres locales. Si el ISP permite bridge, también desaparece el doble NAT; si no, puede mantenerse en modo router con DMZ hacia `192.168.1.2`.

No debe conectarse simultáneamente una LAN del router ISP al WAN del Cudy y otra LAN del mismo router ISP al switch del Cudy para «compartir WiFi»: mezclaría ambos dominios, introduciría dos servidores DHCP o un camino que evita el firewall. Sería un bonito atajo para que la red se organice sola, como una verbena a las tres de la mañana.
## Orden de implantación
1. Actualizar el firmware Cudy de fábrica y guardar una copia.
2. Configurar LAN Cudy como `192.168.10.1/24`, DHCP y reservas.
3. Conectar el LAN fijo del Cudy al TL-SG116 y migrar el cluster.
4. Conectar router ISP al WAN1 y validar Internet, DNS y comunicación interna.
5. Asignar al WAN1 del Cudy `192.168.1.2` estable.
6. Si se mantiene el WiFi ISP, añadir la ruta `192.168.10.0/24 vía 192.168.1.2` y reglas mínimas WAN1→LAN.
7. Conectar el router 5G a WAN2 y configurar métricas 1/2.
8. Ajustar detección de Internet, probar desconectando la fibra y confirmar el retorno automático.
9. Migrar el WiFi a un AP detrás del Cudy cuando sea posible.
10. Valorar OpenWrt oficial sólo después de documentar y estabilizar el firmware Cudy; no hace falta flashearlo el primer día para disponer de DHCP, NAT, firewall y failover.

---

## References

1. [Gigabit Multi-WAN Router, R700 1.0](https://www.cudy.com/en-us/products/r700-1-0) - A router as the gateway of business networks, featuring up to four Multi-WAN for improved redundancy...

2. [Datasheet Gigabit Multi-WAN VPN Router | R700](https://scoop.co.za/download/cudy/CD-R700.pdf)

3. [Cudy 5 Port Gigabit Multi-WAN VPN Router | R700 - Scoopscoop.co.za › cudy-5-port-gigabit-multi-wan-vpn-router-r700](https://scoop.co.za/cudy-5-port-gigabit-multi-wan-vpn-router-r700.html) - Cudy's CD-R700 features 5x Gigabit Ethernet Ports which are comprised of 3x LAN/WAN ports, 1x dedica...

4. [Cudy R700 - Gigabit Multi-WAN VPN Router - handshake systems](https://www.handshake.co.za/2026/cudy-r700-gigabit-multi-wan-vpn-router/) - A multi-WAN, up to 4 WAN ports router that will do load balancing and failover. The reviews on the A...

5. [Cudy R700 Gigabit Multi-WAN VPN Router Guía de ...](https://manuals.plus/es/cudy/r700-gigabit-multi-wan-vpn-router-manual) - Aprenda a instalar y configurar el enrutador VPN de WAN múltiple Gigabit Cudy R700 con este manual d...

6. [Manual de usuario Cudy R700 (2 páginas)](https://www.manuales.mx/cudy/r700/manual) - Manual de Cudy R700. Vea gratis el manual de Cudy R700 o pregunte a otros propietarios de Cudy R700.

7. [Cudy R700 Gigabit Multi-WAN VPN Router Datasheet - Manuals+](https://manuals.plus/m/16d80b089040322def0d233bc10af9fcd8f8a6f7fd15f5b4743d0b2cf6808286) - Detailed datasheet for the Cudy R700 Gigabit Multi-WAN VPN Router, covering features, specifications...

8. [DHCP Server - Docs](https://docs.cudy.com/user_guide/ap_controller/dhcp/) - Documentation for Cudy Products

9. [Network - cudy docs](https://docs.cudy.com/user_guide/4g5g_router/network/) - Documentation for Cudy Products

10. [R700 V1.0 Datasheet - Manuals+](https://manuals.plus/m/c181621c52b546b3b09c75386c5912f7fa5a648763335a2ddbbe4a89e3b3a698)

11. [Cudy R700 - Gigabit Multi-WAN VPN Router | handshake systems](https://www.handshake.co.za/2025/cudy-r700-gigabit-multi-wan-vpn-router/) - A multi-WAN, up to 4 WAN ports router that will do load balancing and failover. The reviews on the A...

12. [How to set up Load Balancing and Failover on a Cudy ...](https://scoop.co.za/blog/how-to-set-up-load-balancing-and-failover-on-a-cudy-multi-wan-router)

13. [Network - Docs - docs.cudy.com](https://docs.cudy.com/user_guide/ap_controller/network/) - Documentation for Cudy Products

14. [System - cudy docs](https://docs.cudy.com/user_guide/wireless_router/system/) - Documentation for Cudy Products

15. [R700 - Cudy](https://support.cudy.com/emulator/R700/)

16. [R700](https://support.cudy.com/emulator/R700/cgi-bin/luci/admin/panel)

17. [Techdata: Cudy R700](https://openwrt.org/toh/hwdata/cudy/cudy_r700) - Device Type: Router; Brand: Cudy; Model: R700; Version: v1; Availability: Available 2025; Where avai...

18. [OpenWrt Software Download – Page 156 – Cudy](https://www.cudy.com/en-gb/blogs/faq/openwrt-software-download?page=156) - Update: December 24,2025 Good news! The OpenWrt forum has merged the pacth which supports the new Fl...

19. [[openwrt/openwrt] ramips: fix support for Cudy r700 - Mailing Lists](http://lists.infradead.org/pipermail/lede-commits/2025-November/027986.html)

20. [OpenWrt Software Download - Cudy](https://www.cudy.com/en-us/blogs/faq/openwrt-software-download) - Update: December 24,2025 Good news! The OpenWrt forum has merged the pacth which supports the new Fl...

21. [Upgrading OpenWrt firmware using LuCI](https://openwrt.org/docs/guide-quick-start/sysupgrade.luci)

22. [[OpenWrt Wiki] Static routes](https://openwrt.org/docs/guide-user/network/routing/routes_configuration)

23. [How to configure OpenWRT to just be a router (no NAT)](https://forum.openwrt.org/t/how-to-configure-openwrt-to-just-be-a-router-no-nat/241741) - Hello. I have a TP-Link A7v5 that I was able to get OpenWRT to install on pretty easily. I’d like to...

24. [OpenWRT needs masquerading on WAN interface even when used ...](https://forum.openwrt.org/t/openwrt-needs-masquerading-on-wan-interface-even-when-used-behind-isp-router/194792) - Hello, I have been trying to solve the following issue for the last few days without success, here i...

25. [[OpenWrt Wiki] Routed Client](https://openwrt.org/docs/guide-user/network/routedclient)

26. [Configure routing between LAN and WAN subnets](https://forum.openwrt.org/t/configure-routing-between-lan-and-wan-subnets/228233) - Hi all. First of all, say hello as this is my first post as I've recently joined this forum and I'm ...

27. [[OpenWrt Wiki] Firewall configuration /etc/config/firewall](https://openwrt.org/docs/guide-user/firewall/firewall_configuration)

