# 23 — Bifrost: gateway LLM hacia AWS Bedrock y Ollama

## Qué es y por qué está aquí

[Bifrost](https://docs.getbifrost.ai/) es un gateway de LLM autoalojado (Maxim AI, Go): expone una única API OpenAI-compatible (`/v1/chat/completions`) hacia 20+ proveedores, incluido AWS Bedrock y Ollama. Es la pieza que le falta al clúster para poder usar modelos en la nube (Claude vía Bedrock) desde Open WebUI y n8n con la misma interfaz — y, tras añadir Ollama como provider más (ver más abajo), también es el único punto por el que Open WebUI habla con los modelos locales de `ryzen`, sin que cada cliente tenga que hablar directo con el SDK de AWS o gestionar credenciales/rutas de red distintas para cada backend.

Nace del punto 21 del backlog (`docs/22-mejoras-futuras.md`) — ver ahí la comparativa completa con LiteLLM (la alternativa evaluada, no desplegada) y el razonamiento de por qué se eligió Bifrost primero.

## Por qué `pi-sonar` y no `retaco`

El backlog original (mejora 21) proponía `retaco`, mismo criterio que el resto de servicios de datos. Se reconsideró en conversación antes de desplegar, por dos motivos concretos:

1. **RAM real disponible**: `pi-sonar` tenía 4.1 GiB disponibles y `pi-dns` 6.5 GiB (`free -h` en ambos, agosto 2026) — de sobra en cualquiera de los dos para un binario Go de decenas/pocos cientos de MB.
2. **Aislamiento de credenciales**: Bifrost guarda credenciales IAM de AWS. `pi-dns` es el nodo más expuesto del clúster (nginx, DNS de toda la LAN, subnet router de Tailscale) — meter ahí un servicio con credenciales cloud amplía innecesariamente el radio de impacto si algo le pasa al contenedor. `pi-sonar` solo aloja SonarQube (análisis de código, sin tráfico externo ni credenciales sensibles propias) — si Bifrost falla aquí, solo se cae la vía hacia Bedrock, no el acceso a todo el clúster.

`retaco` se descartó por estar ya más cargado (Postgres, n8n, Qdrant, registry, dos microservicios) sin necesidad real de meter un tercer tipo de carga ahí.

## Arquitectura

```mermaid
flowchart LR
    subgraph Clientes
        WEBUI["Open WebUI\n(ryzen)"]
        N8N["n8n-main\n(retaco)"]
    end

    subgraph pidns["pi-dns — 192.168.1.170"]
        NGINX["nginx :443\nbifrost.home.arpa"]
    end

    subgraph pisonar["pi-sonar — 192.168.1.172"]
        BF["bifrost :8080\nvirtual keys + governance"]
    end

    AWS["AWS Bedrock\n(eu-west-1)"]

    WEBUI -->|"Authorization: Bearer <virtual key>"| NGINX
    N8N -->|"Authorization: Bearer <virtual key>"| NGINX
    NGINX --> BF
    BF -->|"IAM: bedrock:InvokeModel*"| AWS
```

`bifrost.home.arpa` **no** pasa por `apikey-service` — Bifrost trae su propio sistema de autenticación (virtual keys / "governance"), exigido en origen (`client.enforce_auth_on_inference: true` en `config.json`). Añadir una segunda capa encima sería redundante, mismo criterio ya aplicado a `registry.home.arpa` y `apikey.home.arpa` — ver el comentario en `pi-dns/config/nginx/nginx.conf`.

## Permisos AWS — usuario base + rol asumido, permiso mínimo

**No existe ninguna policy gestionada de AWS suficientemente acotada** para este caso (`AmazonBedrockFullAccess` da acceso a gestión de modelos, *fine-tuning*, *provisioned throughput* — compromisos de coste por hora propios, no solo por uso —, guardrails, *knowledge bases*... muy por encima de lo que necesita un gateway de solo inferencia). Se descartó explícitamente en favor de una policy propia.

También se descartó dar credenciales estáticas de Bedrock directas a un usuario IAM único: en su lugar, un **usuario base sin permiso de Bedrock** solo puede asumir un **rol** que sí lo tiene. Si las credenciales del usuario base se filtran, quien las tenga solo puede asumir ese rol concreto (visible en CloudTrail como evento `AssumeRole`, revocable sin rotar ninguna credencial de Bedrock), no llamar a Bedrock directamente.

### 1. Policy de invocación (se adjunta al **rol**, no al usuario)

Cubre todos los proveedores de modelo de Bedrock (Titan, Llama, Mistral, Anthropic...), no solo Claude — con el mismo alcance de acciones mínimo (invocar + listar el catálogo, nada de gestión):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InvokeFoundationModels",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:*::foundation-model/*"
      ]
    },
    {
      "Sid": "InvokeInferenceProfiles",
      "Effect": "Allow",
      "Action": [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream"
      ],
      "Resource": [
        "arn:aws:bedrock:eu-west-1:<ID_DE_CUENTA_AWS>:inference-profile/*"
      ]
    },
    {
      "Sid": "ListFoundationModels",
      "Effect": "Allow",
      "Action": "bedrock:ListFoundationModels",
      "Resource": "*"
    }
  ]
}
```

Sustituir `<ID_DE_CUENTA_AWS>` por el ID de cuenta de 12 dígitos (**IAM → panel principal**). El segundo statement hace falta porque varios modelos recientes en Bedrock (p. ej. Claude Sonnet 4.6) solo se sirven vía *inference profile* (ARN con prefijo de región), no como *foundation model* directo — sin él, esos modelos fallarían con `AccessDenied` aunque el primer statement esté bien.

**El primer statement usa `*` en la región del ARN a propósito, no un descuido** — probado en el despliegue real: un *inference profile* `eu.` reparte las invocaciones entre varias regiones UE por debajo (a `pi-sonar` le tocó `eu-north-1` en una prueba, no `eu-west-1`), así que si el recurso `foundation-model` se deja fijado a una única región, Bedrock deniega la llamada en cuanto enruta a otra región del mismo perfil — mismo patrón que recomienda AWS para *cross-region inference*. El `inference-profile` en sí (segundo statement) sí se queda fijado a la cuenta/región donde vive el perfil — la apertura de región solo hace falta en el recurso `foundation-model` subyacente, no en el conjunto entero de acciones de Bedrock.

**Tercer statement, `bedrock:ListFoundationModels`, añadido después del despliegue inicial** — sin él, Bifrost no puede validar el catálogo de modelos en vivo al arrancar (avisos `not authorized to perform: bedrock:ListFoundationModels` en el log, visibles en el primer despliegue) y cae a su catálogo estático embebido — funcionalmente no bloqueaba nada (`InvokeModel` seguía funcionando), pero con este permiso Bifrost puede confirmar en vivo qué modelos están realmente disponibles en la cuenta. Bedrock no soporta permisos a nivel de recurso para esta acción — el `Resource` tiene que ser `"*"` por diseño del propio servicio, no por relajar el alcance a propósito. Sigue sin haber `bedrock-agent:*` ni ninguna acción de gestión/escritura de modelos.

**Aplicado y verificado** (agosto 2026): tras añadir el statement y reiniciar, el aviso de `bedrock:ListFoundationModels` desapareció del log — sustituido por uno **distinto**, `bedrock-mantle:ListModels` denegado sobre `arn:aws:bedrock-mantle:eu-west-1:<cuenta>:project/default`. Es otro espacio de nombres (Bedrock **Mantle**, la superficie que enruta modelos "estilo OpenAI" — GPT-OSS/Gemma vía Marketplace —, no el `bedrock-runtime` que usa Claude) que Bifrost también intenta listar al arrancar. Dejado sin permiso a propósito: no se usa ningún modelo vía Mantle en este despliegue, y es el mismo tipo de aviso benigno que el anterior (no bloquea `InvokeModel`, confirmado con una prueba real tras el cambio). Si en el futuro se quisiera cubrir también, el statement sería `{"Effect": "Allow", "Action": "bedrock-mantle:ListModels", "Resource": "arn:aws:bedrock-mantle:eu-west-1:<ID_DE_CUENTA_AWS>:project/*"}`.

### 2. Rol IAM — quien de verdad puede invocar Bedrock

1. **IAM → Roles → Create role** → *Custom trust policy*:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Principal": { "AWS": "arn:aws:iam::<ID_DE_CUENTA_AWS>:user/bifrost-bedrock-base" },
         "Action": "sts:AssumeRole"
       }
     ]
   }
   ```
2. Nombre del rol: `bifrost-bedrock-invoke`.
3. Adjuntar la policy del punto 1 (como *customer managed policy* nueva, o *inline*).

### 3. Usuario IAM base — solo puede asumir el rol, nada más

1. **IAM → Users → Create user**: `bifrost-bedrock-base`. Sin acceso a la consola (solo *programmatic access*).
2. Policy adjunta (inline), **sin ningún permiso de Bedrock**:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "sts:AssumeRole",
         "Resource": "arn:aws:iam::<ID_DE_CUENTA_AWS>:role/bifrost-bedrock-invoke"
       }
     ]
   }
   ```
3. **Security credentials → Create access key** → caso de uso "Application running outside AWS". Guardar `Access key ID` y `Secret access key` — no se pueden volver a ver tras cerrar ese diálogo. Estas son las **únicas** credenciales de larga duración de todo el montaje.

### 4. Cómo lo usa Bifrost — assume-role nativo, sin ficheros de perfil AWS

`bedrock_key_config` soporta `role_arn` (y `external_id`/`session_name`) **de forma nativa** — comprobado directamente contra el JSON Schema real que publica el proyecto (`https://www.getbifrost.ai/schema`), no asumido. Bifrost hace el *assume-role* él mismo con las credenciales del usuario base como punto de partida, y renueva la sesión temporal solo — sin necesidad de montar ningún fichero `~/.aws/credentials`/`config` ni depender de la cadena de credenciales por defecto del SDK. Es la opción más simple de las dos y la que quedó desplegada:

```json
"bedrock_key_config": {
  "region": "env.AWS_REGION",
  "access_key": "env.AWS_ACCESS_KEY_ID",
  "secret_key": "env.AWS_SECRET_ACCESS_KEY",
  "role_arn": "env.AWS_ROLE_ARN",
  "session_name": "bifrost-pi-sonar"
}
```

`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` son las del **usuario base** (`bifrost-bedrock-base`, sin permiso de Bedrock por sí mismo), `AWS_ROLE_ARN` es `arn:aws:iam::<ID_DE_CUENTA_AWS>:role/bifrost-bedrock-invoke` (el rol con la policy de invocación real) — las cuatro como variables de entorno normales en `pi-sonar/docker-compose.yml`/`.env`, nunca en `config.json` en claro.

La alternativa más robusta a largo plazo, si algún día las *access keys* del usuario base resultan incómodas de rotar, sería **IAM Roles Anywhere** (certificados X.509 en vez de cualquier *access key* de larga duración) — evaluada y descartada por ahora por la complejidad añadida frente al beneficio real en un homelab de un único usuario.

## Instalación

```bash
ssh u-sonar@192.168.1.172
mkdir -p /srv/homelab/pi-sonar/bifrost/data
```

Desde la máquina de desarrollo (rsync de lo versionado en el repo):

```bash
rsync -av pi-sonar/config/bifrost/config.json u-sonar@192.168.1.172:/srv/homelab/pi-sonar/bifrost/data/config.json
rsync -av pi-sonar/docker-compose.yml u-sonar@192.168.1.172:/srv/homelab/pi-sonar/docker-compose.yml
```

En `pi-sonar`:

```bash
cd /srv/homelab/pi-sonar
# La imagen corre /app/data como UID:GID 1000:0 — sin esto, Bifrost falla al
# arrancar con "is not writable by UID:GID 1000:0" (visto en el primer
# despliegue: el directorio quedó con el propietario por defecto de
# u-sonar, no 1000:0).
sudo chown 1000:0 bifrost/data && chmod 770 bifrost/data

nano .env   # AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (usuario base) / AWS_ROLE_ARN / AWS_REGION / BIFROST_VIRTUAL_KEY
docker compose up -d bifrost
docker compose logs -f bifrost
```

`config.json` (`pi-sonar/config/bifrost/config.json`, versionado en git) no contiene ningún secreto — todos los campos sensibles usan el prefijo `env.` (`env.AWS_ACCESS_KEY_ID`, `env.BIFROST_VIRTUAL_KEY`...), resueltos en tiempo de arranque contra las variables de entorno del contenedor. Los secretos reales viven solo en `/srv/homelab/pi-sonar/.env`, fuera de git — mismo patrón que el resto del repo.

Bifrost persiste su propio estado de gobernanza (virtual keys creadas/modificadas vía API o UI, tras el arranque inicial desde `config.json`) en `config.db` (SQLite), dentro del mismo volumen `/app/data` — por eso todo el directorio `bifrost/data/` debe tratarse como estado, no solo como config de solo lectura.

**`key_ids` en `provider_configs` de la virtual key debe ser `["*"]`, no el `name` de la clave del proveedor** — es un error real que apareció en el primer despliegue (`could not resolve keys: key_id=bedrock-primary`): `key_ids` referencia identificadores internos que Bifrost asigna él mismo, no el campo `name` que se puso en `config.json`. Con una sola clave de Bedrock, `["*"]` (documentado como "permitir todas las claves") es la forma correcta y más simple.

## nginx (`pi-dns`)

Bloque añadido a `pi-dns/config/nginx/nginx.conf` (sección "pi-sonar"):

```nginx
server {
    listen 443 ssl;
    server_name bifrost.home.arpa;
    location / {
        proxy_pass http://192.168.1.172:8080;
        include /etc/nginx/proxy-common.conf;
    }
}
```

Desplegar — **ojo con la ruta real en el host**: el repo versiona el fichero en `pi-dns/config/nginx/nginx.conf`, pero el `docker-compose.yml` de `pi-dns` monta `/srv/homelab/pi-dns/nginx/conf/nginx.conf` (convención distinta a la del checkout, heredada de una instalación anterior — ver `docs/06-instalacion-pi1-dns.md`, que ya documenta el mismo `cp` de `config/nginx/` a `nginx/conf/` para `apikey-auth.conf`). Copiar al sitio del repo y olvidarse de este paso da un `404` silencioso — pasó en el despliegue real:

```bash
rsync -av pi-dns/config/nginx/nginx.conf u-dns@192.168.1.170:/srv/homelab/pi-dns/nginx/conf/nginx.conf
ssh u-dns@192.168.1.170 'cd /srv/homelab/pi-dns && docker compose exec nginx nginx -t && docker compose exec nginx nginx -s reload'
```

Registro DNS: `bifrost.home.arpa → 192.168.1.170` (apunta a `pi-dns`, que hace el proxy — mismo patrón que el resto de servicios). Añadido a `shared/dns/dns-records.md` y a la lista `HOSTS` de `shared/scripts/load-dns-records.sh`:

```bash
PIHOLE_PASSWORD=*** bash shared/scripts/load-dns-records.sh
```

## Autenticación — virtual key de Bifrost

`config.json` define una única virtual key (`vk-homelab-cluster`), con `enforce_auth_on_inference: true` — cualquier petición a `/v1/chat/completions` sin ella recibe `401`. El valor real vive en `BIFROST_VIRTUAL_KEY` (`.env` de `pi-sonar`, fuera de git).

Los clientes (Open WebUI, n8n) deben mandar una de estas cabeceras:

```
Authorization: Bearer <BIFROST_VIRTUAL_KEY>
```
o
```
x-bf-vk: <BIFROST_VIRTUAL_KEY>
```

Rotar la key: generar un valor nuevo (`openssl rand -hex 24`, prefijo `sk-bf-` por convención), actualizarlo en `.env`, `docker compose up -d bifrost` (recarga el `config.json` con el nuevo valor resuelto), y actualizar la conexión en Open WebUI/n8n.

## Autenticación del panel de administración — `governance.auth_config`

**Hallazgo real de producción**: `enforce_auth_on_inference` protege únicamente `/v1/chat/completions` (y equivalentes) — **no** protege el panel web ni la API de administración (`/api/logs`, `/api/governance/*`, `/metrics`...). Sin nada más, cualquiera en la LAN con la URL `https://bifrost.home.arpa` podía leer el historial completo de prompts, modelos usados y coste por petición, sin ninguna credencial. Corregido con `governance.auth_config`:

```json
"governance": {
  "auth_config": {
    "is_enabled": true,
    "admin_username": "env.BIFROST_ADMIN_USERNAME",
    "admin_password": "env.BIFROST_ADMIN_PASSWORD"
  },
  ...
}
```

Variables correspondientes en `pi-sonar/.env` (usuario `admin`, contraseña generada con `openssl rand -hex 24`, guardada también en Vaultwarden). Verificado: sin credencial, `/api/logs` da `401`; con `-u admin:<password>` (HTTP Basic Auth estándar), `200`. La inferencia con la virtual key normal no se ve afectada — son dos mecanismos de auth independientes, uno para `/v1/*` (virtual key), otro para todo lo demás (usuario/contraseña de admin).

**Al acceder desde el navegador a `https://bifrost.home.arpa` ahora pedirá estas credenciales** (usuario/contraseña de admin), no las de ningún usuario de Open WebUI ni la virtual key.

## Seguimiento de coste y presupuesto con aviso

### Dashboard y logs — ya funciona sin configurar nada

Bifrost calcula el coste real de cada petición automáticamente (sincroniza precios por proveedor/modelo en segundo plano, `framework.pricing`) y lo guarda en el log de cada request — visible en el propio panel (`https://bifrost.home.arpa`, pestaña de logs) o vía API:

```bash
curl -sk -u admin:<BIFROST_ADMIN_PASSWORD> https://bifrost.home.arpa/api/logs
```

Cada entrada incluye `model`, `provider`, `latency` y `cost` (en USD) por petición individual — no hace falta activar nada para tener esto.

### Presupuesto (tope real de gasto) — `governance.budgets`, sí funciona

```json
"governance": {
  "budgets": [
    {
      "id": "budget-test",
      "virtual_key_id": "vk-homelab-cluster",
      "max_limit": 5,
      "reset_duration": "1M"
    }
  ],
  ...
}
```

`max_limit` en USD, `reset_duration` en formato Go duration (`1M` = 1 mes; también válidos `1d`, `1w`, `1h`...). **Verificado que aplica de verdad**, no es solo un contador informativo: según la documentación oficial de Bifrost, al superarlo cualquier petición nueva contra esa virtual key recibe `402 budget_exceeded` hasta el siguiente reinicio del ciclo. Consultar el gasto acumulado en cualquier momento:

```bash
curl -sk -u admin:<BIFROST_ADMIN_PASSWORD> https://bifrost.home.arpa/api/governance/budgets
# → {"budgets":[{"id":"budget-test","max_limit":5,"current_usage":0.0234,...}]}
```

**Ya hay uno configurado**: 5 USD/mes sobre la virtual key `vk-homelab-cluster` (el `id` interno quedó como `budget-test` — nombre histórico de cuando se verificó el mecanismo, cambiarlo requeriría borrar y recrear el presupuesto, no renombrarlo; no afecta a su funcionamiento). Ajustar el límite: editar `max_limit` en `config.json`, redesplegar y reiniciar `bifrost` — mismo `id`, así que Bifrost actualiza el existente en vez de crear uno duplicado.

### "Con aviso" — la parte que NO funciona en la edición autoalojada

Bifrost tiene un sistema de alertas declarativo (`alerting.channels` + `alerting.rules`, con expresiones CEL sobre `budget_usage_percent` para avisar, p. ej., al superar el 80 % — exactamente lo que haría falta para un "aviso" antes del corte total). **Se probó en este despliegue y no funciona**: el JSON se acepta sin error de validación, pero al arrancar Bifrost no aparece ningún plugin `alerting` entre los activos (`plugin status: ...` en el log — solo `logging`, `governance`, `compat`, `model-catalog-resolver`, `telemetry`, `prompts`), y `/api/alerting/channels` ni siquiera resuelve como endpoint real (cae al frontend SPA). El propio schema de configuración ya lo etiqueta como *"Enterprise config store"* — todo apunta a que es una función de pago, no incluida en la imagen `maximhq/bifrost` que usamos.

**Alternativa práctica, con lo que ya tiene el clúster**: un workflow de n8n (`n8n-main`, en `retaco`) con disparador cron, que llame periódicamente a `GET /api/governance/budgets` (con las credenciales de admin), compare `current_usage` contra un porcentaje de `max_limit`, y mande un aviso por el canal que se prefiera (ntfy si se despliega la mejora 4 del backlog, o cualquier otro webhook) cuando se cruce el umbral — mismo resultado que la función de pago, con piezas que ya existen en el clúster. No implementado todavía, anotado como posible ampliación si hace falta de verdad un aviso proactivo antes de los `402`.

## Conectar Open WebUI y n8n

**Open WebUI** (en `retaco`, desde la migración) — ya preconfigurado por variables de entorno al desplegar (`OPENAI_API_BASE_URLS`/`OPENAI_API_KEYS` en `retaco/docker-compose.yml`, ver sección de migración más abajo), no hace falta tocar `Admin Settings → Connections` a mano. Si se necesitara rehacerlo manualmente: conexión "OpenAI API", Base URL `https://bifrost.home.arpa/v1`, API Key el valor de `BIFROST_VIRTUAL_KEY`.

**n8n** — credencial de tipo "OpenAI" (o el nodo HTTP genérico si se prefiere no forzar el tipo):
- Base URL: `https://bifrost.home.arpa/v1`
- API Key: el valor de `BIFROST_VIRTUAL_KEY`

El modelo a seleccionar usa el prefijo del provider: `bedrock/eu.anthropic.claude-sonnet-4-6` (Bedrock, confirmado funcional en esta cuenta/región — ver "Prueba manual" para el porqué del prefijo `eu.`) u `ollama/<modelo>` (Ollama en `ryzen`, p. ej. `ollama/qwen3.5:9b` — ver la sección "Ollama como provider adicional" más abajo).

## Prueba manual

Ejecutada desde `ryzen`/`mole` (el puesto de trabajo físico, con acceso directo sin SSH — ver `docs/01-topologia.md`), para confirmar que la ruta completa cliente → nginx (`pi-dns`) → Bifrost (`pi-sonar`) → Bedrock funciona igual que le llegaría a Open WebUI:

```bash
curl -sk https://bifrost.home.arpa/v1/chat/completions \
  -H "Authorization: Bearer ${BIFROST_VIRTUAL_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "bedrock/eu.anthropic.claude-sonnet-4-6",
    "messages": [{"role": "user", "content": "Responde solo con la palabra: ok"}]
  }'
```

Respuesta esperada: JSON estilo OpenAI (`choices[0].message.content`) con el texto generado por Claude. Sin la cabecera `Authorization`, o con una key incorrecta: `401`. Con la key correcta pero sin permiso IAM sobre el modelo pedido: `403`/`AccessDeniedException` propagado desde Bedrock — señal de que la policy no cubre ese modelo concreto (ver sección de permisos arriba).

**Verificado end-to-end en el despliegue real** (agosto 2026), en orden:

1. Sin cabecera `Authorization` → `401` (virtual key obligatoria, confirmado).
2. Con la virtual key pero un `modelId` de ejemplo desactualizado (`anthropic.claude-3-5-haiku-20241022-v1:0`) → `ValidationException: invalid identifier` — el catálogo de Bedrock cambia con el tiempo, ese ID ya no existe.
3. Con `anthropic.claude-sonnet-5` → `AccessDeniedException: not available for this account` — modelo no habilitado en esta cuenta (Bedrock retiró la página clásica de "Model access"; para modelos Anthropic, la primera vez hay que enviar un formulario de "use case details" desde el propio Model catalog antes de poder invocarlos).
4. Con `anthropic.claude-sonnet-4-6` (sin prefijo de región) → `ValidationException: ... isn't supported [with] on-demand throughput. Retry ... with ... an inference profile` — este modelo concreto solo se sirve vía *inference profile*, no como *foundation model* directo.
5. Con `eu.anthropic.claude-sonnet-4-6` (inference profile) → `AccessDeniedException` de IAM, `... on resource: arn:aws:bedrock:eu-north-1::foundation-model/anthropic.claude-sonnet-4-6` — el perfil `eu.` reparte las invocaciones entre varias regiones UE por debajo (aquí le tocó `eu-north-1`, no `eu-west-1`), y la policy tenía el recurso `foundation-model` fijado a una única región. Corregido a `arn:aws:bedrock:*::foundation-model/*` (sección de permisos arriba).
6. Con la policy corregida, mismo modelo → **200, respuesta real de Claude**:
   ```json
   {"choices":[{"message":{"role":"assistant","content":"ok"}}], "model":"eu.anthropic.claude-sonnet-4-6", ...}
   ```

Modelo confirmado como funcional en esta cuenta/región: `bedrock/eu.anthropic.claude-sonnet-4-6` (usar este prefijo `bedrock/` desde Open WebUI/n8n).

## Alias de modelos Claude — el desplegable de Open WebUI usa nombres "pelados"

Open WebUI no permite escribir un ID de modelo a mano en el chat, solo elegir de un desplegable — y ese desplegable muestra los IDs de Bedrock tal cual (`anthropic.claude-sonnet-4-6`, sin el prefijo `eu.` del *inference profile*). Como casi todos los Claude de generación 4.x/5.x en Bedrock **exigen** ese prefijo (fallan con `on-demand throughput isn't supported` si se invocan pelados, ver sección de permisos), hacía falta que el nombre que ya aparece en el desplegable funcionara solo, sin pedirle al usuario que escriba nada especial.

Solución: campo `aliases` en la clave del provider `bedrock` (`pi-sonar/config/bifrost/config.json`) — mapea el nombre pelado (lo que manda Open WebUI) al ID real con `eu.` (lo que de verdad acepta Bedrock), de forma transparente:

```json
"aliases": {
  "anthropic.claude-sonnet-4-20250514-v1:0": "eu.anthropic.claude-sonnet-4-20250514-v1:0",
  "anthropic.claude-sonnet-4-5-20250929-v1:0": "eu.anthropic.claude-sonnet-4-5-20250929-v1:0",
  "anthropic.claude-sonnet-4-6": "eu.anthropic.claude-sonnet-4-6",
  "anthropic.claude-sonnet-5": "eu.anthropic.claude-sonnet-5",
  "anthropic.claude-haiku-4-5-20251001-v1:0": "eu.anthropic.claude-haiku-4-5-20251001-v1:0",
  "anthropic.claude-opus-4-5-20251101-v1:0": "eu.anthropic.claude-opus-4-5-20251101-v1:0",
  "anthropic.claude-opus-4-6-v1": "eu.anthropic.claude-opus-4-6-v1",
  "anthropic.claude-opus-4-7": "eu.anthropic.claude-opus-4-7",
  "anthropic.claude-opus-4-8": "eu.anthropic.claude-opus-4-8",
  "anthropic.claude-opus-5": "eu.anthropic.claude-opus-5",
  "anthropic.claude-fable-5": "eu.anthropic.claude-fable-5"
}
```

No se alias `anthropic.claude-3-haiku-20240307-v1:0` (más antiguo) — falla por un motivo distinto (`Access denied... marked by provider as Legacy and you have not been actively using the model`, un modelo desactivado por inactividad de cuenta, no un problema de *inference profile*).

### Confirmados funcionando de extremo a extremo, con el nombre pelado tal cual aparece en el desplegable

| Modelo | Nota |
|---|---|
| `bedrock/anthropic.claude-sonnet-4-6` | — |
| `bedrock/anthropic.claude-opus-4-5-20251101-v1:0` | — |
| `bedrock/anthropic.claude-haiku-4-5-20251001-v1:0` | — |
| `bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0` | Necesitó un paso adicional: suscripción de AWS Marketplace desde la consola (Bedrock → Model catalog → buscar por el **ID exacto**, no por el nombre comercial "Sonnet 4.5" — la consola tenía el nombre comercial apuntando a la entrada de catálogo equivocada, `claude-sonnet-5`, que sí está genuinamente no disponible para esta cuenta) |

`anthropic.claude-sonnet-5` (sin fecha, generación más nueva) sigue **no disponible para esta cuenta** — error `AccessDeniedException: ... is not available for this account`, distinto del resto (no es de permisos ni de *inference profile*, es de entitlement de la propia cuenta AWS — el mensaje sugiere contactar con AWS Sales si hiciera falta).

## Dónde se almacena todo lo que se ve en el panel

Tres cosas distintas, tres sitios distintos:

| Qué | Dónde | ¿Persiste entre reinicios/recreaciones? |
|---|---|---|
| **Logs de peticiones** — modelo, proveedor, coste, latencia, timestamps, resumen truncado del contenido (`content_summary`) | SQLite `/app/data/logs.db` (host: `/srv/homelab/pi-sonar/bifrost/data/logs.db`) | Sí — dentro del volumen montado |
| **Gobernanza** — virtual keys, presupuestos y su gasto acumulado (`current_usage`), config de autenticación del panel | SQLite `/app/data/config.db` (host: `/srv/homelab/pi-sonar/bifrost/data/config.db`) | Sí, **ahora** — ver el fallo real de abajo |
| **Métricas `/metrics` (formato Prometheus)** — `bifrost_cost_total` y demás contadores | En memoria del proceso, recalculadas sobre la marcha | **No** — se resetean a cero en cada reinicio; solo quedarían con histórico real si algo externo las scrapea y las guarda (Prometheus, mejora 22 del backlog) |

**Los prompts y respuestas completos (el texto real) NO se guardan por defecto** — solo el `content_summary` truncado que se ve en el log. Guardar el cuerpo completo de cada petición/respuesta requeriría activar `client.disable_content_logging: false` (ya es el comportamiento por defecto, así que en realidad ya casi se guarda — la diferencia real es `send_back_raw_request`/`send_back_raw_response`/`store_raw_request_response` a nivel de proveedor, desactivados aquí) — no configurado en este despliegue.

### Fallo real encontrado y corregido: `config.db` vivía fuera del volumen persistente

`config_store.config.path` en `config.json` estaba puesto como `"config.db"` — una ruta **relativa**. El directorio de trabajo real del proceso de Bifrost es `/app`, no `/app/data`, así que el fichero real se creaba en `/app/config.db`: dentro de la capa interna del contenedor, **fuera** del volumen `/app/data` que sí está montado al host. Confirmado en el despliegue real (`docker exec bifrost find / -iname 'config.db*'` lo mostraba en `/app`, no en `/app/data`).

Efecto práctico: el presupuesto y su gasto acumulado habrían sobrevivido a un `restart` (el contenedor no se destruye), pero se habrían perdido ante cualquier recreación completa (`docker compose up -d` tras cambiar de imagen, `docker rm` + recrear, etc.) — justo el tipo de dato que más le importa a la pregunta de "cuánto llevo gastado".

Corregido cambiando la ruta a **absoluta, dentro del volumen ya montado**:

```json
"config_store": {
  "enabled": true,
  "type": "sqlite",
  "config": {
    "path": "/app/data/config.db"
  }
}
```

Verificado tras el cambio: `config.db` aparece ahora en `/srv/homelab/pi-sonar/bifrost/data/` (visible desde el host), y el presupuesto se recreó correctamente a partir de `config.json` (gasto acumulado volvió a 0 — pérdida trivial, unos pocos céntimos, y es exactamente el momento más barato para haberlo corregido).

## Operación

- **Arranque/parada**: `cd /srv/homelab/pi-sonar && docker compose up -d bifrost` / `docker compose stop bifrost` — igual que cualquier otro servicio del clúster (`docs/11-operacion-diaria.md`).
- **Logs**: `docker compose logs -f bifrost`, o desde Grafana/Loki (`promtail` en `pi-sonar` ya envía los logs de todos los contenedores del nodo) — esto son los logs del *proceso* (stdout), no los logs de peticiones del panel (esos están en `logs.db`, ver arriba).
- **Actualizaciones**: **manuales, nunca automáticas** — `bifrost` no lleva la label de watchtower a propósito (mismo criterio que `sonarqube` en este nodo, ver `docs/16-mantenimiento-actualizaciones.md`). Subir de versión: cambiar el tag en `pi-sonar/docker-compose.yml`, `docker compose pull bifrost && docker compose up -d bifrost`, revisar el changelog de Bifrost antes (puede tocar el formato de `config.json` o el comportamiento de `enforce_auth_on_inference`).
- **Coste**: Bedrock factura por token de AWS — a diferencia del resto del clúster (100 % local). Presupuesto de 5 USD/mes ya configurado (`governance.budgets`, ver sección "Seguimiento de coste y presupuesto con aviso" más arriba).
- **Añadir más modelos/proveedores**: editar `providers` en `config.json` (nuevo proveedor) y `allowed_models` de la virtual key si se quiere restringir por modelo en vez de dejar `["*"]`.
- **Backup**: `bifrost/data/` (`config.db` con el estado de gobernanza, `logs.db` con el historial de peticiones) no está cubierto todavía por ningún script de `shared/scripts/backup-*.sh` — con `config.db` ya persistiendo correctamente en el volumen (ver arriba), perder el directorio entero ante un fallo de disco sí sería una pérdida real ahora (presupuesto, gasto acumulado, historial de logs), no solo un inconveniente menor — candidato razonable para la mejora 1 del backlog (copias de seguridad automatizadas) el día que se aborde.

## Troubleshooting

| Síntoma | Causa probable |
|---|---|
| Contenedor en *restart loop*, log `Error: /app/data is not writable by UID:GID 1000:0 (owned by ...)` | Visto en el despliegue real — la imagen corre como UID:GID `1000:0`, y `mkdir` en el host crea el directorio con el propietario del usuario SSH (`u-sonar`, no `1000:0`). Arreglo: `sudo chown 1000:0 bifrost/data && chmod 770 bifrost/data` antes de `docker compose up` |
| `failed to sync governance config: ... could not resolve keys: key_id=<nombre>` al arrancar | Visto en el despliegue real — `key_ids` en `provider_configs` de la virtual key debe ser `["*"]`, no el `name` de la clave del proveedor (`bedrock-primary` en nuestro caso). Bifrost asigna sus propios identificadores internos a cada clave; `name` es solo para logs/UI, no es lo que `key_ids` espera |
| `401` en toda petición, incluso con la key correcta | `BIFROST_VIRTUAL_KEY` en `.env` no coincide con el valor que Bifrost resolvió al arrancar — revisar `docker compose logs bifrost` al inicio, o reiniciar tras cambiar `.env` |
| Error de credenciales AWS al arrancar (`unable to assume role`, `AccessDenied` en el propio `AssumeRole`) | Revisar `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`/`AWS_ROLE_ARN` en `.env`, y que la trust policy del rol `bifrost-bedrock-invoke` apunte exactamente al ARN del usuario `bifrost-bedrock-base` — un ARN mal escrito en cualquiera de los dos lados rompe el `AssumeRole` en silencio. Verificable fuera de Bifrost con `aws sts assume-role --role-arn <ARN> --role-session-name test` usando las credenciales del usuario base |
| `403` / `AccessDeniedException` de Bedrock (pero el `AssumeRole` funcionó) | La policy adjunta al **rol** no cubre el modelo pedido — comprobar si es un *inference profile* (necesita el segundo `Statement`) o si el modelo no está habilitado en **Bedrock → Model access** de esa cuenta/región (paso manual en la consola de AWS, aparte de IAM) |
| `ValidationException: The provided model identifier is invalid` | El `modelId` no existe tal cual en esa región/cuenta — el catálogo de Bedrock cambia con frecuencia (IDs de *foundation model* vs. *inference profile*, con o sin prefijo de región). Confirmar el ID exacto en **Bedrock → Model catalog** de la consola antes de asumir que es un problema de permisos |
| `404` de nginx (página genérica, no de Bifrost) en `bifrost.home.arpa` | Visto en el despliegue real — `nginx.conf` se copió a la ruta del repo (`config/nginx/`) en vez de a la ruta real montada por Docker en este nodo (`/srv/homelab/pi-dns/nginx/conf/nginx.conf`); sin el bloque `bifrost.home.arpa` cargado, nginx cae al primer `server{}` de la lista (`index.home.arpa`) y da 404 al no encontrar la ruta como fichero estático |
| `502` desde nginx en `bifrost.home.arpa` | Contenedor `bifrost` caído o arrancando — `docker compose ps` en `pi-sonar`, healthcheck tarda hasta `start_period: 15s` |
| Contenedor marcado `unhealthy` en `docker compose ps` pese a responder bien a las peticiones reales | Visto en el despliegue real — la imagen de Bifrost **no trae `bash`** (`docker inspect bifrost --format '{{json .State.Health}}'` mostraba `"bash: not found"`), así que el truco `bash -c '</dev/tcp/...'` usado para `qdrant` en `retaco` no sirve aquí. Sí trae `wget` — healthcheck corregido a `wget -q -O /dev/null http://localhost:8080/health` |
| Open WebUI sin ningún modelo en el selector, sin error visible en la UI | Visto en el despliegue real — cliente TLS estricto (Python/aiohttp) fallando en silencio contra `bifrost.home.arpa`: revisar logs (`docker compose logs open-webui \| grep -i ssl`). Dos causas posibles, en este orden: (1) el SAN del certificado de `pi-dns` no incluye ese hostname — `openssl s_client -connect <ip-pi-dns>:443 -servername bifrost.home.arpa \| openssl x509 -noout -text \| grep -A2 "Subject Alternative Name"`; (2) el proceso no confía en la CA interna — ver sección "No hay modelos disponibles" arriba para ambos fixes |
| Timeout en respuestas largas | Igual que `ollama.home.arpa` (`docs/06`) — si se repite, subir `proxy_read_timeout`/`proxy_send_timeout` en el bloque `bifrost.home.arpa` de `nginx.conf`, no tocado por defecto porque Bedrock suele responder dentro del timeout estándar de nginx (60s) salvo generaciones muy largas |
| `connection to private IP <IP> is not allowed` | Bifrost bloquea por defecto conexiones a IPs RFC 1918 (protección SSRF) — pasa con cualquier provider casero en la LAN, no solo Ollama. Añadir `"network_config": {"allow_private_network": true}` como hermano de `"keys"` dentro del bloque de ese provider en `config.json` (ver sección de Ollama más abajo) |
| `Model '<nombre>' is not allowed for this virtual key`, con `routing_info` vacío | El *live model listing* del provider falló al arrancar (ver siguiente fila) y Bifrost cae a un catálogo estático que no conoce modelos locales/arbitrarios — no es un problema de la propia virtual key aunque el mensaje lo sugiera |
| `failed to list models ...: failed to execute HTTP request to provider API: falling back onto the static datasheet` para un provider casero (Ollama, LM Studio, vLLM propio...) | Casi siempre el bloqueo de IP privada de la fila de arriba — confirmarlo probando `docker exec bifrost sh -c 'wget -qO- <url>'` (si eso responde bien pero Bifrost sigue fallando, es la protección SSRF, no un problema de red real) |

## Ollama como provider adicional — modelos locales de `ryzen` a través del mismo gateway

Motivo: Open WebUI se migró de `ryzen` a `retaco` (ver sección de migración más abajo) y ya no puede llegar a Ollama por red Docker interna. La alternativa nativa de Open WebUI (conexión "Ollama" directa a `https://ollama.home.arpa`) exige la cabecera `X-Api-Key` de `apikey-service`, y no hay confirmación fiable de que ese tipo de conexión sepa mandarla — sí sabemos que la conexión "OpenAI API" manda `Authorization: Bearer` correctamente, porque es como ya hablamos con Bedrock. Se optó por añadir Ollama como provider más dentro de Bifrost: una única conexión desde Open WebUI, un único virtual key, para Bedrock y para Ollama.

`config.json` (fragmento relevante, `providers.ollama`):

```json
"ollama": {
  "keys": [
    {
      "name": "ollama-ryzen",
      "models": ["*"],
      "weight": 1.0,
      "ollama_key_config": {
        "url": "env.OLLAMA_UPSTREAM_URL"
      }
    }
  ],
  "network_config": {
    "allow_private_network": true
  }
}
```

Y en la virtual key, un segundo `provider_configs` (junto al de `bedrock` ya existente):

```json
{
  "provider": "ollama",
  "weight": 1.0,
  "allowed_models": ["*"],
  "key_ids": ["*"]
}
```

`OLLAMA_UPSTREAM_URL` (variable de entorno en `pi-sonar/docker-compose.yml`/`.env`, no en `config.json` directamente): **`http://192.168.1.150:11434`, por IP directa, no `https://ollama.home.arpa`**. Es tráfico servicio-a-servicio dentro de la LAN — mismo patrón que el resto del clúster (`n8n-main`, Qdrant... llegan a sus backends por IP directa; `apikey-service` solo protege las rutas de `nginx` pensadas para clientes humanos/externos, no las llamadas internas entre nodos). Ollama no tiene autenticación propia — igual que antes de la migración, sin cambio real de superficie de riesgo, solo cambia quién hace la llamada.

`ollama_key_config` solo necesita `url` — a diferencia de Bedrock, Ollama no tiene concepto de credenciales, así que no hay nada más que configurar.

### Dos problemas reales encontrados al desplegar esto, en orden

1. **Bloqueo SSRF de IPs privadas.** Primer intento sin `network_config`: toda petición a `ollama/*` daba `model_blocked` (`"Model '...' is not allowed for this virtual key"`, con `routing_info` vacío) o, mirando el log, `failed to execute HTTP request to provider API: falling back onto the static datasheet` — el *live model listing* de Ollama fallaba silenciosamente en cada arranque/refresco, aunque `docker exec bifrost wget http://192.168.1.150:11434/api/version` funcionaba perfectamente desde dentro del propio contenedor. La causa real, solo visible al probar una petición de inferencia real (no solo el listado): `{"error":"connection to private IP 192.168.1.150 is not allowed"}` — Bifrost bloquea por diseño las IPs RFC 1918 salvo que se le diga explícitamente lo contrario, ver `network_config.allow_private_network` arriba.
2. **Refresco del catálogo en segundo plano.** Tras el fix de arriba hizo falta reiniciar Bifrost para que el *live model listing* de Ollama se resolviera correctamente contra el catálogo real (`qwen3.5:27b`, `qwen3.5:9b`, etc., no los nombres desactualizados de `CLAUDE.md`). Se añadió `framework.pricing.live_models_sync_interval: 60` (mínimo permitido) en `config.json` para que ese refresco ocurra cada 60s en vez de cada hora — útil mientras se prueba, opcional mantenerlo a largo plazo.

Verificado con `qwen3.5:9b` (modelo de razonamiento — la respuesta incluye su propio *reasoning trace* antes del contenido final): `200`, `content: "ok"`, `latency: ~2.8s`, `routing_info.provider: "ollama"`. Modelo a usar desde Open WebUI/n8n: `ollama/qwen3.5:9b` (mismo prefijo `provider/` que `bedrock/...`).

## Migración de Open WebUI: de `ryzen` a `retaco`

**Por qué**: `retaco` está siempre encendido, `ryzen` no — Open WebUI (y, a través de Bifrost, tanto Bedrock como Ollama) queda accesible aunque el puesto de trabajo físico esté apagado. Decisión tomada en conversación, con dos motivos concretos verificados antes de mover nada: RAM real disponible en `retaco` (`free -h`, con margen de sobra) y que Open WebUI, corriendo como "solo backend + UI" sin RAG local activo, no necesita el peso que sí necesitaría con embeddings locales cargados.

### Qué se migró y qué no

Del volumen `ryzen/open-webui/data/` (890 MB total):

| Directorio/fichero | Migrado | Motivo |
|---|---|---|
| `webui.db` | Sí | Usuarios, chats, configuración — el estado real |
| `vector_db/` (ChromaDB) | Sí | Colecciones de Knowledge/RAG local, si se han usado (184 KB en este despliegue — uso mínimo) |
| `uploads/` | Sí | Ficheros subidos referenciados por Knowledge (vacío en este despliegue) |
| `cache/` | **No** | 889 MB — modelos de embeddings/caché descargados, reconstruible sin pérdida de datos reales; no vale la pena migrar 889 MB por red para algo que se regenera solo |

```bash
rsync -av \
  /srv/homelab/ryzen/open-webui/data/webui.db \
  /srv/homelab/ryzen/open-webui/data/vector_db \
  /srv/homelab/ryzen/open-webui/data/uploads \
  retaco:/srv/homelab/retaco/open-webui/data/
```

### Backend LLM tras la migración

`ENABLE_OLLAMA_API=false` — la conexión nativa "Ollama" de Open WebUI queda desactivada del todo, ya no se usa. Una única conexión "OpenAI API", preconfigurada por variables de entorno en `retaco/docker-compose.yml` (patrón estable — se evitó `OPENAI_API_CONFIGS`/`OLLAMA_API_CONFIGS`, las variables JSON más nuevas, por un bug conocido de parseo en versiones recientes de Open WebUI):

```yaml
environment:
  ENABLE_OLLAMA_API: "false"
  OPENAI_API_BASE_URLS: https://bifrost.home.arpa/v1
  OPENAI_API_KEYS: ${BIFROST_VIRTUAL_KEY}
```

`WEBUI_SECRET_KEY` — **mismo valor exacto que tenía `ryzen/.env`** (`OPENWEBUI_SECRET_KEY`). Firma las sesiones existentes; con un valor distinto los usuarios ya creados no invalidan datos pero sí tienen que volver a iniciar sesión.

### nginx (`pi-dns`) y orden de corte

```nginx
server {
    listen 443 ssl;
    server_name openwebui.home.arpa;
    location / {
        proxy_pass http://192.168.1.174:8080;   # antes: 192.168.1.150:8080
        include /etc/nginx/proxy-common.conf;
    }
}
```

**Mismo aviso de ruta real que en la sección de instalación de Bifrost**: en `pi-dns`, el fichero de verdad es `/srv/homelab/pi-dns/nginx/conf/nginx.conf`, no `config/nginx/` (convención del checkout distinta a la del host). Se despliega ahí, se valida con `nginx -t`, y se recarga con `nginx -s reload` (no hace falta `restart`).

Orden seguido, cada paso verificado antes de pasar al siguiente:
1. Desplegar `open-webui` en `retaco` con los datos ya migrados.
2. Verificar en local (`curl http://192.168.1.174:8080/api/config`, `docker exec open-webui` consultando `webui.db` directamente — confirmado 1 usuario existente, la cuenta ya creada en `ryzen`, migrada intacta) **antes** de tocar nginx.
3. Repuntar nginx, recargar, verificar de nuevo pero esta vez contra `https://openwebui.home.arpa` (la ruta real que van a usar los clientes).
4. Solo entonces, retirar el servicio de `ryzen/docker-compose.yml` — los datos originales (`ryzen/open-webui/data/`) se dejan en el disco como backup, no se borran.

### Qué cambia para quien ya usaba Open WebUI

- **Usuario/contraseña: hay que crearlos de nuevo** — no es lo que se hizo al principio (ver más abajo, "Base de datos centralizada", el cambio de SQLite a Postgres dejó esto sin efecto a los pocos minutos de migrar, con muy poco todavía configurado). Registrarse de nuevo en `https://openwebui.home.arpa` — el primer usuario que se registra en una base vacía se convierte en administrador automáticamente.
- Mismos modelos disponibles, con nombres nuevos: `bedrock/eu.anthropic.claude-sonnet-4-6` (Bedrock) y `ollama/<modelo>` (Ollama de `ryzen`) — ya no aparece una sección "Ollama" separada en la UI, todo cuelga de la única conexión OpenAI-compatible hacia Bifrost.
- Si `ryzen` está apagado, Bedrock sigue funcionando con normalidad; los modelos `ollama/*` fallan (Bifrost no puede alcanzar `192.168.1.150:11434`) hasta que se encienda — comportamiento esperado, no un fallo de la migración.

## "No hay modelos disponibles" — CA interna y certificado incompleto

Tras la migración a Postgres, con usuario nuevo creado, la UI no mostraba ningún modelo. `Bifrost` respondía perfectamente por su cuenta (`curl -k .../v1/models` daba el catálogo completo) — el problema estaba en cómo Open WebUI, como cliente HTTPS estricto, verifica el certificado de `bifrost.home.arpa`. Dos fallos reales distintos, hallados en este orden:

### 1. El certificado compartido de `pi-dns` no incluía `bifrost.home.arpa`

`pi-dns/config/nginx/generate-cert.sh` mantiene una lista fija `DOMAINS` con los nombres que entran en el `subjectAltName` (SAN) del certificado único que sirve todo `nginx`. Bifrost (y `apikey.home.arpa`, `epub2pdf.home.arpa`, `pdf2chunks.home.arpa`) se añadieron a nginx **después** de la última vez que se generó ese certificado, así que nunca entraron en el SAN. Los `curl -k` usados durante todo este documento **no lo detectaban** — `-k` se salta la verificación de hostname además de la de CA. Un cliente TLS estricto (Python `ssl`/`aiohttp`, lo que usa Open WebUI) sí la exige, y sin SAN da `Hostname mismatch, certificate is not valid for 'bifrost.home.arpa'`.

Corregido añadiendo los cuatro dominios que faltaban a `DOMAINS` en `generate-cert.sh` y regenerando:

```bash
ssh pi-dns
bash generate-cert.sh          # mismo CA, nuevo certificado con el SAN completo
docker exec nginx nginx -s reload
```

Como sigue firmado por la misma CA interna, ningún dispositivo que ya confiara en ella necesita reinstalar nada — solo nginx tenía que recargar el fichero nuevo.

### 2. Open WebUI (Python) no confía en la CA interna por defecto

Con el SAN corregido, el error cambió a `SSLCertVerificationError: unable to get local issuer certificate` — Open WebUI usa `aiohttp`, que por defecto valida contra el bundle de **`certifi`** (paquete Python con la lista de CAs públicas de Mozilla), no contra el almacén de certificados del sistema operativo ni contra ninguna CA propia. Mismo tipo de problema ya conocido en este repo para otros lenguajes (`NODE_EXTRA_CA_CERTS` en `n8n-main`, `REQUESTS_CA_BUNDLE` en `pysonar` — `docs/09`), aquí con su propia variante Python/aiohttp.

Solución aplicada en `retaco/docker-compose.yml` — montar la CA y generar un bundle combinado (CAs públicas de `certifi` + la CA interna) en un fichero nuevo, **sin sustituir** el bundle de `certifi` entero (para no romper la verificación de servicios públicos reales, como la descarga del modelo de embeddings desde `huggingface.co`, confirmada seguía funcionando tras el cambio):

```yaml
volumes:
  - /srv/homelab/retaco/open-webui/homelab-ca.crt:/etc/ssl/certs/homelab-ca.crt:ro
entrypoint: ["sh", "-c"]
command:
  - |
    CERTIFI_BUNDLE=$$(python3 -c "import certifi; print(certifi.where())") &&
    cat "$$CERTIFI_BUNDLE" /etc/ssl/certs/homelab-ca.crt > /tmp/combined-ca.pem &&
    export SSL_CERT_FILE=/tmp/combined-ca.pem &&
    exec bash start.sh
```

La ruta de `certifi` se resuelve en caliente (`python3 -c "import certifi; print(certifi.where())"`) en vez de hardcodear la versión de Python de la imagen (`python3.11` hoy) — evita que una actualización futura de la imagen rompa esto en silencio. Verificado contra el proceso real, no solo con `docker exec` suelto: `cat /proc/1/environ` dentro del contenedor confirma `SSL_CERT_FILE` puesto en el proceso que de verdad sirve la app, y una llamada real a `https://bifrost.home.arpa/v1/models` desde dentro del contenedor devuelve los 64 modelos del catálogo.

**Esta corrección de `generate-cert.sh` es de infraestructura compartida, no específica de Open WebUI** — cualquier otro cliente HTTPS estricto (no solo Python) que hable con `bifrost.home.arpa`, `apikey.home.arpa`, `epub2pdf.home.arpa` o `pdf2chunks.home.arpa` se beneficia del SAN corregido sin hacer nada más.

## Base de datos centralizada: Postgres + Qdrant (en vez de SQLite/ChromaDB locales)

Decisión tomada aparte, después de la migración inicial: con muy poco todavía configurado en la instancia recién migrada (sin uso real, solo pruebas), se aprovechó para dejar de depender de las bases de datos locales por defecto de Open WebUI (SQLite para todo lo de aplicación, ChromaDB local para RAG/Knowledge) y centralizarlas en la infraestructura que el clúster ya tiene — mismo criterio que el resto de servicios en `retaco`.

### Un hallazgo real por el camino: la config persistida gana a las variables de entorno

Al migrar `webui.db` tal cual desde `ryzen` (antes de decidir pasar a Postgres), la conexión a Bifrost que se había preconfigurado por variables de entorno (`OPENAI_API_BASE_URLS`/`OPENAI_API_KEYS`) **no se aplicó** — Open WebUI guarda su configuración en una tabla `config` (una fila por clave, no un blob único), y esas variables de entorno solo siembran valores en una base **vacía**. Como `webui.db` venía con configuración real ya existente de `ryzen` (`ollama.enable=true`, `ollama.base_urls=["http://ollama:11434"]`, `openai.api_base_urls=["https://api.openai.com/v1"]` por defecto), esa config persistida ganó, y la UI no mostraba ningún modelo hasta corregirlo a mano desde `Admin Settings → Connections`.

Con Postgres (base `openwebui`, vacía desde el primer arranque) esto no vuelve a pasar — confirmado con `SELECT key, value FROM config WHERE key IN ('ollama.enable','openai.enable','openai.api_base_urls','openai.api_keys')` justo después del primer arranque: `ollama.enable=false`, `openai.api_base_urls=["https://bifrost.home.arpa/v1"]`, `openai.api_keys` con la virtual key correcta — las variables de entorno se sembraron bien esta vez.

### Postgres — base `openwebui`

Creada con el patrón ya establecido (`create-postgres-db.sh`, misma herramienta que `n8n`/`sonarqube`/`apikeys`):

```bash
ssh retaco
bash /srv/homelab/shared/scripts/create-postgres-db.sh postgres-main dbadmin openwebui openwebui
```

`DATABASE_URL` en `retaco/docker-compose.yml`:

```yaml
DATABASE_URL: postgresql://openwebui:${OPENWEBUI_DB_PASSWORD}@postgres-main:5432/openwebui
```

Por nombre de contenedor (`postgres-main`, no `postgresql.home.arpa`) porque `open-webui` vive en el mismo nodo, en la misma red `retaco-net` — mismo patrón que `n8n-main` (ver `docs/05-instalacion-retaco.md`). Al arrancar, Open WebUI corre sus propias migraciones de Alembic contra la base vacía (esquema completo, ~20 migraciones) — no hace falta ningún paso manual de inicialización, a diferencia de Postgres para n8n (que sí necesita `01-init-n8n.sh` porque usa el entrypoint oficial de la imagen `postgres`, no un ORM con migraciones propias).

### Qdrant — vectores de RAG/Knowledge

```yaml
VECTOR_DB: qdrant
QDRANT_URI: http://qdrant:6333
QDRANT_API_KEY: ${QDRANT_API_KEY}
```

Mismo Qdrant que ya usa el pipeline de contenido (`articles`, `transcripts`) — Open WebUI crea sus propias colecciones con el prefijo `open-webui_...` por defecto (`QDRANT_COLLECTION_PREFIX`), sin colisión con las existentes, sin necesidad de configurar nada aparte. `http://` (no HTTPS) porque es tráfico interno de `retaco-net`, no cruza la LAN — Open WebUI avisa en el log ("Api key is used with an insecure connection"), esperado y sin importancia en este contexto, mismo criterio que el resto del tráfico interno del clúster.

### Vaultwarden — por qué no se pudo automatizar

Se pidió guardar `OPENWEBUI_DB_PASSWORD` y `QDRANT_API_KEY` en Vaultwarden. **No es automatizable sin la contraseña maestra de un usuario real**: Vaultwarden es un servidor Bitwarden-compatible con cifrado de extremo a extremo — el `VAULTWARDEN_ADMIN_TOKEN` (que sí se tiene) solo da acceso al panel `/admin` (gestión de usuarios del servidor, diagnóstico), nunca al contenido cifrado de un vault concreto, que el propio servidor no puede leer ni escribir sin una sesión autenticada de ese usuario (contraseña maestra, interactiva). Añadidas a mano por el usuario tras esta migración — dos entradas nuevas en Vaultwarden:
- `openwebui — postgres` (usuario `openwebui`, contraseña `OPENWEBUI_DB_PASSWORD`, host `postgres-main:5432`/`postgresql.home.arpa:5432`, base `openwebui`)
- Confirmar si `QDRANT_API_KEY` ya estaba guardada de antes (se reutiliza la misma que ya usa el pipeline de contenido, no se generó una nueva)

### Efecto sobre lo migrado de `ryzen`

El `webui.db`/`vector_db` migrados de `ryzen` (sección anterior) quedan en `/srv/homelab/retaco/open-webui/data/` sin usarse — Postgres y Qdrant los sustituyen por completo para datos de aplicación y vectores. No se borran (mismo criterio de todo este documento: dejar backups en vez de eliminar), pero ya no hace falta preservarlos con cuidado especial — la única cuenta que tenían (creada en `ryzen`) no se migró a Postgres, hay que darla de alta de nuevo.
