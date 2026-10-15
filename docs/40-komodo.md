# 40 — Komodo: visibilidad del clúster y API para operar los nodos

Komodo (`komo.do`) da una UI y una API para **ver el estado del clúster** (servidores, contenedores, stacks y servicios de Swarm) y **operarlo** (desplegar, parar, reiniciar) desde scripts, n8n, Capataz o Forgejo Actions, sin SSH ni `docker stack deploy` a mano. Mejora 53 de `docs/22-mejoras-futuras.md` (completada el 2026-10-15; instalada el 2026-10-14; el documento numerado es el 40 porque el 39 ya es el de `miugarita`).

**No sustituye** a Portainer ni a Capataz, ni es una reconsideración de "Docker Swarm, no Kubernetes": convive con ellos.

## Arquitectura

```
navegador / scripts ──► Traefik ──► komodo_core (UI + API, :9120)
                                         │  mongodb://  (authMechanism=PLAIN)
                                         ▼
                                  komodo_ferretdb 1.24.2 ──► postgres-main (retaco)
                                         ▲                    base `komodo`, rol `komodo`
komodo_core ── https://periphery:8120 ──►  komodo-periphery_periphery (retaco, docker.sock)
```

| Pieza | Dónde | Notas |
|---|---|---|
| `komodo_core` | stack `komodo`, sin `constraints` (flota entre nodos) | API + UI en `https://komodo.404labo.net`. Claves de Core en un volumen NFS (`/volume1/nfs-data/komodo/config`) |
| `komodo_ferretdb` | stack `komodo` | Traduce el protocolo de MongoDB a SQL. **v1.24.2** (ver "Por qué FerretDB 1.x") |
| Base de datos | `postgres-main`, base `komodo`, rol `komodo` (no superusuario) | Sin MongoDB, sin cambiar la imagen de `postgres-main`, sin extensiones |
| `komodo-periphery_periphery` | stack `komodo-periphery`, `mode: global`, `node.role == manager` | Agente con `docker.sock`. Hoy solo `retaco` es manager real, así que una réplica |

Stacks: `docker-swarm/stacks/komodo/` y `docker-swarm/stacks/komodo-periphery/`. Se despliegan **siempre a mano** (`docker stack deploy`), nunca desde el propio Komodo; lo mismo vale para `postgres-main`.

## Por qué FerretDB 1.x y no la v2

Komodo solo habla MongoDB. FerretDB **v2** guarda los datos con la extensión DocumentDB, que solo existe para Debian/glibc, no para el Alpine de `postgres-main`: hubiera exigido migrar la base compartida de todo el clúster (o montar un Postgres aparte). FerretDB **1.x** funciona sobre un PostgreSQL corriente. En el ensayo del 2026-10-14 (aislado, en `ryzen`) Komodo 2.3.3 funcionó entero sobre FerretDB 1.24.2 y `postgres:16-alpine` (PostgreSQL 16.15, musl): login, API, persistencia (24 tablas), y un Periphery real con sus contenedores. La alternativa con DocumentDB también se probó (restauración de `pg_dumpall` con 726 tablas y 371.167 filas idénticas, `--locale=C.UTF-8`) y queda anotada en la mejora 53 por si hiciera falta.

**Lo que se acepta**: FerretDB 1.x está en mantenimiento (la 1.24.2 es la última de la serie). Si una versión futura de Komodo exigiera funciones que solo da la v2, habrá que revisar esto. Versiones fijadas (`ferretdb:1.24.2`, `komodo-core:2.3.3`), nunca `latest`.

## Secretos

Swarm secrets externos (los mismos valores, en Infisical, proyecto "Homelab Cluster", carpeta `/komodo/`):

| Swarm secret | Infisical | Para qué |
|---|---|---|
| `komodo-database-uri-v1` | `KOMODO_DB_PASSWORD` (solo la contraseña) | URI de Mongo hacia FerretDB; lleva la contraseña del rol `komodo` |
| `komodo-passkey-v1` | `KOMODO_PASSKEY` | Clave compartida Core ↔ Periphery |
| `komodo-jwt-secret-v1` | `KOMODO_JWT_SECRET` | Firma de sesiones |
| `komodo-webhook-secret-v1` | `KOMODO_WEBHOOK_SECRET` | Webhooks |
| `komodo-admin-password-v1` | `KOMODO_ADMIN_PASSWORD` | Contraseña del admin inicial |
| — | `KOMODO_API_KEY_ESTADO_RO` / `KOMODO_API_SECRET_ESTADO_RO` | API key de la cuenta de servicio de solo lectura |

FerretDB 1.x **no necesita ningún secreto**: las credenciales las aporta el cliente Mongo (`authMechanism=PLAIN`) y se reenvían a Postgres. Core lee sus secretos con las variables `*_FILE` (`KOMODO_DATABASE_URI_FILE`, `KOMODO_PASSKEY_FILE`, `KOMODO_JWT_SECRET_FILE`, `KOMODO_WEBHOOK_SECRET_FILE`, `KOMODO_INIT_ADMIN_PASSWORD_FILE`), todas verificadas.

Para iniciar sesión en la UI (usuario `admin`):

```bash
infisical secrets get KOMODO_ADMIN_PASSWORD --plain --projectId=ca5af978-b62d-471a-b922-8dc545cd80c6 --env=prod --path=/komodo
```

Cambiar un secreto exige un `-vN+1` (los secretos de Swarm son inmutables) y redesplegar el stack, como el resto del clúster.

## Acceso y seguridad

- Solo en la LAN/Tailscale (`*.404labo.net`). No hay altas locales (`KOMODO_DISABLE_LOCAL_USER_REGISTRATION`): las personas entran por **OIDC con Authentik** (sección siguiente). El admin local (`admin`) es la cuenta de emergencia.
- El router de Traefik **no lleva `apikey-auth`**: Komodo usa la cabecera `X-Api-Key` para su propia API y ese middleware rechazaría todas las llamadas.
- Periphery monta `docker.sock` (control total del host, como `portainer-agent`) y no publica ningún puerto en la LAN (Core llega por el overlay `komodo_komodo-net`). Los terminales de Periphery están deshabilitados.
- **La API con permisos de ejecución equivale a control remoto de todos los nodos.** Usar siempre cuentas de servicio con permisos mínimos y nunca la del admin en scripts.

## Usar la API

Autenticación con cabeceras `X-Api-Key` y `X-Api-Secret` (se crean para una cuenta de servicio en la UI o con `CreateApiKeyForServiceUser`). Peticiones tipo RPC: `POST /read`, `/write`, `/execute`, con cuerpo `{"type": "<Petición>", "params": {...}}`.

```bash
K=$(infisical secrets get KOMODO_API_KEY_ESTADO_RO    --plain --projectId=ca5af978-b62d-471a-b922-8dc545cd80c6 --env=prod --path=/komodo)
S=$(infisical secrets get KOMODO_API_SECRET_ESTADO_RO --plain --projectId=ca5af978-b62d-471a-b922-8dc545cd80c6 --env=prod --path=/komodo)
curl -s -X POST https://komodo.404labo.net/read -H "X-Api-Key: $K" -H "X-Api-Secret: $S" \
  -H 'content-type: application/json' -d '{"type":"ListServers","params":{}}'
```

Peticiones validadas: `GetVersion`, `ListServers`, `ListSwarms`, `ListDockerContainers {server}`, `ListSwarmNodes`/`ListSwarmServices {swarm}`, `CreateServer`, `CreateSwarm`, `CreateServiceUser`, `CreateApiKeyForServiceUser`, `UpdatePermissionOnResourceType`, `GetUpdate`.

⚠️ **Las operaciones `/execute` son asíncronas y devuelven siempre 200.** La respuesta es el objeto *Update* recién encolado (con `success: true` aunque aún no se haya hecho nada o aunque vaya a fallar). El resultado real —`success`, `logs`, y los errores de permisos— hay que leerlo con `GetUpdate {id}`. Probado: una cuenta de solo lectura que lanza `StopContainer` recibe 200, y el Update posterior dice `User does not have required permissions on this Server. Must have at least Execute`. No dar por buena una operación mirando solo el código HTTP.

### Cuenta de servicio de solo lectura (`estado-ro`)

Creada con `CreateServiceUser` y permiso `Read` por tipo de recurso (`UpdatePermissionOnResourceType`) sobre `Server`, `Swarm`, `Stack` y `Deployment`. Verificado: puede listar servidores y el Swarm; `CreateServer` da 403; `StopContainer` queda denegado. Para una acción concreta (reiniciar un servicio, desplegar un stack) crear **otra** cuenta con `Execute` solo sobre ese recurso, y guardar su clave en `/komodo/`.

## Estado y qué falta

| Fase | Estado |
|---|---|
| 0 Ensayo aislado | ✅ 2026-10-14 |
| 1 Migrar `postgres-main` | ❎ descartada (FerretDB 1.x no la necesita) |
| 2 FerretDB + Core | ✅ |
| 3 Periphery en los managers | ✅ (solo `retaco`, único manager) |
| 4 Más servidores (`pinchi`, `miugarita`, `ryzen`, `pi-dns`) | ✅ 2026-10-14, modo saliente a través de Traefik (ver más abajo) |
| 5 API | ✅ cuenta de solo lectura; falta una de ejecución cuando haya un caso de uso |
| 6 Integraciones | ✅ 2026-10-15: OIDC con Authentik y alerter a ntfy (el conector de Komodo en Capataz queda opcional) |
| 7 GitOps con Forgejo | ➖ fuera del alcance de la mejora 53 (opcional) |

## Cómo entrar al panel y con qué usuarios

**URL**: `https://komodo.404labo.net` (hace falta resolver `*.404labo.net`: estar en la LAN o por Tailscale).

| Quién | Cómo entra | Dónde está la credencial |
|---|---|---|
| **Personas** (lo normal) | Botón **Oidc** de la pantalla de acceso → login de Authentik. Solo pasa quien esté en el grupo `authentik Admins` de Authentik | Su cuenta de Authentik (ya en Vaultwarden si la tienen guardada) |
| **`admin` local** (emergencia: Authentik caído o mal configurado) | Usuario y contraseña en la propia pantalla de acceso | Infisical, proyecto "Homelab Cluster", `/komodo/`, secreto `KOMODO_ADMIN_PASSWORD`. **Guardarla en Vaultwarden** |
| **`estado-ro`** (cuenta de servicio, solo lectura, para scripts) | Solo API: cabeceras `X-Api-Key`/`X-Api-Secret` | Infisical `/komodo/` (`KOMODO_API_KEY_ESTADO_RO`, `KOMODO_API_SECRET_ESTADO_RO`) |

**No hay que crear usuarios a mano**: los usuarios de OIDC se dan de alta solos la primera vez que inician sesión, con el **nombre de usuario de Authentik** (`akadmin`, no el email). Nacen **habilitados** (`KOMODO_ENABLE_NEW_USERS`, porque el control de acceso lo hace Authentik) pero **sin ser administradores y sin ver ningún recurso**: un usuario nuevo entra y el panel aparece vacío hasta que un administrador lo promueve. El primer usuario OIDC tampoco es administrador por ser el primero.

**Promover a un usuario OIDC a administrador** (procedimiento verificado el 2026-10-15 con `akadmin`), con la cuenta `admin` local:

```bash
# 1) listar usuarios y localizar el id del usuario OIDC
curl -s -X POST https://komodo.404labo.net/read -H "authorization: $JWT" -H 'content-type: application/json' \
  -d '{"type":"ListUsers","params":{}}'
# 2) promoverlo (la respuesta correcta es {})
curl -s -X POST https://komodo.404labo.net/write -H "authorization: $JWT" -H 'content-type: application/json' \
  -d '{"type":"UpdateUserAdmin","params":{"user_id":"<id>","admin":true}}'
```

`$JWT` sale de iniciar sesión con el `admin` local (`POST /auth/login`, `LoginLocalUser`). Un administrador ve y opera todos los recursos; **no** es `super_admin` (ese flag solo lo tiene el `admin` local y es el único que puede gestionar a otros administradores). Para dar acceso solo a *algunos* recursos a un usuario que no sea administrador hay que concederle permisos por recurso o por tipo (`UpdatePermissionOnResourceType`, como se hizo con `estado-ro`). El mismo cambio se puede hacer desde la interfaz, en la gestión de usuarios de la cuenta administradora, pero esa ruta no se ha verificado aquí.

## Autenticación con Authentik (OIDC)

Configurada el 2026-10-15. Komodo es un cliente OIDC **confidencial** de Authentik:

| Pieza | Valor |
|---|---|
| Proveedor y aplicación en Authentik | `Komodo` (proveedor OAuth2/OpenID) y aplicación `komodo`, lanzador `https://komodo.404labo.net` |
| Emisor (issuer) | `https://authentik.404labo.net/application/o/komodo/` (modo `per_provider`, firma RS256 con el certificado autofirmado de Authentik) |
| Redirección | `https://komodo.404labo.net/auth/oidc/callback` (estricta, una sola) |
| Flujos | autorización con consentimiento implícito (`default-provider-authorization-implicit-consent`) e invalidación por defecto |
| Scopes | `openid`, `email`, `profile` (y `offline_access`) |
| Tipos de concesión | **solo `authorization_code` y `refresh_token`** |
| Control de acceso | Binding de la aplicación al grupo **`authentik Admins`** (más grupos: añadir bindings en Authentik) |
| En Komodo | `KOMODO_OIDC_ENABLED`, `KOMODO_OIDC_PROVIDER`, `KOMODO_OIDC_CLIENT_ID` y `KOMODO_OIDC_CLIENT_SECRET_FILE` (docker secret `komodo-oidc-client-secret-v1`; copia en Infisical `/komodo/`: `KOMODO_OIDC_CLIENT_ID`/`KOMODO_OIDC_CLIENT_SECRET`) |

Cómo se creó (sin pasar por la interfaz de Authentik): con su propia shell dentro del contenedor, ver `docs/27-authentik-sso.md`, sección "Crear un proveedor OIDC por código". Se prefirió a la interfaz porque deja el procedimiento repetible y sin que el secreto del cliente pase por pantalla.

⚠️ **Gotchas reales encontrados**:
- **`Invalid grant_type for provider`** → el proveedor creado por código tiene `grant_types = []` y Authentik lo rechaza con `invalid_request: The request is otherwise malformed` **antes** de mostrar el login. Hay que asignarlos explícitamente (los proveedores creados desde la interfaz ya los traen). Lo diagnóstico está en el log de `authentik-server` (`authentik.providers.oauth2.views.authorize`).
- **Registro**: con `KOMODO_DISABLE_USER_REGISTRATION=true` Komodo solo deja entrar al **primer** usuario, también por OIDC. Hay que dejarlo en `false` y bloquear las altas locales con `KOMODO_DISABLE_LOCAL_USER_REGISTRATION=true`.
- El `local_auth` sigue activo a propósito: es la vía de emergencia si Authentik falla (y Authentik depende de `postgres-main`, igual que Komodo, así que no caen por separado).

## Alertas a ntfy

Alerter `ntfy-homelab` (endpoint Ntfy) hacia `https://ntfy.404labo.net/homelab-alerts`. Publica con un **usuario propio de ntfy** (`komodo`) con permiso `write-only` solo sobre ese topic, no con el de otra aplicación; su token está en Infisical (`/komodo/`, `KOMODO_NTFY_TOKEN`). ntfy admite la autenticación como parámetro `?auth=` (el valor de la cabecera `Authorization` en base64 URL-safe, sin relleno): así basta con una URL en la configuración del alerter. **La URL, con el token, queda guardada en la base de datos de Komodo**; al ser un token de solo escritura sobre un topic, es un riesgo aceptado.

Alertas activas: `SwarmUnhealthy`, `ServerUnreachable`, `ServerDisk`, `ServerMem`. **`ryzen` está excluido** (se apaga a propósito). No se han activado `ContainerStateChange` ni `ServerCpu` por ruido; añadirlos desde la UI si se quieren. Convive con las alertas de Grafana (mejora 42): conviene no duplicar la misma condición por los dos caminos.

## Servidores fuera de los managers (modo saliente)

`pinchi`, `miugarita`, `ryzen` y `pi-dns` aparecen en Komodo como servidores con su Periphery en modo **saliente**: el agente se conecta él a Core por `wss://komodo.404labo.net` (a través de Traefik) y no abre ningún puerto en la LAN. Un compose por nodo, en fichero aparte para no tocar el principal: `<nodo>/docker-compose.komodo-periphery.yml` (proyecto `komodo-periphery-<nodo>`; en `pi-dns` es un fichero separado a propósito, sin tocar Pi-hole ni Unbound).

Alta de un servidor nuevo (una sola vez):

1. Crear una clave de alta en Core con caducidad corta (`CreateOnboardingKey` con `expires` en milisegundos). Devuelve `private_key` **una sola vez**.
2. En el nodo, `/etc/komodo/keys` y un `.komodo-periphery.env` (modo 600) con `KOMODO_ONBOARDING_KEY=<la clave>`; `docker compose -f docker-compose.komodo-periphery.yml --env-file .komodo-periphery.env up -d`. El servidor se da de alta solo con el nombre de `PERIPHERY_CONNECT_AS`.
3. Cuando aparezca `Ok` en Komodo: borrar el `.env` y recrear (`up -d --force-recreate`). Desde entonces se autentica con su propio par de claves (persistido en `/etc/komodo/keys/periphery.key`, no hace falta la clave de alta). Borrar la clave de alta de Core (`DeleteOnboardingKey` con su `public_key`).

El agente solo acepta a este Core: `PERIPHERY_CORE_PUBLIC_KEYS` lleva su clave pública (`/mnt/nfs-data/komodo/config/keys/core.pub`, base64). **Si algún día se regenera la clave de Core, hay que actualizarla en los 4 compose.**

Estado a 2026-10-14: `retaco` (27 contenedores), `pinchi` (20), `miugarita` (30), `ryzen` (13) y `pi-dns` (9), todos `Ok`. `ryzen` se apaga habitualmente (`docs/19`): aparecerá offline cuando duerma, es lo esperado. Los workers del Swarm **no** se añaden al recurso Swarm `homelab` (agrupa managers); Komodo descubre sus nodos a través del manager.

## Operación

```bash
# Estado
docker service ls --filter label=com.docker.stack.namespace=komodo
# Redesplegar (desde retaco; los compose se copian a /tmp, ver CLAUDE.md)
docker stack deploy -c docker-compose.yml komodo --with-registry-auth
docker stack deploy -c docker-compose.yml komodo-periphery --with-registry-auth
# Logs de Core (el driver loki: consultar Loki si `docker service logs` sale vacío)
```

**Quitarlo**: `docker stack rm komodo-periphery komodo`, borrar los 5 `docker secret` `komodo-*-v1` y, si ya no se quiere la base, `DROP DATABASE komodo; DROP ROLE komodo;` en `postgres-main`. No afecta a ningún otro servicio.

## Lecciones

- **FerretDB 1.x no tiene shell** en la imagen: no se puede leer un secreto con un entrypoint; resulta que no hace falta (ver "Secretos").
- **`create-postgres-db.sh` imprime la contraseña**: para un servicio nuevo con secretos de Swarm se hizo el SQL equivalente por entrada estándar, sin pasar la contraseña por argumentos ni por pantalla.
- **`CREATE ROLE` + `CREATE DATABASE` en un único `psql -c`** hace rollback conjunto si el segundo falla (no pueden ir en la misma transacción); ejecutar cada sentencia por separado.
- **Alta saliente**: probado el ciclo completo en `pinchi` (alta, recrear sin clave de alta, reconexión) antes de repetirlo en los otros tres. Una clave de alta con `expires` y borrada de Core tras usarse no deja credenciales vivas.
- **En `pi-dns` Docker creó una red bridge nueva** (`komodo-periphery-pi-dns_default`, 172.18.0.0/16) para el contenedor del agente; no afecta a `pi-dns-net`, pero conviene saberlo antes de asignar rangos.
- **Authentik por código**: `ak shell` dentro del contenedor no funciona con un `docker exec` normal ("Secret key missing"): el secreto lo inyecta el wrapper de Infisical en el proceso principal. Hay que lanzar la shell heredando el entorno de ese proceso (ver `docs/27`).
- **`ntfy` con token**: el token no puede ser el de otra aplicación; un usuario y token por consumidor (`docs/34`). La contraseña del usuario se pasa por la variable `NTFY_PASSWORD`, no por argumento.
- **Core flota entre nodos**: no suponer que está en `retaco` (en la instalación quedó en `miugarita`); sus claves viven en NFS.
