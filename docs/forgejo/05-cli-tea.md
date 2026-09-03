# 05 — La CLI `tea`

[`tea`](https://gitea.com/gitea/tea) es la CLI oficial de Gitea/Forgejo — el equivalente directo al `gh` de GitHub o al `glab` de GitLab. Permite gestionar repositorios, incidencias, pull requests, releases, webhooks y más sin salir de la terminal, y hablando con la API de esta instancia (`https://forgejo.404labo.net`), no con un servicio externo. Todos los comandos de este documento son reales, ejecutados contra `impalah/proyecto-demo` en esta instancia — no son un ejemplo inventado.

## Instalación

`tea` se distribuye como binario estático — no hace falta compilarlo ni tener Go instalado.

**Linux (x86_64), descarga directa** (mismo patrón que se usó para escribir este manual):

```bash
curl -sL -o tea "https://gitea.com/gitea/tea/releases/download/v0.15.1/tea-0.15.1-linux-amd64"
chmod +x tea
sudo mv tea /usr/local/bin/tea   # o cualquier directorio en tu $PATH
```

Comprueba la versión más reciente en <https://gitea.com/gitea/tea/releases> antes de fijar la URL — la de arriba (v0.15.1) es la usada al escribir este manual (2026-09-03), pero `tea` recibe actualizaciones con cierta frecuencia.

**Otras plataformas**: hay binarios para `linux-arm64`/`linux-arm-*` (útiles si trabajas desde uno de los nodos Raspberry Pi del clúster, `docs/01-topologia.md`), `darwin-amd64`/`darwin-arm64` (macOS), `windows-amd64.exe` y `freebsd-amd64` en la misma página de releases. También existe como paquete en algunos gestores de distribución (`brew install tea` en macOS/Linuxbrew, `scoop install tea` en Windows) si prefieres no gestionar el binario a mano.

Verifica la instalación:

```bash
$ tea --version
Version: 0.15.1    golang: 1.26.5    go-sdk: v1.2.0
```

## Autenticarse

`tea` necesita un token de acceso (documento 01, sección "Tokens de acceso") — nunca tu contraseña.

```bash
$ tea login add --name homelab --url https://forgejo.404labo.net --token <tu-token>
Login as impalah on https://forgejo.404labo.net successful. Added this login as homelab
Tip: pass --git-credentials (or run 'tea login helper setup') to authenticate 'git push' and 'git clone' over HTTPS with this token.
```

`--name` es solo una etiqueta local (útil si algún día gestionas más de una instancia Forgejo/Gitea desde la misma máquina). El aviso final es una comodidad opcional: `tea login helper setup` configura Git para usar el mismo token también en clones HTTPS — no necesario si ya usas SSH (documento 01), como en el resto de este manual.

```bash
$ tea login list
┌─────────┬─────────────────────────────┬──────────────────────┬─────────┬─────────┐
│  NAME   │             URL             │       SSH HOST       │  USER   │ DEFAULT │
├─────────┼─────────────────────────────┼───────────────────────┼─────────┼─────────┤
│ homelab │ https://forgejo.404labo.net │ forgejo.404labo.net  │ impalah │ false   │
└─────────┴─────────────────────────────┴───────────────────────┴─────────┴─────────┘

$ tea login default homelab   # evita tener que pasar --login en cada comando si solo usas una instancia

$ tea whoami
  # impalah (admin)
  Follower Count: 0, Following Count: 0, Starred Repos: 0
```

El token queda guardado en `$XDG_CONFIG_HOME/tea/config.yml` (normalmente `~/.config/tea/config.yml`) — mismo criterio de cualquier credencial local: permisos de fichero restrictivos, nunca en un repositorio.

## Uso — `tea` detecta el repositorio actual

Dentro de un clon local de un repositorio Forgejo, `tea` detecta automáticamente contra qué instancia/repo trabajar leyendo el remoto Git — no hace falta repetir `--repo owner/nombre` en cada comando si ya estás dentro del clon.

### Repositorios

```bash
$ tea repos list --login homelab
┌─────────┬───────────────┬────────┬────────────────────────────────────────────────────────────┐
│  OWNER  │     NAME      │  TYPE  │                              SSH                              │
├─────────┼───────────────┼────────┼────────────────────────────────────────────────────────────┤
│ impalah │ proyecto-demo │ source │ ssh://git@forgejo.404labo.net:2222/impalah/proyecto-demo.git │
└─────────┴───────────────┴────────┴────────────────────────────────────────────────────────────┘
```

### Incidencias

```bash
$ cd proyecto-demo
$ tea issues create \
    --title "Documentar los ejemplos de saludo.py" \
    --description "Falta un README mas detallado con ejemplos de uso de cada funcion."

  # #4 Documentar los ejemplos de saludo.py (open)
  @impalah created 2026-09-03 16:43
  Falta un README mas detallado con ejemplos de uso de cada funcion.

https://forgejo.404labo.net/impalah/proyecto-demo/issues/4

$ tea issues
┌───────┬───────────────────────────────────────┬───────┬─────────┬───────────┬────────┬─────────┬───────────────┐
│ INDEX │                 TITLE                  │ STATE │ AUTHOR  │ MILESTONE │ LABELS │  OWNER  │     REPO      │
├───────┼───────────────────────────────────────┼───────┼─────────┼───────────┼────────┼─────────┼───────────────┤
│ 4     │ Documentar los ejemplos de saludo.py   │ open  │ impalah │           │        │ impalah │ proyecto-demo │
└───────┴───────────────────────────────────────┴───────┴─────────┴───────────┴────────┴─────────┴───────────────┘
```

`tea issues` sin argumentos lista solo las abiertas del repo actual; `tea issues --state all` incluye las cerradas; `tea issue <N>` (singular) muestra el detalle completo de una, con sus comentarios.

### Pull requests — el ciclo completo por CLI

Sin salir nunca de la terminal: crear rama y commit con Git normal, luego crear y fusionar la PR con `tea`.

```bash
$ git checkout -b docs/ejemplos-saludo main
$ # ... editar README.md ...
$ git add README.md
$ git commit -m "Documentar ejemplos de uso en el README

Closes #4"
$ git push -u origin docs/ejemplos-saludo

$ tea pr create --title "Documentar ejemplos de uso" --description "Closes #4" \
    --head docs/ejemplos-saludo --base main

  # #5 Documentar ejemplos de uso (open)
  @impalah created 2026-09-03 16:43    main <- docs/ejemplos-saludo
  Closes #4
  --------
  • No Conflicts
https://forgejo.404labo.net/impalah/proyecto-demo/pulls/5

$ tea pr merge 5

$ tea pulls --state all
┌───────┬───────────────────────────────────┬────────┬─────────┬───────────┬───────────────────┬────────┐
│ INDEX │               TITLE                │ STATE  │ AUTHOR  │ MILESTONE │      UPDATED       │ LABELS │
├───────┼───────────────────────────────────┼────────┼─────────┼───────────┼───────────────────┼────────┤
│ 5     │ Documentar ejemplos de uso         │ merged │ impalah │           │ 2026-09-03 16:43   │        │
│ 3     │ Validar nombre vacio en saludo()   │ merged │ impalah │           │ 2026-09-03 16:36   │        │
│ 1     │ Añadir función de despedida        │ merged │ impalah │           │ 2026-09-03 16:37   │        │
└───────┴───────────────────────────────────┴────────┴─────────┴───────────┴───────────────────┴────────┘
```

`"No Conflicts"` en la salida de `tea pr create` es la propia CLI confirmando de antemano que la fusión no tendrá conflictos — la misma comprobación que se ve en la UI web (documento 04). Si los hubiera, `tea pr create` sigue creando la PR igualmente (la comprobación es informativa), pero `tea pr merge` fallaría hasta resolverlos — el flujo de resolución sigue siendo el mismo que por Git normal (documento 06), `tea` no tiene un resolutor de conflictos propio.

### Claves SSH — también gestionables por CLI

```bash
$ tea ssh-keys
┌────┬──────────────────────┬───────────────────────────────────────────────────┬──────────┬───────────┬──────────────────┐
│ ID │         TITLE         │                     FINGERPRINT                     │ KEY TYPE │ READ ONLY │     CREATED      │
├────┼──────────────────────┼───────────────────────────────────────────────────┼──────────┼───────────┼──────────────────┤
│ 1  │ demo-manual-forgejo  │ SHA256:AYTrL58FTrEd31kNp7uitmKJZUuQShvsjjk2bHyDZ/I │ user     │ false     │ 2026-09-03 16:20 │
└────┴──────────────────────┴───────────────────────────────────────────────────┴──────────┴───────────┴──────────────────┘
```

`tea ssh-keys add --title "nombre" --pub-key "$(cat ~/.ssh/mi_clave.pub)"` añade una nueva sin pasar por la web — útil para provisionar claves desde un script (por ejemplo, al dar de alta un runner de CI en el futuro).

## Otros comandos útiles

| Comando | Qué hace |
|---|---|
| `tea clone owner/repo` | Como `git clone`, pero resuelve la URL sola a partir del nombre corto `owner/repo` |
| `tea open` | Abre en el navegador la página del repositorio actual (o de una PR/incidencia concreta con `tea open <N>`) |
| `tea labels` | Lista/crea etiquetas del repo — el equivalente CLI del documento 03, sección de etiquetas |
| `tea milestones` | Gestión de hitos |
| `tea releases` | Crear/listar releases (versiones publicadas, con binarios adjuntos si aplica) |
| `tea comment <issue/pr> "texto"` | Añade un comentario sin abrir el navegador |
| `tea api <ruta>` | Llamada autenticada directa a la API REST de Forgejo, para lo que no cubre ningún subcomando de más arriba — `tea api /repos/impalah/proyecto-demo` por ejemplo |
| `tea notifications` | Lista tus notificaciones pendientes (menciones, PRs asignadas...) |

`tea <comando> --help` en cualquier nivel documenta las opciones completas — la CLI es exhaustiva, este documento cubre el 80 % de uso diario, no el catálogo entero.

## Siguiente paso

`tea` cubre el lado Forgejo del flujo — para el lado Git puro (qué hacer cuando algo sale mal, cómo deshacer un lío sin perder trabajo), sigue con [06-git-guia-practica.md](06-git-guia-practica.md).
