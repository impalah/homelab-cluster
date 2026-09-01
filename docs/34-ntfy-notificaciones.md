# 34 — ntfy: canal de notificación proactivo del clúster

## Qué es y por qué está aquí

Mejora 4 del backlog (`docs/22-mejoras-futuras.md`). Hasta ahora ninguna alerta del clúster avisaba activamente a nadie — la de undervoltage (`docs/14-monitorizacion-completa-cluster.md`) y las del SAI (`docs/33-nut-sai.md`) solo eran visibles entrando al panel de Grafana. [ntfy](https://ntfy.sh) es un servidor de notificaciones push HTTP muy simple: cualquier cliente (curl, un script Python, Grafana, el móvil) publica un mensaje con un `POST` a `https://ntfy.404labo.net/<topic>`, y cualquiera suscrito a ese topic (la app oficial, un navegador, otro script) lo recibe en segundos. No requiere cuenta de Google/Apple ni un backend propio de push — es la pieza que faltaba para que las alertas dejen de ser "solo de consulta".

Autoalojado (no `ntfy.sh`, la instancia pública) — mismo criterio que Vaultwarden/Infisical/Forgejo: FOSS real, sin depender de un tercero para algo tan sensible como los avisos del propio clúster.

## Arquitectura

- **Stack Swarm** (`docker-swarm/stacks/ntfy/docker-compose.yml`), imagen oficial `binwiederhier/ntfy`. A diferencia de casi todos los demás servicios con estado del clúster, **nace directamente como stack Swarm** — no es una migración de un servicio Compose preexistente, así que no hay bind-mount real que mover ni motivo histórico para fijarlo a un nodo concreto.
- **Sin `node.hostname` fijo** — usa `node.labels.role == stateful` (`retaco`/`pinchi`, ver `docs/31-docker-swarm.md`), el destino por defecto documentado para cualquier servicio nuevo con estado. El único estado real es `cache.db` (historial corto de mensajes, retenido 12h) y `attachments/` — volumen de escritura bajo, nada comparable al WAL de una base de datos de aplicación.
- **Expuesto en `ntfy.404labo.net` vía Traefik** (labels `traefik.http.routers.*` en el propio stack, mismo patrón que `markitdown`), certificado real de Let's Encrypt (wildcard `*.404labo.net`). Alcanzable desde la LAN y, vía Tailscale (`docs/18-tailscale.md`, Split DNS), desde fuera de casa.
- **Auth propia de ntfy**, `NTFY_AUTH_DEFAULT_ACCESS=deny-all` — sin usuario/token válido, ni lectura ni escritura en ningún topic. No está protegido con `apikey-service` (los clientes ntfy, incluida la app móvil, no mandan `X-Api-Key`).
- **Datos**: `/srv/homelab/ntfy/data` (ruta compartida, no bajo ningún `<node>/` — igual que `markitdown-cache`/`valkey`/`infisical`, porque el scheduler de Swarm puede colocar la tarea en cualquiera de los dos nodos `role=stateful`). Crear y dar permisos **en los dos candidatos** (`retaco` y `pinchi`) antes del primer despliegue:

  ```bash
  ssh u-data@192.168.1.174 "sudo mkdir -p /srv/homelab/ntfy/data && sudo chown u-data:u-data /srv/homelab/ntfy/data"
  ssh u-forge@192.168.1.175 "sudo mkdir -p /srv/homelab/ntfy/data && sudo chown u-forge:u-forge /srv/homelab/ntfy/data"
  ```

## Despliegue

Desde un manager del Swarm (patrón habitual, ver la sección "Deploying to a Docker Swarm stack" del `CLAUDE.md` raíz / `docker-swarm/README.md`):

```bash
rsync -av docker-swarm/stacks/ntfy/docker-compose.yml u-data@192.168.1.174:/tmp/ntfy-compose.yml
ssh u-data@192.168.1.174 "docker stack deploy -c /tmp/ntfy-compose.yml ntfy --with-registry-auth"
docker service ls | grep ntfy
```

Verificación rápida (sin auth todavía configurada, `deny-all` responde `401`, lo cual ya es una señal de que el servicio está vivo):

```bash
curl -i https://ntfy.404labo.net/v1/health
```

## Alta del usuario y los tokens — obligatorio antes de usarlo para nada

Con `NTFY_AUTH_DEFAULT_ACCESS=deny-all` no hay topics públicos: hace falta un usuario y, para consumo programático, un token de acceso. Todo se gestiona con la CLI `ntfy` dentro del propio contenedor (`docker exec`, en el nodo donde haya aterrizado la tarea — `docker service ps ntfy_ntfy` para verlo):

```bash
# Usuario "grafana" (el que usa el contact point de Grafana, ver más abajo) —
# rol "user" normal, no admin.
docker exec -it $(docker ps -q -f name=ntfy_ntfy) ntfy user add grafana
docker exec -it $(docker ps -q -f name=ntfy_ntfy) ntfy access grafana homelab-alerts write-only

# Token de acceso para el propio usuario "grafana" -- esto es lo que va en
# el campo "password" de pi-obs/config/grafana/alerting/ntfy-contactpoint.yml
# (la copia DESPLEGADA, nunca la de git -- ver el comentario de ese fichero)
docker exec -it $(docker ps -q -f name=ntfy_ntfy) ntfy token add grafana

# Un segundo usuario, uno por app/persona que vaya a leer o publicar --
# igual que las API keys de apikey-service, no se comparte un único
# usuario/token entre consumidores distintos.
docker exec -it $(docker ps -q -f name=ntfy_ntfy) ntfy user add mi-app
docker exec -it $(docker ps -q -f name=ntfy_ntfy) ntfy access mi-app homelab-alerts write-only
docker exec -it $(docker ps -q -f name=ntfy_ntfy) ntfy token add mi-app
```

`ntfy access <user> <topic> <permission>` acepta `read-only`/`write-only`/`read-write`/`deny`, y `<topic>` admite comodines (`homelab-*`). Los tokens no caducan por defecto (`ntfy token add --expires` para ponerles fecha). Listar/revocar: `ntfy token list <user>` / `ntfy token remove <user> <token>`.

## Sistemas de notificación disponibles

Todo lo que sigue habla el mismo protocolo HTTP — no hay un "sistema" propietario distinto por canal, solo formas distintas de conectarse al mismo servidor:

| Método | Para qué sirve | Detalle |
|---|---|---|
| **Web app** (`https://ntfy.404labo.net`) | Ver notificaciones desde cualquier navegador, sin instalar nada | Requiere la pestaña abierta salvo que se configure Web Push (ver más abajo) |
| **PWA** (la propia web app "instalada") | Icono propio en el escritorio/launcher/pantalla de inicio, como una app nativa | Soportado en Chrome (Android/Windows/Linux/macOS), Safari (iOS 16.4+/macOS 14+), Firefox Android, Edge. Necesita Web Push configurado para recibir en segundo plano |
| **App oficial Android** (Play Store / F-Droid / APK de GitHub) | Notificaciones en el móvil, con canales de prioridad, sonidos, acciones | Por defecto usa "entrega instantánea" (servicio en primer plano) en vez de Firebase — ver la sección de push nativo más abajo |
| **App oficial iOS** (App Store) | Lo mismo en iPhone/iPad | iOS no permite el mismo truco de "servicio en primer plano" que Android — necesita el relé de sondeo (`upstream-base-url`) para ser rápida, ver más abajo |
| **ntfy CLI** (`ntfy subscribe <topic>`) | Terminal/scripts — mismo binario que el servidor | `docs.ntfy.sh/subscribe/cli` — útil para probar rápido desde cualquier nodo con el cliente instalado, sin escribir curl a mano |
| **API HTTP genérica** — esto es lo que responde a "¿puedo suscribirme desde un servicio externo?" | Cualquier aplicación, script o plataforma de automatización que hable HTTP | Ver subsección siguiente |

### Suscribirse desde un servicio externo (script, otra plataforma, otro nodo)

Sí — es la forma más flexible, y no necesita la app ni el navegador. Cuatro variantes del mismo endpoint, todas en `https://ntfy.404labo.net/<topic>`:

- **`/json`** — un objeto JSON por línea, conexión abierta indefinidamente (`curl -s https://ntfy.404labo.net/homelab-alerts/json`). La forma recomendada para casi cualquier lenguaje (Python, Go, PHP...).
- **`/sse`** — Server-Sent Events, pensado para `EventSource` en JavaScript (`new EventSource("https://ntfy.404labo.net/homelab-alerts/sse")`).
- **`/raw`** — una línea de texto plano por mensaje, solo el cuerpo (sin título/prioridad/tags) — para scripts muy simples.
- **`/ws`** — WebSocket (`wss://ntfy.404labo.net/homelab-alerts/ws`), igual de soportado que los anteriores, útil si el consumidor ya habla WebSocket de forma nativa.

Con auth, si el topic no es de lectura pública, la cabecera de siempre (`Authorization: Bearer <token>`) — o, para clientes que no pueden fijar cabeceras (como `EventSource` en el navegador), el parámetro `?auth=<credencial en base64, igual que Basic Auth>` en la propia URL.

En vez de mantener la conexión abierta, un consumidor que solo se ejecuta de vez en cuando (un cron, una Lambda) puede hacer **polling puntual** con `?poll=1&since=<marca>`:

```bash
# Todo lo publicado en los últimos 10 minutos, sin abrir un stream
curl -s "https://ntfy.404labo.net/homelab-alerts/json?poll=1&since=10m"

# Desde el último mensaje visto (guardando su "id" entre ejecuciones)
curl -s "https://ntfy.404labo.net/homelab-alerts/json?poll=1&since=<ultimo-id-visto>"
```

## App móvil (Android/iOS) y navegador — puesta en marcha básica

1. Instalar la app oficial [ntfy](https://ntfy.sh/docs/subscribe/phone/) (Play Store / App Store / F-Droid).
2. En **Settings → Default server**, apuntar a `https://ntfy.404labo.net` (solo alcanzable en la LAN o vía Tailscale, `docs/18-tailscale.md`).
3. Suscribirse al topic (p. ej. `homelab-alerts`), con el usuario/token creado arriba si el topic no es de lectura pública.
4. **Entrega en segundo plano, por defecto**: esta instancia es 100 % autoalojada sin Firebase configurado, así que Android usa su mecanismo de respaldo — una conexión persistente propia (activable en **Settings → "Instant delivery"** dentro de la app), no el push nativo del sistema operativo. Con eso activo la entrega es prácticamente instantánea, a costa de algo más de batería; sin activarlo, la app solo actualiza al abrirla o cada cierto tiempo. Para las alertas de este clúster (undervoltage, SAI, actualizaciones pendientes) es un compromiso razonable — la sección siguiente explica cómo conseguir push nativo de verdad si hace falta.
5. La web app (`https://ntfy.404labo.net` en un navegador) sirve exactamente para lo mismo, sin instalar nada.

## Push nativo de verdad — Firebase (Android), relé para iOS, y Web Push (navegador)

**No implementado todavía en este clúster** — la entrega actual (servicio en primer plano de la app / pestaña de navegador abierta) funciona bien para el volumen y la urgencia de las alertas de hoy. Esta sección documenta las tres formas reales de conseguir push nativo, verificadas contra el código y la documentación oficial de ntfy (no solo la guía superficial), para cuando se quiera dar el paso. **Son tres mecanismos independientes** — cada plataforma necesita el suyo, no hay un interruptor único de "activar push".

### Android — Firebase Cloud Messaging (FCM)

Esto es lo que la mayoría de gente entiende por "configurar Firebase para push", y es real, pero con una limitación importante que no siempre se explica bien: **la app oficial de Play Store/F-Droid trae su propio proyecto Firebase de ntfy.sh integrado en el APK — no se le puede decir "usa este otro servidor Y este otro Firebase" solo tocando la configuración del servidor**. Para que un self-hosted use Firebase de verdad con Android hace falta **compilar tu propia APK** con tu propio proyecto Firebase incrustado. La documentación oficial de ntfy lo dice explícitamente: *"Using Firebase is optional and only works if you modify and build your own Android .apk. For a self-hosted instance, it's easier to just not bother with FCM."*

Aun así, aquí están los pasos completos por si se decide asumir ese esfuerzo:

1. Crear una cuenta/proyecto en [Firebase Console](https://console.firebase.google.com/).
2. Dentro del proyecto, crear una app y descargar la clave de cuenta de servicio (`Configuración del proyecto → Cuentas de servicio → Generar nueva clave privada`) — un fichero JSON tipo `homelab-ntfy-firebase-adminsdk-xxxxx.json`.
3. **Lado servidor**: copiar ese JSON a un volumen del contenedor `ntfy` (p. ej. `/var/lib/ntfy/firebase.json`, montado además del volumen de datos ya existente) y añadir al `docker-compose.yml` del stack: `NTFY_FIREBASE_KEY_FILE: /var/lib/ntfy/firebase.json`. Redeploy del stack para que lo recoja.
4. **Lado app — el paso pesado**: compilar una APK propia a partir del código fuente ([github.com/binwiederhier/ntfy-android](https://github.com/binwiederhier/ntfy-android)), sustituyendo su `google-services.json` por el del proyecto Firebase propio (obtenido al registrar una app Android en la Consola de Firebase), firmarla con una clave propia, e instalarla manualmente en cada móvil (no puede convivir con la app de Play Store, que apunta al Firebase de ntfy.sh) — y mantenerla actualizada a mano en cada nueva versión de ntfy.
5. Requiere Android Studio/toolchain de compilación Android — fuera del alcance de lo que este repo automatiza hoy.

**Coste real**: alto para el beneficio (batería ahorrada) frente a la entrega instantánea por defecto, que ya funciona bien. Por eso el propio proyecto lo desaconseja para self-hosted, y por eso este clúster no lo tiene activado.

### iOS — relé de sondeo (`upstream-base-url`), sin proyecto Firebase propio

Distinto problema, distinta solución. iOS no permite que una app mantenga una conexión en segundo plano indefinidamente (a diferencia de Android) — sin ayuda externa, las notificaciones en el self-hosted pueden tardar horas en llegar. La solución oficial **no requiere una cuenta de Firebase propia**: el servidor autoalojado reenvía un aviso mínimo (el ID del mensaje y un hash del topic — **nunca el contenido real**) al servidor público `ntfy.sh`, que lo empuja por su propio Firebase/APNs para "despertar" la app en el móvil; la app entonces se conecta directamente a nuestro servidor para traer el mensaje de verdad.

Un único ajuste en el servidor, sin tocar la app:

```yaml
# En docker-swarm/stacks/ntfy/docker-compose.yml, environment:
NTFY_UPSTREAM_BASE_URL: https://ntfy.sh
# NTFY_UPSTREAM_ACCESS_TOKEN solo hace falta si ntfy.sh empieza a limitar
# por rate-limit las peticiones de este servidor (poco probable con el
# volumen de este clúster).
```

Confirmado leyendo el código real del servidor (`server/config.go`, no solo la documentación): **el valor por defecto de `upstream-base-url` es vacío** — es decir, esta instancia hoy NO reenvía ningún aviso a `ntfy.sh`, por eso el push de iOS no es instantáneo ahora mismo (puede tardar hasta un par de horas según el estado del teléfono). Activarlo es la mejora de menor esfuerzo de las tres — una sola variable de entorno y un redeploy — y no expone el contenido de las notificaciones a `ntfy.sh`, solo un identificador opaco.

### Navegador / PWA — Web Push (VAPID), tampoco es Firebase ni necesita Google

Un tercer mecanismo, el más autocontenido de los tres — es el estándar [Web Push API](https://developer.mozilla.org/en-US/docs/Web/API/Push_API) (RFC 8030) que usan Chrome/Edge/Firefox/Safari de forma nativa. No hace falta cuenta de Google ni de Apple: se generan un par de claves propias (VAPID) y el propio ntfy hace de servidor push.

```bash
# Generar el par de claves (una sola vez, dentro del contenedor ntfy)
docker exec -it $(docker ps -q -f name=ntfy_ntfy) ntfy webpush keys
```

Y en el `docker-compose.yml` del stack:

```yaml
environment:
  NTFY_WEB_PUSH_PUBLIC_KEY: "<clave pública generada>"
  NTFY_WEB_PUSH_PRIVATE_KEY: "<clave privada generada>"
  NTFY_WEB_PUSH_FILE: /var/lib/ntfy/webpush.db
  NTFY_WEB_PUSH_EMAIL_ADDRESS: "admin@404labo.net"
```

Requisitos ya cumplidos por este clúster: certificado HTTPS válido (Let's Encrypt real vía Traefik — Web Push exige un certificado de confianza, no autofirmado) y un volumen persistente para `webpush.db` (el mismo `/srv/homelab/ntfy/data` ya montado). Una vez activo, cualquier usuario puede encender "background notifications" desde **Ajustes** en la propia web app — sin instalar nada, funciona igual en el navegador de escritorio y en la PWA instalada en el móvil (salvo iOS con Safari < 16.4).

**De los tres, este es el que más relación coste/beneficio tiene para este clúster** — cero dependencias externas, cero compilación, y cubre a cualquiera que use la web app o la PWA sin necesitar la app nativa de ningún sistema operativo.

### Resumen — qué activar según el caso

| Plataforma | Mecanismo | Esfuerzo | Dependencia externa |
|---|---|---|---|
| Android | Entrega instantánea (ya activo) | Ninguno | Ninguna |
| Android | Firebase (FCM) | Alto — compilar y mantener una APK propia | Cuenta de Firebase propia |
| iOS | Relé de sondeo (`upstream-base-url`) | Bajo — una variable de entorno | `ntfy.sh` (solo metadatos, no contenido) |
| Navegador / PWA | Web Push (VAPID) | Medio — generar claves + variables | Ninguna |

## Conectado como contact point de Grafana (undervoltage + SAI)

Desplegado y **verificado end-to-end en vivo** (2026-09-01, botón "Test" de Grafana + suscripción real al topic con la app web de ntfy — no solo revisión de logs):

- `pi-obs/config/grafana/alerting/ntfy-contactpoint.yml` — contact point `ntfy-cluster-alerts`, tipo `webhook`, apunta directo a `https://ntfy.404labo.net/homelab-alerts` (topic en la ruta). Auth vía `authorization_scheme: Bearer` + `authorization_credentials` (**no** `username`/`password` — ver el gotcha real más abajo).
- `pi-obs/config/grafana/alerting/notification-policies.yml` — árbol de políticas completo (la provisión por fichero sustituye el árbol entero, no añade una rama): la raíz se deja en el receiver por defecto de Grafana (sin SMTP configurado, no llega a ningún sitio — igual que antes de esta mejora) y se añade una ruta hija que envía a `ntfy-cluster-alerts` todo lo que tenga la label `category` en `power|hardware|disk` — las alertas de `undervoltage.yml`, `sai-bateria.yml` (`docs/33-nut-sai.md`) y `disk-space.yml` (mejora 3, cerrada el mismo día, `docs/14-monitorizacion-completa-cluster.md`).

**Gotcha real encontrado con el botón "Test" de Grafana**: la primera versión de `ntfy-contactpoint.yml` usaba `username`/`password` (HTTP Basic Auth) con el token de ntfy como contraseña — Grafana lo aceptó sin quejarse al provisionar, pero al probarlo de verdad dio `401 Unauthorized` (confirmado también reproduciéndolo con `curl -u usuario:token`). Los tokens de ntfy (`tk_...`) **solo** funcionan como `Authorization: Bearer <token>`, no como contraseña de Basic Auth. Grafana 10.4.2 sí trae un campo dedicado para esto — "Authorization Header - Scheme"/"-Credentials" (`authorization_scheme`/`authorization_credentials` en el YAML) — confirmado en la UI real y en el código fuente del notifier (`github.com/grafana/alerting`, campos disponibles desde la 9.1, muy por debajo de esta versión). Tras el cambio, "Test" respondió "Test alert sent." y el mensaje llegó de verdad a la app.

**Limitación real, verificada contra la documentación de ambos proyectos y confirmada con el propio "Test"** (no asumida): el "publish as JSON" de ntfy (que extraería `title`/`message`/`priority` limpios de un body JSON) solo funciona posteando al endpoint **raíz** de ntfy con un campo `"topic"` dentro del propio JSON (`docs.ntfy.sh/publish/#publish-as-json`) — postear directamente a `/homelab-alerts` con `Content-Type: application/json`, que es lo que hace el webhook nativo de Grafana, NO activa ese parseo. El webhook de Grafana 10.4.2 sí tiene campos `title`/`message` propios (confirmado en la UI, disponibles desde la 9.3) pero no cambian nada aquí — solo rellenan el JSON que Grafana genera, y ntfy ignora igualmente ese JSON al no postear a la raíz; "Custom Payload" (que sí lo arreglaría de raíz) **confirmado que no existe en esta versión** (revisada la UI real campo a campo, es de la 12.0). Consecuencia práctica, confirmada con la notificación real recibida: **el mensaje contiene el JSON crudo de Grafana como texto** — funcional y con toda la información dentro (incluido un `"title"`/`"message"` ya bien formados, solo que como texto dentro del JSON, no como los campos nativos de la notificación) — pero no tan legible como cabría. Si esto resulta molesto en el uso real, la forma limpia de arreglarlo sin depender de una versión concreta de Grafana es un pequeño workflow de traducción en n8n-main (webhook de Grafana → nodo Function extrayendo `title`/`message` → HTTP Request a ntfy con esos valores como cabeceras `Title`/`Message`, igual que los ejemplos de curl de más abajo) — ver "Pendiente / ideas futuras".

**Redeploy desde cero** (si se recrea el stack de `ntfy` o el usuario `grafana` alguna vez): la versión en git de `ntfy-contactpoint.yml` lleva el placeholder `CHANGE_ME_NTFY_TOKEN` — sustituirlo por un token real (`ntfy token add grafana`, sección anterior) SOLO en la copia desplegada (`/srv/homelab/pi-obs/config/grafana/alerting/ntfy-contactpoint.yml`, nunca en git) y `docker service update --force pi-obs_grafana` para que recargue la provisión.

## Publicar notificaciones — protocolo HTTP genérico

Es solo HTTP — no hace falta ningún SDK. Con el token del usuario correspondiente (creado arriba), como cabecera `Authorization: Bearer <token>` — **no** como contraseña de HTTP Basic Auth, eso da `401` de verdad (gotcha real encontrado configurando el contact point de Grafana, ver la sección anterior):

```bash
# Forma simple -- el body es el mensaje, tal cual
curl -H "Authorization: Bearer tk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
     -d "El backup nocturno de postgres-main ha terminado sin errores" \
     https://ntfy.404labo.net/homelab-alerts

# Con título, prioridad y tags (emoji) -- cabeceras, no en el body
curl -H "Authorization: Bearer tk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx" \
     -H "Title: Backup completado" \
     -H "Priority: default" \
     -H "Tags: white_check_mark" \
     -d "postgres-main volcado y comprimido correctamente (retaco)" \
     https://ntfy.404labo.net/homelab-alerts

# Prioridades válidas: min, low, default, high, urgent (urgent hace sonar
# la alerta incluso en "no molestar" en la app, úsese con criterio)
```

`Click` (URL a abrir al tocar la notificación — por ejemplo, el propio dashboard de Grafana), `Actions` (botones), y adjuntar un fichero (`-T archivo.png`) también están soportados — ver [docs.ntfy.sh/publish](https://docs.ntfy.sh/publish/) para el catálogo completo de cabeceras.

## Uso desde Python

Sin cliente oficial en PyPI — no hace falta, es una petición HTTP normal con `requests` (ya una dependencia habitual en cualquiera de los microservicios FastAPI del clúster, `services/`):

```python
import requests

NTFY_URL = "https://ntfy.404labo.net/homelab-alerts"
NTFY_TOKEN = "tk_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # nunca hardcodeado -- desde Infisical/env, ver abajo


def notify(message: str, title: str | None = None, priority: str = "default", tags: list[str] | None = None) -> None:
    headers = {"Authorization": f"Bearer {NTFY_TOKEN}"}
    if title:
        headers["Title"] = title
    if priority:
        headers["Priority"] = priority
    if tags:
        headers["Tags"] = ",".join(tags)

    response = requests.post(NTFY_URL, data=message.encode("utf-8"), headers=headers, timeout=10)
    response.raise_for_status()


if __name__ == "__main__":
    notify(
        "El workflow de n8n 'sync-nas' ha fallado en el tercer reintento",
        title="n8n-main — workflow fallido",
        priority="high",
        tags=["warning"],
    )
```

Puntos a tener en cuenta al integrarlo en un servicio real del clúster (n8n vía nodo HTTP Request, uno de los microservicios FastAPI, un script de `shared/scripts/`...):

- **El token nunca en el código** — mismo criterio que el resto del repo: variable de entorno, `.env` local (gitignored) o, si el consumidor ya usa Infisical (la mayoría de stacks Swarm), un secreto más en el mismo proyecto (`services/apikey-service/`, por ejemplo, ya sigue este patrón para sus propias credenciales).
- **Timeout explícito** (`timeout=10` arriba) — ntfy normalmente responde en milisegundos, pero un servicio que dispara notificaciones desde un flujo síncrono no debería poder colgarse indefinidamente si ntfy está caído.
- **No lanzar la excepción hacia arriba sin más** si la notificación es secundaria al flujo principal (p. ej. un backup que ya ha terminado bien) — capturar `requests.RequestException` y solo loguear con `loguru` (`docs/desarrollo-microservicios-python.md`, sección 7), para que un ntfy caído no tumbe el proceso que solo quería avisar.
- **Suscribirse también es HTTP** (`GET https://ntfy.404labo.net/homelab-alerts/json`, streaming NDJSON — una línea JSON por mensaje) si algún día un consumidor Python necesita reaccionar a notificaciones en vez de solo emitirlas; no hay caso de uso real para esto todavía en el clúster.

## Uso desde n8n

Nodo **HTTP Request** genérico (no hay nodo nativo de ntfy) — método `POST`, URL `https://ntfy.404labo.net/<topic>`, header `Authorization: Bearer <token>`, body el mensaje en texto plano (o cabeceras `Title`/`Priority`/`Tags` igual que en los ejemplos de curl). Encaja con el resto de automatizaciones ya construidas en n8n-main/n8n-aux (`docs/22-mejoras-futuras.md`, varias mejoras que mencionan n8n) sin necesitar ninguna credencial nueva más allá de un header estático.

## Operación

- **Backup**: sin script dedicado todavía — `cache.db` solo guarda 12h de historial (no hay nada crítico que perder, las notificaciones ya se han entregado), y `auth.db` (usuarios/tokens) es pequeño y de baja frecuencia de cambio. Si en el futuro se gestionan muchos usuarios/tokens a mano, un volcado puntual de `/srv/homelab/ntfy/data/auth.db` basta — mismo criterio que se aplicó a Vaultwarden antes de tener backup automático (`docs/31-docker-swarm.md`).
- **Logs**: como el resto de stacks Swarm, vía driver `loki` — `docker service logs ntfy_ntfy` no muestra nada (limitación conocida del driver, ver `CLAUDE.md`), consultar Loki directamente (`grafana.404labo.net`, datasource Loki, `{service_name="ntfy_ntfy"}` o el label que aplique).
- **Auto-actualización**: sin la label de watchtower a propósito, mismo criterio que el resto de servicios con estado del clúster (`CLAUDE.md`, sección de watchtower) — actualizar la imagen (`binwiederhier/ntfy:vX.Y.Z`) es un cambio deliberado, no automático.
- **`check-image-updates.sh` (mejora 4, punto 5, opcional)**: si se exporta `NTFY_TOKEN` (token de un usuario con permiso de escritura en `homelab-alerts`) antes de ejecutar `shared/scripts/check-image-updates.sh`, el script publica además un aviso por ntfy cuando detecta contenedores con imagen desactualizada — sin el token, se comporta exactamente igual que antes (solo métricas Prometheus).

## Pendiente / ideas futuras

- **Relé por n8n para un título/mensaje limpios en las notificaciones de Grafana** (ver la limitación descrita en "Conectado como contact point de Grafana") — workflow pequeño en n8n-main: webhook que recibe el POST de Grafana, extrae `title`/`message` del JSON y republica a ntfy vía cabeceras. No implementado todavía porque el JSON crudo, aunque poco legible, sí llega y contiene toda la información — se deja como mejora de calidad, no de funcionalidad.
- ~~Alerta de espacio en disco (mejora 3)~~ — hecho (2026-09-01), `pi-obs/config/grafana/alerting/disk-space.yml`, `category=disk`, ya enrutada por el mismo contact point.
- Integrar el coste de Bifrost (mejora 22) mencionaba explícitamente "en cuanto exista ntfy" como contact point alternativo/complementario al de Grafana — sigue siendo una decisión pendiente de esa mejora, no de esta.
- Push nativo (Firebase/Android, relé de sondeo/iOS, Web Push/navegador) — documentado en detalle en "Push nativo de verdad" más arriba, ninguno de los tres activado todavía. El de menor esfuerzo y sin dependencia externa real es Web Push (navegador/PWA); el relé de iOS (`upstream-base-url`) es el siguiente más barato si el retraso actual en iOS molesta en el uso real.
