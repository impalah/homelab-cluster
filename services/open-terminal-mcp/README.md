# open-terminal-mcp

Envoltorio de una sola línea real sobre la imagen oficial [`ghcr.io/open-webui/open-terminal:slim`](https://github.com/open-webui/open-terminal), que añade el extra opcional `[mcp]` (`fastmcp>=2.0.0`) — la imagen oficial no lo trae en ninguna variante publicada, así que el subcomando `open-terminal mcp` no arranca sin esto. Ver `Dockerfile` para el detalle completo.

No hay código propio aquí, solo la capa que falta para exponer Open Terminal como servidor **MCP** (transporte `streamable-http`) en vez de su API REST normal — mejora 17 de `docs/22-mejoras-futuras.md`, desplegado en `retaco` como `open-terminal-mcp` (ver `retaco/docker-compose.yml`) y documentado en `docs/24-open-terminal-mcp.md`.

## Build y publicación

```bash
cp .env.example .env   # credenciales del registry, ver Vaultwarden
make build              # login + build + push a registry.home.arpa/open-terminal-mcp:latest
```

## Aviso de seguridad importante

`OPEN_TERMINAL_API_KEY` protege la API REST propia de Open Terminal, pero **no** el servidor MCP: `open_terminal/mcp_server.py` construye el `FastMCP` sin ningún proveedor de autenticación (`FastMCP.from_fastapi(app=app, ...)`, sin `auth=`), así que cualquier cliente que alcance el puerto en modo `mcp --transport streamable-http` tiene shell y sistema de ficheros completos, sin credencial de ningún tipo. Por eso este servicio **nunca** se expone directamente — va siempre detrás de `nginx` + `apikey-service` (`X-Api-Key`) en `pi-dns`, nunca con el puerto publicado a la LAN sin esa capa delante. Ver `docs/24-open-terminal-mcp.md` para el razonamiento completo y cómo se verificó.
