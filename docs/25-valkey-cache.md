# 25 — Valkey: caché clave-valor compartido del clúster

## Qué es y por qué está aquí

Mejora 24 del backlog (`docs/22-mejoras-futuras.md`): no existía ningún almacén clave-valor ni sistema de pub/sub de propósito general en el clúster. Se despliega hoy sin ningún consumidor real todavía — la mejora 16 (Infisical) sería el primer candidato natural si se implementa, pero no depende de este documento.

## Valkey, no Redis — no son dos productos complementarios

Valkey es un *fork* de Redis (mismo protocolo RESP, mismos comandos, mismas librerías cliente), nacido cuando Redis Inc. cambió la licencia de las versiones ≥ 7.4 a SSPLv1/RSALv2 — licencias no reconocidas por la OSI que restringen ofrecer Redis como servicio a terceros. Se despliega Valkey en solitario: licencia BSD-3 real, mantenido por la Linux Foundation con AWS/Google/Oracle detrás, 100 % compatible con cualquier librería cliente de Redis — mismo criterio "FOSS de verdad" ya aplicado en este proyecto a Infisical sobre HashiCorp Vault y a Forgejo autoalojado con GitHub como espejo.

## Despliegue

`retaco/docker-compose.yml`, servicio `valkey`:

```yaml
valkey:
  image: valkey/valkey:9.1.1-alpine
  container_name: valkey
  restart: unless-stopped
  command: >
    valkey-server
    --aclfile /etc/valkey/users.acl
    --save ""
    --appendonly no
    --maxmemory 256mb
    --maxmemory-policy allkeys-lru
  volumes:
    - /srv/homelab/retaco/valkey/users.acl:/etc/valkey/users.acl:ro
  ports:
    - "6379:6379"
  networks:
    - retaco-net
```

- **Nodo**: `retaco` — ya aloja `postgres-main`, Qdrant y el registry.
- **Sin persistencia a propósito** (`--save ""`, `--appendonly no`): uso previsto hoy es solo caché, sin consumidor real todavía — el contenido se pierde en cada reinicio del contenedor. Si en el futuro un consumidor necesita persistir datos de verdad, activar AOF/RDB entonces (y añadirlo a la estrategia de backups, `shared/scripts/backup-postgres.sh` o un script hermano).
- **Límite de memoria**: 256 MB con política `allkeys-lru` (evict de las keys menos usadas recientemente al llenarse) — correcta para un caché puro, a diferencia del `noeviction` por defecto de Redis/Valkey (que simplemente empezaría a rechazar escrituras al llenarse). Generoso para el uso actual (cero consumidores), fácil de subir cuando haga falta.
- **Puerto publicado a la LAN**, como `postgres-main`/Qdrant — expuesto como `valkey.home.arpa` (alias DNS directo, ver más abajo). Protegido por la ACL (usuario `default` desactivado), no por aislamiento de red — mismo criterio que `postgresql.home.arpa`.

### TLS — certificado propio firmado por la CA interna

El puerto se publicó primero sin TLS (contraseña en claro para cualquier cliente cross-host) y se activó después, aprovechando que ya existe la CA interna del clúster (`docs/15-ca-interna.md`) — sin ella habría sido bastante más trabajo.

- **Clave y certificado propios de Valkey**, no compartidos con los de nginx — generados con `pi-dns/config/nginx/generate-valkey-cert.sh` (se ejecuta en `pi-dns`, porque necesita `ca.key`, que nunca sale de ahí) y copiados a `retaco:/srv/homelab/retaco/valkey/tls/` (`valkey.crt`, `valkey.key`, `ca.crt`) con el patrón habitual de despliegue.
- **`--port 0` + `--tls-port 6379`**: desactiva el puerto en claro por completo — no coexisten ambos, solo se acepta TLS. Confirmado en vivo: un cliente sin `--tls` recibe `Connection reset by peer`.
- **`--tls-auth-clients no`**: TLS aquí es solo para cifrar el transporte, no exige certificado de cliente — la autenticación la sigue haciendo la ACL (usuario/contraseña), no un cliente TLS mutuo.
- Regenerar el certificado (rutina, no afecta a la CA): `bash pi-dns/config/nginx/generate-valkey-cert.sh` en `pi-dns`, copiar el resultado a `retaco`, `docker compose up -d valkey` (recrea el contenedor, recoge el certificado nuevo).

## Seguridad — ACL, no `requirepass` a secas

`retaco/config/valkey/users.acl` (no versionado — mismo criterio que `.env`, plantilla en `users.acl.example`):

```
user default off
user valkey-admin on >{contraseña generada con openssl rand -hex 32} ~* &* +@all
```

- Usuario `default` **desactivado** — sin esto, cualquiera que alcance el puerto entra sin contraseña (comportamiento por defecto de Redis/Valkey).
- Un único usuario `valkey-admin` con acceso completo (`~*` todas las keys, `&*` todos los canales, `+@all` todos los comandos), pensado para pruebas y gestión — no para que lo use ningún servicio consumidor directamente.
- Cuando aparezca un consumidor real, crear un usuario propio y restringido (`ACL SETUSER`), por ejemplo:
  ```
  ACL SETUSER infisical on >otra_contraseña ~infisical:* &infisical:* +@read +@write -@dangerous
  ```
  y guardarlo en `users.acl` (no solo en memoria vía `ACL SETUSER` — se perdería al reiniciar el contenedor sin `ACL SAVE`, y `ACL SAVE` requiere que `aclfile` sea escribible, hoy montado `:ro` a propósito).

⚠️ **El fichero `aclfile` no admite comentarios** (`#`) en esta versión de Valkey (9.1.1) — cualquier línea que no empiece literalmente por `user` rompe el arranque con `should start with user keyword followed by the username`. Confirmado en el despliegue real: la primera versión del fichero, con comentarios explicativos como en el resto de configs de este repo, hizo que el contenedor entrara en crash-loop. `users.acl`/`users.acl.example` se mantienen deliberadamente sin comentarios — la documentación vive aquí, no en el propio fichero.

## Nombre DNS — `valkey.home.arpa`

Alias directo (sin nginx, RESP no es HTTP) a `192.168.1.174:6379`, mismo patrón que `postgresql.home.arpa` — ver `shared/dns/dns-records.md`. Añadido a `shared/scripts/load-dns-records.sh` y aplicado en Pi-hole.

## Prueba manual — verificado en el despliegue real

Local (dentro del contenedor, vía `docker exec` — TLS obligatorio desde que se activó, `--port 0` desactivó el puerto en claro):

```bash
docker exec valkey valkey-cli --tls --cacert /etc/valkey/tls/ca.crt PING
# → NOAUTH Authentication required.

docker exec valkey valkey-cli --tls --cacert /etc/valkey/tls/ca.crt --user valkey-admin --pass <contraseña> PING
# → PONG
docker exec valkey valkey-cli --tls --cacert /etc/valkey/tls/ca.crt --user valkey-admin --pass <contraseña> ACL LIST
# → user default off sanitize-payload resetchannels -@all
#   user valkey-admin on sanitize-payload #<hash> ~* &* +@all
```

Confirmado también: `CONFIG GET save` vacío, `CONFIG GET appendonly` → `no`, `CONFIG GET maxmemory` → `268435456` (256 MB), `CONFIG GET maxmemory-policy` → `allkeys-lru`.

Cross-host, desde `ryzen`/`mole`, vía DNS real (no `--resolve`/IP a mano):

```bash
# Sin --tls → rechazado de raíz, ya no hay puerto en claro
valkey-cli -h valkey.home.arpa -p 6379 PING
# → Error: Connection reset by peer

# Con --tls, verificando el certificado contra la CA interna
valkey-cli -h valkey.home.arpa -p 6379 --tls --cacert ca.crt --user valkey-admin --pass <contraseña> PING
# → PONG
```

## Añadir un consumidor nuevo — procedimiento

1. Generar contraseña: `openssl rand -hex 32`.
2. Añadir una línea `user <nombre> on >contraseña ~<prefijo>:* &<prefijo>:* +@read +@write -@dangerous` a `retaco/config/valkey/users.acl` (sin comentarios, ver aviso arriba) y desplegarla con el patrón habitual (`rsync` a `/tmp` + `sudo cp` a `/srv/homelab/retaco/valkey/users.acl`, ver `CLAUDE.md`/`docs/01-topologia.md`).
3. Recargar sin reiniciar el contenedor: `docker exec valkey valkey-cli --user valkey-admin --pass <admin> ACL LOAD`.
4. Guardar la contraseña del consumidor en Vaultwarden, igual que el resto de credenciales del clúster.

⚠️ **`ACL LOAD` es aditivo, no sincroniza** — comprobado en vivo: quitar una línea de `users.acl` y ejecutar `ACL LOAD` **no** elimina ese usuario, sigue activo en memoria. Para borrar uno de verdad hace falta `ACL DELUSER <nombre>` explícito, además de quitar la línea del fichero (para que no reaparezca en un reinicio completo del contenedor, que sí relee el fichero desde cero).
