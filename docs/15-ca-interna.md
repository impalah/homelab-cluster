# 15 — CA interna del clúster (eliminar los avisos de certificado)

## Qué es y por qué

`nginx` en `pi-dns` usaba un certificado **autofirmado**: el propio certificado se avala a sí mismo, así que ningún navegador confía en él por defecto — de ahí el aviso de "conexión no privada" en cada `*.home.arpa`.

La solución estándar para una red doméstica (no se puede usar Let's Encrypt: `*.home.arpa` no es un dominio público) es crear una **CA (entidad certificadora) propia**:

1. Se genera una CA raíz una sola vez (`generate-ca.sh`).
2. El certificado real de nginx para `*.home.arpa` lo firma esta CA (`generate-cert.sh`), no se autofirma.
3. Cada dispositivo instala **solo el certificado público de la CA** (nunca la clave privada), **una vez**.
4. A partir de ahí, confía automáticamente en el certificado actual **y en cualquiera que se regenere en el futuro** con la misma CA.

La clave privada de la CA vive únicamente en `pi-dns` (`/srv/homelab/pi-dns/nginx/ca/ca.key`, permisos `600`) — lo único realmente sensible. El `.crt` público es lo que se reparte a cada dispositivo, sin riesgo por sí solo.

---

## Descargar el certificado de la CA

```
http://192.168.1.170/ca.crt
```

o, una vez resuelva DNS: `http://pi-dns.home.arpa/ca.crt`

> Esto funciona igual desde un dispositivo remoto conectado por Tailscale (`docs/18-tailscale.md`) — la ruta a `192.168.1.0/24` lo deja alcanzable exactamente como si estuviera en la LAN. Instalar la CA ahí es un paso aparte del acceso remoto en sí: Tailscale resuelve *llegar* al clúster, la CA resuelve que el navegador *confíe* en su HTTPS.

---

## Instalación por dispositivo

### Linux (Ubuntu/Debian) — igual que en `mole`

Dos pasos — sistema y Chrome/Chromium por separado (usa su propia base NSS):

```bash
curl -s http://192.168.1.170/ca.crt -o /tmp/homelab-ca.crt

# 1. Almacén del sistema (curl, wget, herramientas OpenSSL)
sudo cp /tmp/homelab-ca.crt /usr/local/share/ca-certificates/homelab-cluster-ca.crt
sudo update-ca-certificates

# 2. Chrome/Chromium/Edge/Brave (base de datos NSS propia)
sudo apt install -y libnss3-tools
certutil -d sql:$HOME/.pki/nssdb -A -t "C,," -n "Homelab Cluster Root CA" -i /tmp/homelab-ca.crt
```

Tras el paso 2, cerrar Chrome por completo y reabrirlo. **Firefox tampoco** usa ninguno de los dos almacenes — ver su apartado más abajo.

### Windows

1. Descargar `http://192.168.1.170/ca.crt` desde el navegador.
2. Doble clic → **Instalar certificado**.
3. **Equipo local** → **Colocar todos los certificados en el siguiente almacén** → **Examinar** → **Entidades de certificación raíz de confianza**.
4. Siguiente → Finalizar.

Cubre Chrome/Edge automáticamente. Firefox necesita el paso aparte.

### macOS

1. Descargar `http://192.168.1.170/ca.crt`.
2. Doble clic — se abre Acceso a Llaveros.
3. Añadir al llavero **System** (no "login").
4. Buscarlo (`Homelab Cluster Root CA`), doble clic → **Confiar** → "Usar este certificado" → **Confiar siempre**.
5. Cerrar y confirmar con la contraseña del Mac.

Cubre Safari y Chrome. Firefox necesita el paso aparte.

### Android

1. Descargar `http://192.168.1.170/ca.crt` en el móvil (misma WiFi/LAN).
2. **Ajustes → Seguridad → Cifrado y credenciales → Instalar un certificado → Certificado de CA**.
3. Confirmar el aviso ("la red podría estar siendo supervisada" — normal al instalar una CA propia).

### iOS / iPadOS

Dos pasos, ambos obligatorios:

1. Abrir `http://192.168.1.170/ca.crt` en **Safari** (no otro navegador) → Permitir → Instalar (código del dispositivo) → Instalar de nuevo.
2. **Ajustes → General → Información → Ajustes de confianza de certificados** → activar "Homelab Cluster Root CA".

Sin el paso 2, iOS tiene el certificado pero no confía en él para TLS.

### Firefox (todas las plataformas)

No usa el almacén del sistema por defecto:

**Opción A (recomendada):** `about:config` → `security.enterprise_roots.enabled` → `true`.

**Opción B:** `about:preferences#privacy` → Certificados → Ver certificados → Autoridades → Importar → seleccionar `ca.crt` → "Confiar en esta CA para identificar sitios web".

---

## Verificar que funciona

```
https://pihole.home.arpa
https://grafana.home.arpa
https://vaultwarden.home.arpa
```

```bash
curl https://pihole.home.arpa/admin/ -o /dev/null -w "HTTP %{http_code}\n"
# HTTP 302 sin quejarse de certificado = confiando correctamente
```

---

## Regenerar el certificado de servicio (rutina, no afecta a la CA)

```bash
ssh u-dns@192.168.1.170
bash /srv/homelab/pi-dns/config/nginx/generate-cert.sh
docker exec nginx nginx -s reload
```

**No hace falta reinstalar la CA en ningún dispositivo** — el certificado nuevo sigue firmado por la misma CA.

### Añadir un nombre de host nuevo al certificado

Editar el array `DOMAINS` en `config/nginx/generate-cert.sh`, añadir el nuevo `*.home.arpa`, `generate-cert.sh` + `nginx -s reload`. Tampoco requiere tocar la CA ni los dispositivos.

---

## ⚠️ Cuándo SÍ hay que reinstalar en todos los dispositivos

Solo si se regenera la **CA** en sí (`generate-ca.sh`) — el propio script evita hacerlo por defecto si ya existe una. Motivos legítimos: sospecha de que se filtró `ca.key`, o querer empezar de cero.

---

## Detalle técnico: por qué el certificado incluye `extendedKeyUsage=serverAuth`

`generate-cert.sh` firma con `basicConstraints=CA:FALSE` y `extendedKeyUsage=serverAuth` explícitos. Sin el segundo, macOS/Safari (y Chrome en algunas configuraciones) rechazan el certificado como servidor TLS aunque la CA sea de confianza — requisito no muy conocido pero real desde hace años en el ecosistema Apple.
