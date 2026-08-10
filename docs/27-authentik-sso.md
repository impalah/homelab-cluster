# 27 — Authentik: SSO/authn para personas

## Qué es y por qué

Mejora 25 del backlog (`docs/22-mejoras-futuras.md`). `apikey-service` ya resuelve autenticación **máquina a máquina** (`X-Api-Key`, `docs/06-instalacion-pi1-dns.md`), pero no había nada equivalente para **personas** con sesión de navegador — cada panel de administración del clúster tenía su propia cuenta suelta, y `prometheus.home.arpa` no tenía ninguna autenticación en absoluto, ni propia ni de `apikey-service`. Authentik cubre ese hueco: identidad centralizada, con OIDC nativo donde la app lo soporte y *forward-auth* (vía nginx) donde no.

Alcance de esta implementación: desplegar Authentik en producción + protegerlo con Prometheus como piloto verificado (el hueco de seguridad real, sin ninguna auth hoy) — mismo patrón que Infisical/`apikey-service` en la mejora 16. Grafana/Portainer vía OIDC nativo, y evaluar SonarQube/Pi-hole, quedan como roadmap (ver "Pendiente" más abajo), no bloqueando esto.

## Decisiones de arquitectura

### Postgres compartido con `postgres-main` (no dedicado como Infisical)

A diferencia de Infisical (ADR 0002), Authentik usa la base multi-tenant `postgres-main` sin aislarla en una instancia propia. Motivo: Authentik solo gatea **login de personas**, no el arranque de ningún servicio máquina — un incidente de `postgres-main` por un motivo ajeno a Authentik deja sin SSO temporalmente, pero no tumba nada en cascada (a diferencia de Infisical, del que dependen los servicios ya migrados para arrancar). El radio de fallo es mucho menor aquí, así que compartir es defendible — mismo razonamiento que ya se documentó en el ADR 0002, aplicado al revés: la conclusión cambia porque la pregunta de fondo ("¿qué tan grave es que esto falle junto con `postgres-main`?") tiene una respuesta distinta para cada servicio.

Creada con el patrón habitual: `bash shared/scripts/create-postgres-db.sh postgres-main dbadmin authentik authentik`.

### Sin Redis/Valkey

Confirmado contra la documentación oficial vigente (versión de imagen `2026.5.6`): el `docker-compose.yml` de referencia oficial ya no incluye ningún servicio Redis, y la lista completa de variables `AUTHENTIK_*` no tiene ninguna relacionada con Redis — versiones recientes de Authentik lo quitaron como dependencia dura, la caché y las tareas de fondo van sobre Postgres (`django_dramatiq_postgres`, confirmado en los logs reales de `authentik-worker` en producción). No hizo falta tocar Valkey para esto en absoluto.

### Secretos vía Infisical desde el primer despliegue

Mismo mecanismo que `apikey-service` (`docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md`): binario del CLI montado por bind-mount, `entrypoint`/`command` sobreescritos con el wrapper de dos pasos (`infisical login --method=universal-auth` + `infisical run --token=...`). Secretos en la carpeta `/authentik/` del proyecto "Homelab Cluster": `AUTHENTIK_POSTGRESQL__PASSWORD` y `AUTHENTIK_SECRET_KEY` (`openssl rand -base64 60` — **nunca rotar sin plan de migración**, invalida todas las sesiones y datos cifrados existentes). Machine Identity `authentik`, Universal Auth, rol Viewer restringido a esa carpeta.

Entrypoint real de la imagen oficial (`ghcr.io/goauthentik/server:2026.5.6`), confirmado con `docker inspect`: `dumb-init -- ak`. El wrapper re-invoca `dumb-init` explícitamente al final del script (`exec dumb-init -- ak server` / `... ak worker`), no solo `ak`, para conservar el mismo manejo de señales/reaping de zombies que trae la imagen de fábrica.

### Sin `docker.sock`, outpost embebido

La imagen oficial monta `/var/run/docker.sock` en el `worker` por defecto, para el descubrimiento automático de Docker y el autodespliegue de outposts (`AUTHENTIK_OUTPOSTS__DISCOVER`). Aquí se desactiva (`AUTHENTIK_OUTPOSTS__DISCOVER: "false"`) y no se monta el socket — mismo criterio de superficie de riesgo ya aplicado a Floci/`open-terminal-mcp`/`portainer-agent` en este clúster: nada de acceso al Docker del host salvo que sea imprescindible.

En su lugar se usa el **outpost embebido**, el que trae el propio `authentik-server` — confirmado en producción (logs reales: peticiones con `user_agent: goauthentik.io/outpost/2026.5.6` contra la propia API del server, sin ningún contenedor de outpost aparte desplegado). El modo forward-auth apunta `/outpost.goauthentik.io` directo al `authentik-server`, sin necesidad de nada más.

**Nota de proceso**: el Proxy Provider creado para Prometheus no se asignó solo al outpost embebido en esta versión — hubo que entrar en Applications → Outposts → editar el "authentik Embedded Outpost" y añadirlo a mano a "Assigned applications". No dar por hecho la asignación automática en migraciones futuras, confirmarlo cada vez.

### `home.arpa` está en la Public Suffix List — nada de modo "domain-level"

Primer intento real (no lo que se planteó originalmente en el backlog): Proxy Provider en modo **"Forward auth (domain level)"**, con `Cookie domain=home.arpa`, pensado para compartir una sola sesión entre todos los servicios que se protejan así con Authentik en el futuro (Prometheus hoy, Grafana/Portainer/etc. más adelante).

**Falló en producción** — login correcto contra Authentik, pero el callback devolvía `HTTP ERROR 400`. Los logs de `authentik-server` lo dejaron claro: `"event":"mismatched session ID"` / `"event":"invalid state"`, con el campo `"should":""` (vacío) — es decir, la cookie de sesión que Authentik puso durante el `/start` nunca llegó de vuelta en la petición del `/callback`.

Motivo real, confirmado contra la [Public Suffix List](https://publicsuffix.org/list/public_suffix_list.dat) pública: `home.arpa` está **explícitamente incluido** en esa lista —

```
// arpa : https://www.iana.org/domains/root/db/arpa.html
arpa
...
home.arpa
...
```

— precisamente porque la RFC 8375 lo reserva como dominio de "homenet". La Public Suffix List es lo que usan todos los navegadores modernos para decidir qué "cuenta como un dominio propio" a efectos de cookies — exactamente el mismo mecanismo que impide que una web ponga una cookie con `Domain=com` o `Domain=co.uk`. Con `home.arpa` en esa lista, **ningún navegador acepta una cookie con `Domain=home.arpa`** — la descarta en silencio, sin ningún error visible ni en la consola ni en la respuesta HTTP, así que el síntoma es exactamente el que se vio: todo parece ir bien hasta el callback, que falla porque la sesión que debería estar en la cookie sencillamente no está.

**Arreglo real**: cambiar el Proxy Provider a modo **"Forward auth (single application)"**, con `External Host=https://prometheus.home.arpa` — la cookie de sesión queda entonces scoped a `prometheus.home.arpa`, un dominio real (no un sufijo de la PSL), y el navegador la acepta sin problema. Coste aceptado: cada servicio protegido así necesita su propio Provider y su propio login — sin sesión compartida entre servicios bajo `*.home.arpa`. Afecta a la mejora 29 (Grafana/Portainer): el modo "domain level" no es una opción viable para ningún servicio de este clúster mientras se use `*.home.arpa` como dominio interno — cada forward-auth futuro será "single application" también.

## Despliegue

Nodo: `retaco` — recursos reales medidos en vivo antes de decidir (9.5 GiB RAM disponible y 386 GB disco libre, frente a 3.8–6.4 GiB en las Raspberry Pi), y porque ya aloja `postgres-main`. `ryzen`/`mole` descartado (no siempre encendido).

Dos contenedores, misma imagen (`command: server` / `command: worker`, ambos envueltos por el wrapper de Infisical):

```yaml
authentik-server:
  image: ghcr.io/goauthentik/server:2026.5.6
  # ... entrypoint/command con el wrapper de Infisical, ver retaco/docker-compose.yml
  ports:
    - "9000:9000"   # HTTP interno — sin 9443, TLS lo termina nginx en pi-dns
authentik-worker:
  image: ghcr.io/goauthentik/server:2026.5.6
  # mismas variables, sin puerto publicado (proceso de fondo, no HTTP propio)
```

Publicado en `authentik.home.arpa` vía nginx (`pi-dns`), sin `apikey-auth.conf` — Authentik gestiona su propio login, mismo criterio que `infisical.home.arpa`/`bifrost.home.arpa`.

## Cómo se protegió `prometheus.home.arpa`

Procedimiento completo, para repetir con el siguiente servicio (mejora 29) — instrucciones manuales en la UI de Authentik primero, nginx después.

### 1. El Proxy Provider (UI de Authentik, `https://authentik.home.arpa/if/admin/`)

1. **Applications → Providers → Create**.
2. Tipo: **Proxy Provider**.
3. Nombre: `prometheus` (usar el nombre del servicio, en minúsculas, para que sea fácil identificar cuál es cuál cuando haya varios).
4. **Authorization flow**: dejar el que venga preseleccionado por defecto (normalmente `default-provider-authorization-implicit-consent`).
5. **Proxy Type**: **"Forward auth (single application)"** — **no** "domain level" (ver el porqué más arriba: `home.arpa` está en la Public Suffix List, ningún navegador acepta una cookie compartida bajo ese dominio).
6. **External Host**: `https://prometheus.home.arpa` — la URL pública real del servicio a proteger, con esquema incluido.
7. Dejar el resto de campos (validez del token, etc.) en su valor por defecto.
8. Guardar.

### 2. La Application

1. **Applications → Applications → Create**.
2. Nombre: `Prometheus`.
3. Slug: se autogenera (`prometheus`), dejarlo así.
4. **Provider**: seleccionar el `prometheus` creado en el paso anterior.
5. **Launch URL** (opcional): `https://prometheus.home.arpa` — para que aparezca como acceso directo en el panel de aplicaciones de Authentik.
6. Guardar.

### 3. Dar acceso a un usuario/grupo

Por defecto puede quedar sin ninguna restricción explícita o completamente cerrado según la versión — no dejarlo al azar:

1. Entrar en la Application recién creada → pestaña **Policy / Group / User Bindings**.
2. **Bind** → elegir el usuario (o el grupo `authentik Admins` para dar acceso a todos los administradores) → **Create**.

### 4. Asignar el Provider al outpost embebido

1. **Applications → Outposts**.
2. Confirmar que el Provider `prometheus` aparece ya asignado dentro de **"authentik Embedded Outpost"**. Si no aparece solo (pasó así en este despliegue — no dar por hecho la asignación automática): editar el outpost y añadirlo a mano en "Assigned applications".

### 5. El snippet de nginx

`pi-dns/config/nginx/authentik-auth.conf` (nuevo, mismo espíritu que `apikey-auth.conf` pero para forward-auth de personas en vez de `X-Api-Key` de máquinas) — define las locations internas `/outpost.goauthentik.io/auth/nginx` (la comprobación real, por IP directa al contenedor `authentik-server` en `retaco`, sin salto de vuelta por el propio nginx) y `@goauthentik_proxy_signin` (la redirección al login — **relativa**, sin esquema/host, a propósito: en modo single-application todo el flujo se queda en el dominio del propio servicio protegido, ver la sección de la Public Suffix List de arriba). Contenido completo, reutilizable tal cual para el siguiente servicio: `pi-dns/config/nginx/authentik-auth.conf`.

Uso en el `server{}` del servicio a proteger:

```nginx
server {
    listen 443 ssl;
    server_name prometheus.home.arpa;
    include /etc/nginx/authentik-auth.conf;
    location / {
        auth_request /outpost.goauthentik.io/auth/nginx;
        error_page 401 = @goauthentik_proxy_signin;
        proxy_pass http://192.168.1.171:9090;
        include /etc/nginx/proxy-common.conf;
    }
}
```

Despliegue paso a paso (nodo `pi-dns`):

```bash
# 1. El snippet es un fichero NUEVO — nginx monta cada fichero de config
#    individual, no el directorio entero. Añadir el bind-mount en
#    pi-dns/docker-compose.yml (una línea más, junto al de apikey-auth.conf)
#    ANTES de desplegar el fichero, o el include de nginx.conf fallará:
#      - /srv/homelab/pi-dns/nginx/conf/authentik-auth.conf:/etc/nginx/authentik-auth.conf:ro

# 2. Desplegar el fichero — patrón estándar del repo (/tmp + sudo cp, NUNCA
#    rsync/scp directo al destino final, ver docs/01-topologia.md):
rsync -av pi-dns/config/nginx/authentik-auth.conf u-dns@192.168.1.170:/tmp/authentik-auth.conf
ssh u-dns@192.168.1.170 "sudo cp /tmp/authentik-auth.conf /srv/homelab/pi-dns/nginx/conf/authentik-auth.conf && rm /tmp/authentik-auth.conf"

# 3. Desplegar nginx.conf con el bloque server{} actualizado, mismo patrón.

# 4. Como el bind-mount es NUEVO, "nginx -s reload" no basta — hay que
#    recrear el contenedor para que recoja el volumen:
ssh u-dns@192.168.1.170 "cd /srv/homelab/pi-dns && docker compose up -d nginx"

# 5. Validar antes de dar por bueno:
ssh u-dns@192.168.1.170 "docker compose exec nginx nginx -t"
```

**Gotcha real, encontrado al editar `authentik-auth.conf` una SEGUNDA vez** (para pasar de domain-level a single-application): incluso desplegando con el patrón correcto (`/tmp` + `sudo cp`, que en teoría reescribe el mismo inodo — ver `docs/01-topologia.md`), el contenedor `nginx` siguió sirviendo el contenido viejo tras el `nginx -s reload`. Confirmado con `docker exec nginx stat -c '%i' /etc/nginx/authentik-auth.conf` frente a `stat -c '%i'` del fichero en el host: **inodos distintos** (`128560` en el contenedor, `128592` en el host) — el bind-mount del contenedor ya no apuntaba al inodo que el host estaba reescribiendo, probablemente porque la primerísima vez que se creó este fichero se desplegó con un `rsync` directo al destino final (el error que el propio `docs/01-topologia.md` avisa evitar), dejando el mount de esa recreación del contenedor "enganchado" a un inodo que los `cp` posteriores ya no tocaban. Solución: `docker compose up -d --force-recreate nginx` — fuerza un bind-mount nuevo del fichero tal cual está en ese momento en el host, sin depender de qué inodo tuviera antes. Ante cualquier duda con un fichero bind-montado individual que "no coge" un cambio pese a haber usado `cp`, comparar inodos con `stat -c '%i'` antes de asumir que el problema está en otro sitio.

## Verificación end-to-end

- Sanity de servicios no tocados (`n8n.home.arpa`) sin cambios, antes y después de cada `nginx -s reload`/recreate.
- `https://prometheus.home.arpa` sin sesión → `302` a `https://prometheus.home.arpa/outpost.goauthentik.io/start?rd=...` — **mismo host**, no `authentik.home.arpa` (confirmado con `curl -D -`, no un 401 seco; ver la sección de la Public Suffix List sobre por qué es importante que el redirect se quede en el mismo dominio).
- Login real en navegador → llega hasta Prometheus tras el redirect, sesión ya autenticada.
- Logs de `authentik-server`/`authentik-worker`: migraciones completas sin error, sin errores de conexión a Postgres ni a Infisical.
- Reinicio de ambos contenedores (`docker compose restart authentik-server authentik-worker`) → recuperan solos, healthy, y el forward-auth de Prometheus sigue funcionando igual después.
- `retaco/.env`: cero líneas `AUTHENTIK_POSTGRESQL__PASSWORD=`/`AUTHENTIK_SECRET_KEY=` en claro — solo quedan las credenciales de la Machine Identity de Infisical.
- Repo local verificado en sync byte a byte con lo desplegado en `retaco`/`pi-dns`.

## Pendiente — roadmap

No incluido en esta ronda, a propósito (ver "Alcance" arriba):

1. **Grafana y Portainer vía OIDC nativo** — ambos lo traen de serie (Community Edition incluida), da identidad real dentro de la propia app (usuario, grupos, roles), preferible a forward-auth siempre que exista. Crear un OAuth2/OIDC Provider por app en Authentik, configurar el cliente en cada app. La limitación de la Public Suffix List (ver arriba) no afecta a OIDC nativo — cada app gestiona su propia sesión tras el login, no depende de una cookie compartida bajo `home.arpa`.
2. **Evaluar SonarQube y Pi-hole** — login propio ya débil/único en ambos, candidatos a forward-auth si se hace (mismo `authentik-auth.conf`, modo single-application obligatorio — ver la sección de la Public Suffix List), menor prioridad que Prometheus.
3. **n8n** — Community Edition no trae SSO propio (solo Enterprise), candidato a forward-auth si se hace.
4. Vaultwarden y `apikey-service` **no** se ponen detrás de Authentik — Vaultwarden tiene su propio modelo E2E (añadir SSO delante lo cambiaría sin necesidad real), `apikey-service` resuelve un problema distinto (máquinas, no personas).

## Backup

`authentik` es una base más dentro de `postgres-main`, ya cubierta por el bucle existente de `shared/scripts/backup-postgres.sh` sin cambios adicionales (a diferencia de Infisical, que sí necesitó un caso nuevo por tener instancia propia). `AUTHENTIK_SECRET_KEY` también a Vaultwarden, no solo a Infisical — perderla sin backup deja ilegibles todas las sesiones/datos cifrados existentes.
