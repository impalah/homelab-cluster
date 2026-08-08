# 19 — Wake-on-LAN: encender "mole" (ryzen) remotamente

## Qué resuelve

`mole` (nombre de host del nodo `ryzen`, 192.168.1.150) es un PC de sobremesa con GPU que no interesa tener encendido todo el día — a diferencia del resto del clúster (Raspberry Pi + mini PC), que sí está siempre arriba. Wake-on-LAN (WoL) permite encenderla enviando un "magic packet" desde cualquier otro nodo de la LAN, sin acceso físico.

## Arquitectura

```
Otro nodo del clúster (p. ej. pi-utils)
  │  wakeonlan -i 192.168.1.255 50:eb:f6:97:31:a1   (broadcast UDP puerto 9)
  ▼
mole (192.168.1.150, apagada/suspendida/hibernada)
  └─ NIC enp6s0 (Intel I225, driver igc) — sigue recibiendo alimentación en
     espera y "escucha" ese broadcast a nivel de firmware/NIC, incluso con
     el equipo apagado
```

El magic packet es un broadcast de capa 2/UDP normal — no importa desde qué nodo de `192.168.1.0/24` se envíe, mientras esté en el mismo segmento (todo el clúster lo está). `pi-utils` se usa como origen por convención (nodo "de utilidades"), no por necesidad técnica — ver `shared/scripts/wake-mole.sh`.

## Comprobación previa (ya hecha en `mole`)

```bash
ip -br a                          # identificar la interfaz real (enp6s0)
sudo ethtool enp6s0 | grep -i wake
```

Resultado en este clúster:

```
Supports Wake-on: pumbg   ← la NIC soporta magic packet ("g")
Wake-on: g                ← ya estaba activado por defecto (driver igc)
Link detected: yes
```

```bash
cat /proc/acpi/wakeup | grep -i i225
# I225   S4   *enabled   pci:0000:06:00.0
```

El dispositivo PCI de la NIC ya tiene el wakeup ACPI habilitado para S4 (hibernación) — sin tocar nada.

## Configuración aplicada

### 1. Persistir `Wake-on: g` en NetworkManager

Por defecto, el ajuste de NetworkManager para la conexión estaba en `default` (hereda lo que traiga el driver/kernel en cada arranque). Para no depender de eso — por ejemplo tras una actualización de kernel que cambie el comportamiento por defecto del driver `igc` — se fijó explícitamente:

```bash
CONN="Conexión cableada 1"   # nombre real del perfil en mole, ver `nmcli connection show`
sudo nmcli connection modify "${CONN}" 802-3-ethernet.wake-on-lan magic
```

Verificación: `nmcli connection show "${CONN}" | grep -i wake` → debe mostrar `802-3-ethernet.wake-on-lan: magic`. Aplica en el próximo arranque/reconexión de la interfaz — no hace falta reiniciar para que `ethtool` siga mostrando `g` ahora mismo, ya lo traía así el driver.

### 2. Envío del magic packet desde otro nodo

`shared/scripts/wake-mole.sh` — instala `wakeonlan` en el nodo origen (si falta) y envía el paquete. Detecta si ya se está ejecutando en el propio nodo destino (lo envía en local) o si hay que saltar por SSH a otro nodo.

⚠️ **Importante**: como el objetivo es encender `mole` estando apagada, el script **no puede lanzarse desde la propia `mole`** en ese momento — hay que ejecutarlo desde otro nodo del clúster, o por SSH contra otro nodo desde tu propio equipo. Por eso `shared/scripts/wake-mole.sh` (como el resto de `shared/scripts/`, ver `docs/03-instalacion-base-ubuntu-raspi.md`) está desplegado como copia local en `/srv/homelab/shared/scripts/` de cada uno de los 5 nodos siempre encendidos, no solo en este checkout — cualquiera de ellos puede lanzarlo sin depender de que `mole`/este repo estén disponibles:

```bash
# Desde tu equipo, por SSH directo a cualquier nodo siempre encendido:
ssh u-utils@192.168.1.173 "bash /srv/homelab/shared/scripts/wake-mole.sh pi-utils"
ssh u-dns@192.168.1.170   "bash /srv/homelab/shared/scripts/wake-mole.sh pi-dns"

# O, si mole está encendida y este checkout disponible, en modo "control"
# (salta por SSH desde aquí hacia el nodo elegido):
bash shared/scripts/wake-mole.sh              # hacia pi-utils (por defecto)
bash shared/scripts/wake-mole.sh pi-dns       # hacia otro nodo
```

`wakeonlan` ya está instalado en `pi-utils` (`u-utils@192.168.1.173`) — preparado para usarse en cualquier momento.

⚠️ Si en el futuro se edita `wake-mole.sh` (o cualquier otro script de `shared/scripts/`), hay que repetir el `rsync -av shared/ <nodo>:/srv/homelab/shared/` en los 5 nodos — no es un recurso compartido en red, cada uno tiene su propia copia (mismo aviso que ya existía para el resto de `shared/`).

## 3. BIOS/UEFI — el paso que NO se puede hacer desde Linux (ya aplicado)

`Wake-on: g` activado en el sistema operativo es **necesario pero no suficiente**. Con el equipo completamente apagado (S5), es la propia placa base/firmware la que tiene que dejar pasar la señal a la NIC estando "apagada" — eso se controla con un ajuste de BIOS/UEFI que no es visible ni modificable desde Linux, y solo se comprueba/activa entrando físicamente a la BIOS.

**Hardware real de `mole`** (confirmado con `dmidecode`):

```
Manufacturer: ASUSTeK COMPUTER INC.
Product Name: ROG STRIX B550-XE GAMING WIFI
BIOS Vendor:  American Megatrends Inc. (versión 2425, 2021)
```

Primer intento: la opción de WoL **no aparecía en absoluto** en la BIOS. Causa real (confirmada, no solo sospecha): esta placa tiene un ajuste **"ErP Ready"** en `Advanced → APM Configuration` que, si está activado (`Enabled (S4+S5)` o similar), corta la alimentación en espera de USB/PCI-E — incluida la NIC — para cumplir la normativa europea de bajo consumo. Con ErP activo, el propio menú de WoL puede quedar oculto o atenuado, no solo desactivado.

**Pasos aplicados (funcionando, verificado con apagado real + magic packet)**:

1. Entrar a la BIOS (`Supr` al arrancar) → **Advanced Mode** (`F7` si
   arranca en modo EZ)
2. `Advanced → APM Configuration`
3. **ErP Ready** → `Disabled`
4. **Power On By PCI-E/PCI** → `Enabled` (este es el interruptor de WoL en
   sí, en placas ASUS vive en este mismo submenú)
5. Guardar y salir (`F10`)

Si en otra placa/fabricante la opción de WoL tampoco aparece a la primera, buscar primero un ajuste de tipo **ErP/EuP** en el mismo menú de energía — es la causa más común de "la opción no existe" cuando el hardware sí la soporta.

## S3 vs S4 vs S5 — ¿es más fácil si dejo `mole` hibernada?

Depende de qué se compara exactamente. Resumen:

| Estado | Qué pasa | WoL mediante magic packet |
|---|---|---|
| **S3 (suspender / "sleep")** | RAM sigue alimentada, todo lo demás para | El más fiable y rápido de los tres — es el propio kernel el que arma el wakeup ACPI al suspender, casi nunca depende de un ajuste de BIOS aparte. Consumo en espera algo mayor que S4/S5. |
| **S4 (hibernar)** | Estado volcado a disco, casi toda la alimentación cortada | Ya confirmado arriba que el wakeup ACPI para la NIC está `*enabled` en S4 sin tocar nada — en teoría debería funcionar igual de bien que S3 **en el arranque de vuelta**, pero en Linux con GPU NVIDIA la hibernación es la opción menos fiable de las tres: es frecuente que el driver NVIDIA no restaure bien el estado de la GPU al volver (síntoma típico: contenedores con `--gpus all` fallan hasta reiniciar el servicio o el propio equipo), justo el caso de `mole` (RTX 5070 + RTX 3070). No se recomienda para este nodo sin probarlo primero a fondo. |
| **S5 (apagado completo)** | Equipo totalmente apagado salvo alimentación de espera a la placa | ✅ **Confirmado funcionando en `mole`** tras desactivar "ErP Ready" y activar "Power On By PCI-E/PCI" en la BIOS (sección 3). Es el único que da un apagado real (mínimo consumo, arranque limpio de todos los servicios, sin arrastrar ningún estado de GPU previo). |

**Recomendación (aplicada y en uso)**: para el caso de uso descrito ("no me interesa tenerlo encendido todo el día"), **apagado completo (S5)** es la opción usada — evita por completo el problema de reanudación de la GPU en Linux/NVIDIA, a cambio de un arranque algo más lento (boot completo en vez de reanudar desde RAM/disco). La suspensión (S3) sigue siendo una alternativa válida si algún día se prioriza velocidad de reanudación sobre ahorro máximo de energía. La hibernación (S4) sigue sin recomendarse: comparte el riesgo de reanudación de la GPU de S3 sin su ventaja de velocidad.

## Verificación

```bash
# Desde otro nodo, con mole apagada:
bash shared/scripts/wake-mole.sh
ping -c 5 192.168.1.150          # espera unos 20-40s a boot completo (BIOS + POST + Linux)

# Una vez arriba, comprobar que los servicios con GPU están realmente bien
# (no solo que el host responda a ping):
curl -s http://192.168.1.150:11434/api/tags   # ollama
nvidia-smi                                     # en la propia mole, por SSH
```

## Resolución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `mole` no responde a `ping` tras el magic packet, estando apagada (S5) | Ajuste de BIOS "Power On By PCI-E/PCI" desactivado, o bloqueado por "ErP Ready" activo | Sección 3 — en placas ASUS, revisar `Advanced → APM Configuration` para ambos ajustes |
| La opción de WoL no aparece en absoluto en la BIOS | Ajuste "ErP Ready"/"EuP" activo la oculta o desactiva (visto en este clúster, ASUS ROG STRIX B550-XE) | Desactivar ErP primero — el menú de WoL suele reaparecer justo al lado |
| Funciona apagada pero no suspendida/hibernada, o viceversa | Cada S-state depende de mecanismos distintos (ACPI del kernel vs firmware de placa) | Confirmar `/proc/acpi/wakeup` para S3/S4, BIOS para S5 — son independientes |
| `wakeonlan: command not found` en el nodo origen | No estaba instalado | `shared/scripts/wake-mole.sh` lo instala solo; si falla, `sudo apt-get install -y wakeonlan` a mano |
| Tras hibernar y despertar, `ollama`/`whisper-service` fallan aunque el host responda | Problema conocido de reanudación de la GPU NVIDIA tras S4/S3 en Linux | Evitar hibernar/suspender este nodo (usar S5); si hace falta S3, reiniciar el contenedor o el host tras despertar |
| `Wake-on: d` en vez de `g` tras un reinicio | El driver `igc` volvió al valor por defecto, o el perfil de NetworkManager no tiene el ajuste explícito | Repetir `nmcli connection modify ... 802-3-ethernet.wake-on-lan magic` (sección "Configuración aplicada") |
