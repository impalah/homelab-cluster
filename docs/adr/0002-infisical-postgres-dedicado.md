# ADR 0002 — Infisical usa un Postgres dedicado, no `postgres-main`

**Estado**: aceptada
**Fecha**: 2026-08-09
**Contexto**: mejora 16 del backlog (`docs/22-mejoras-futuras.md`), desarrollada en `docs/26-infisical-secretos.md`

## Contexto

El primer despliegue de Infisical (ver historial de este mismo documento en `docs/26-infisical-secretos.md`) usó una base `infisical` dentro de `postgres-main` — el mismo patrón que ya siguen `n8n`, `openwebui` y `apikeys` (`create-postgres-db.sh`, aislamiento por rol/base dentro de la misma instancia). Durante la revisión se planteó una pregunta legítima: si Infisical depende de `postgres-main`, ¿qué pasa el día que `postgres-main` tenga un incidente o mantenimiento por un motivo que no tiene nada que ver con Infisical?

Dos preocupaciones distintas, que conviene no mezclar:

1. **La contraseña de `dbadmin` (superusuario de `postgres-main`) nunca va a poder protegerla Infisical** — esto es cierto sea cual sea la base de datos que use Infisical, incluso una dedicada: el backend de almacenamiento de Infisical necesita estar accesible ANTES de que Infisical pueda servir ningún secreto, así que la credencial de ESE backend (dedicado o compartido) es, por definición, un secreto que Infisical nunca puede autoproteger — mismo problema de fondo que el sellado de Vault, ya descartado en `docs/22` mejora 16. Esta ADR no resuelve ni pretende resolver este punto — es estructural.
2. **Radio de fallo compartido** — esto sí es evitable, y es lo que resuelve esta decisión: si Infisical depende de `postgres-main`, cualquier mantenimiento, sobrecarga o incidente de esa instancia (por cualquier motivo ajeno a Infisical — un problema de `n8n`, de `openwebui`, de `sonarqube`...) tumba también al gestor de secretos, y con él, en cascada, a cualquier servicio ya migrado que necesite `infisical run` para arrancar. `valkey` (Redis) no tenía este problema al reutilizarse — `docs/25-valkey-cache.md` documenta que no tenía ningún consumidor real todavía — pero `postgres-main` sí es ya multi-tenant en producción.

## Alternativas consideradas

### A — Compartir `postgres-main` (descartada, fue el primer despliegue real)

Base `infisical` dentro de `postgres-main`, mismo patrón que `n8n`/`openwebui`/`apikeys`. Cero trabajo adicional, reutiliza backups existentes tal cual. Descartada por el motivo 2 de arriba — el propio mecanismo que hace útil a Infisical (que otros servicios dependan de él para arrancar) es justo lo que empeora las consecuencias de heredar el radio de fallo de una instancia multi-tenant que no tiene motivo para compartir.

### B — Postgres dedicado en `retaco` (elegida)

Contenedor `postgres-infisical` propio, mismo nodo (`retaco`, siempre encendido), sin multi-tenencia (un único rol/base, creados automáticamente por la imagen oficial al arrancar — no hace falta `create-postgres-db.sh` aquí). Aísla el radio de fallo de `postgres-main` sin añadir un nodo nuevo.

### C — Postgres dedicado en un nodo distinto

Aislamiento máximo (ni siquiera comparte nodo con `postgres-main`), pero exige planificar un servicio nuevo completo: sistema operativo, Docker, copias de seguridad, DNS/CA — coste operativo notable para un clúster de un solo operador, sin que el beneficio adicional (aislamiento a nivel de nodo, no solo de proceso) esté claramente justificado hoy. Descartada por desproporcionada — reevaluar si en el futuro `retaco` se convierte en un punto de fallo demasiado cargado.

## Decisión

**Opción B** — `postgres-infisical`, contenedor Postgres dedicado en `retaco`, sin multi-tenencia, sin compartir instancia con `postgres-main`.

## Consecuencias

**Positivas:**
- Un incidente de `postgres-main` (por cualquier motivo ajeno a Infisical) ya no tumba al gestor de secretos ni, en cascada, a los servicios que dependen de él para arrancar.
- Separación de responsabilidades más clara: `postgres-main` sigue siendo "el Postgres de las aplicaciones", `postgres-infisical` es infraestructura de seguridad, no una aplicación más.

**Negativas (aceptadas explícitamente):**
- Un contenedor más que mantener, actualizar y respaldar por separado — `bash shared/scripts/backup-postgres.sh retaco postgres-infisical infisical` (ya soportado, caso añadido al script existente, mismo mecanismo que `postgres-main`/`sonarqube-db`).
- Más uso de RAM/disco en `retaco` (un proceso Postgres adicional) — sin impacto medido relevante dado el margen de recursos del nodo (ver `docs/24-open-terminal-mcp.md`, ~10 GiB libres medidos en vivo antes de añadir servicios).
- La preocupación estructural del punto 1 (contraseña de arranque de la propia base de Infisical) sigue sin resolverse — no podía resolverse por diseño, ver arriba.

## Referencias

- `docs/22-mejoras-futuras.md`, mejora 16 — decisión Infisical vs Vault, incluye el problema del sellado que motiva el punto 1 de esta ADR.
- `docs/26-infisical-secretos.md` — despliegue completo, incluida la migración en vivo desde el primer intento (compartiendo `postgres-main`) a `postgres-infisical`.
- `docs/adr/0001-infisical-inyeccion-bind-mount-vs-imagen-derivada.md` — decisión relacionada pero distinta (cómo se inyectan los secretos en cada servicio migrado, no dónde vive el backend de Infisical).
