# ADR 0001 — Inyección de secretos de Infisical: bind-mount + `entrypoint`, no imagen derivada

**Estado**: aceptada
**Fecha**: 2026-08-09
**Contexto**: mejora 16 del backlog (`docs/22-mejoras-futuras.md`), desarrollada en `docs/26-infisical-secretos.md`

## Contexto

Infisical no tiene ningún mecanismo nativo de inyección de secretos para Docker Compose (a diferencia de Kubernetes, donde sí existen un Operator y un Agent Injector). El patrón recomendado por el propio proyecto para Compose es envolver el proceso real de cada contenedor con su CLI: `infisical run --env=<entorno> -- <comando original>` — el CLI resuelve los secretos del proyecto/entorno vía API, los inyecta como variables de entorno del proceso hijo y hace `exec` de él, de forma que la aplicación nunca sabe que los secretos vinieron de Infisical.

Para que eso funcione, el binario `infisical` tiene que existir dentro del contenedor en el momento de arrancar. Hace falta decidir **cómo llega ahí**, de forma consistente para los ~10 servicios candidatos a migrar — tanto propios (`apikey-service`, `markitdown-service`, `epub2pdf-service`...) como de terceros sin `Dockerfile` propio (`postgres-main`, `n8n-main`, `qdrant`, `vaultwarden`, `grafana`...).

## Alternativas consideradas

### A — CLI horneado en la imagen (`Dockerfile` propio o wrapper fino)

Añadir `COPY --from=infisical/cli:latest /usr/local/bin/infisical /usr/local/bin/infisical` al `Dockerfile` de cada servicio propio, y para servicios de terceros crear una imagen derivada fina (`FROM <imagen-original>` + el mismo `COPY` + `ENTRYPOINT` reescrito) publicada en `registry.home.arpa`, construida con el mismo `docker buildx build --platform linux/amd64,linux/arm64 --push` que ya usan los microservicios propios (`docs/05-instalacion-retaco.md` sección 5.3).

Descartada: subir la versión del CLI de Infisical — sin haber tocado una sola línea de código de la aplicación — habría exigido reconstruir y republicar la imagen de cada servicio migrado. Para servicios de terceros habría supuesto además mantener y sincronizar un `Dockerfile` wrapper propio por cada uno, divergiendo de la imagen oficial upstream (hay que rehacer el wrapper cada vez que el proyecto original cambia su entrypoint). Rompe el flujo de actualización que ya usa el resto del clúster — `docker compose pull` + `watchtower`/`update-stack.sh`, sin reconstrucción — acoplando el ciclo de vida del CLI de Infisical al de cada aplicación.

### B — Binario estático por nodo + bind-mount + override de `entrypoint:` en Compose (elegida)

Un binario estático de la release oficial de `infisical` por nodo, guardado en `/srv/homelab/<nodo>/infisical-cli/infisical` (misma convención de rutas que el resto del repo, `docs/01-topologia.md`), montado de solo lectura en el servicio a migrar, con `entrypoint:` sobreescrito en el `docker-compose.yml` de ese nodo:

```yaml
volumes:
  - /srv/homelab/<nodo>/infisical-cli/infisical:/usr/local/bin/infisical:ro
entrypoint: ["/usr/local/bin/infisical", "run", "--env=prod", "--", <entrypoint-original-de-la-imagen>]
```

Sin `command:` — Compose sigue pasando el `CMD` original de la imagen como argumento al nuevo entrypoint, así que no hace falta duplicarlo ni mantenerlo sincronizado si cambia en una versión futura de la imagen.

Funciona exactamente igual para un servicio propio que para uno de terceros: ninguna imagen se toca, ninguna se reconstruye.

> **Actualización tras la migración real de `apikey-service`** (primer servicio migrado, `docs/26-infisical-secretos.md`): el `entrypoint:` de una sola línea de arriba es el caso ideal, pero en la práctica, con la versión del CLI desplegada (0.43.121), `infisical run` no acepta autenticación por Universal Auth vía variables de entorno directamente — hace falta un paso previo `infisical login --method=universal-auth` que devuelve un token de corta duración, pasado después a `infisical run --token=...`. Eso obliga a `entrypoint: ["/bin/sh", "-c"]` + un `command:` con el script de dos pasos **y** el arranque real del servicio escrito explícito (ya no se hereda el `CMD` de la imagen, al reemplazar el entrypoint por un shell). Sigue cumpliéndose lo importante de esta ADR — ninguna imagen se toca ni se reconstruye — pero el "sin `command:`" de la sección B es el caso simple, no el real. Ver el bloque `apikey-service` en `pi-dns/docker-compose.yml` para el patrón completo a reutilizar en el resto de servicios.

## Decisión

**Opción B, siempre, sin excepción por tipo de servicio.** No se hornea el CLI en ninguna imagen, propia o de terceros.

## Consecuencias

**Positivas:**
- Cero reconstrucciones de imagen ligadas a Infisical — actualizar un servicio migrado a una versión nueva de su propia aplicación sigue siendo `docker compose pull && up -d`, ajeno del todo a este sistema de secretos.
- Mismo mecanismo para servicios propios y de terceros — no hay que decidir caso a caso ni mantener wrappers derivados que diverjan de la imagen oficial upstream.
- El binario vive bajo `/srv/homelab/<nodo>/`, no contamina el sistema operativo del host (nada de paquetes ni repositorios apt/yum añadidos).

**Negativas (aceptadas explícitamente):**
- Actualizar la versión del propio CLI de Infisical exige tocar cada nodo a mano — descargar el binario nuevo con `shared/scripts/deploy-infisical-cli.sh <nodo>` y recrear (no solo reiniciar: problema de inodo ya documentado en `docs/01-topologia.md`) los contenedores que lo montan. No se beneficia de Watchtower/`update-stack.sh` como el resto de imágenes del clúster.
- Cada servicio de terceros que se quiera migrar exige averiguar su `ENTRYPOINT`/`CMD` real (`docker inspect --format='{{.Config.Entrypoint}} {{.Config.Cmd}}' <imagen>`) antes de sobreescribirlo, para no romper su arranque — trabajo puntual por servicio, no automatizable de forma genérica.
- Para servicios con estado (Postgres, Qdrant), conviene verificar en vivo que `infisical run` hace `exec` real del proceso hijo (sustituye el PID, no lo envuelve), para que el apagado ordenado (señales) siga funcionando igual — no asumido a ciegas antes de migrar un servicio con datos reales.
- **Confirmado en la migración real de `apikey-service`**: el CLI (binario Go) no confía en la CA interna del clúster por defecto — cualquier imagen que no la tenga instalada de fábrica necesita, además del binario, un bind-mount del certificado de la CA y la variable `SSL_CERT_FILE` apuntando a él (Go respeta esa variable de forma nativa, sin tener que instalar el certificado a nivel de sistema operativo ni reconstruir nada). Un paso más a repetir en cada servicio migrado, documentado en `docs/26-infisical-secretos.md`.
- **También confirmado**: si Infisical está caído en el momento exacto en que un servicio migrado necesita (re)arrancar, ese servicio no puede arrancar hasta que Infisical vuelva — probado apagando Infisical con `apikey-service` ya en marcha (sigue funcionando, no necesita reinyectar nada mientras no se reinicie) y forzando después un reinicio de `apikey-service` con Infisical aún caído (se queda reintentando en bucle, `restart: unless-stopped` lo recupera solo en cuanto Infisical vuelve, sin intervención manual). Es exactamente el trade-off ya anticipado en `docs/22`, mejora 16, punto 5 — aquí queda confirmado en vivo, no solo en teoría.
- **Confirmado migrando los 9 servicios de la mejora 28** (2026-08-19, detalle completo en `docs/26-infisical-secretos.md`): el nombre de la clave del secreto en Infisical tiene que coincidir con el nombre de variable que la aplicación real consume — el volcado masivo original importó cada `.env` tal cual, con los nombres (a veces con prefijo de servicio/nodo) que usaba ESTE repo, no necesariamente los que la app espera de fábrica (p. ej. `N8N_DB_PASSWORD` en el `.env` vs `DB_POSTGRESDB_PASSWORD` que realmente lee n8n). Hubo que renombrar claves en 6 de los 9 servicios antes de conectar el wrapper. Un healthcheck que referencie un secreto migrado directamente (`$$ALGUNA_VAR`) también deja de funcionar tal cual: `docker exec` (que es como Compose ejecuta el healthcheck) no ve el entorno dinámico de PID 1 tras el `exec` de `infisical run`, solo el entorno estático con el que se creó el contenedor.

## Referencias

- `docs/22-mejoras-futuras.md`, mejora 16 — decisión Infisical vs Vault.
- `docs/26-infisical-secretos.md` — despliegue, procedimiento de migración, estado actual.
- `docs/24-open-terminal-mcp.md` — precedente de "imagen oficial no trae algo que necesitamos, se envuelve con una capa fina propia", considerado y descartado aquí por el coste de reconstrucción (ver Alternativa A).
