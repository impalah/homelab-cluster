FROM ghcr.io/open-webui/open-terminal:slim

# open-webui/open-terminal (imagen oficial, ver https://github.com/open-webui/open-terminal)
# no incluye el extra opcional "[mcp]" (fastmcp) en ninguna de sus variantes
# publicadas (latest/slim/alpine/openshift) — confirmado leyendo Dockerfile y
# Dockerfile.slim: el "pip install ." del build no pide el extra. Además, la
# imagen slim/alpine desinstala pip a propósito al final del build (menos
# superficie/tamaño) y su entrypoint declara explícitamente que NO instala
# nada en caliente ("No runtime apt/pip package installation") — así que no
# hay forma de activar el modo MCP (subcomando "open-terminal mcp") solo con
# variables de entorno, hace falta añadir la dependencia en la imagen.
#
# Reinstalar pip temporalmente en vez de reconstruir la imagen entera desde
# las fuentes: sigue el tag "slim" oficial en cada rebuild sin duplicar su
# Dockerfile, y el único cambio real es una dependencia Python de más.
#
# "python3 -m pip", no el binario "pip" a secas: justo tras ensurepip, el
# script "pip" no queda en el PATH del shell (aunque el paquete se instale
# correctamente) — visto en un build real. Sin ningún "|| true" en la cadena:
# la primera versión de este Dockerfile llevaba uno al final pensado solo
# para el "pip uninstall", pero por precedencia de operadores enmascaraba
# también un fallo real del "pip install" anterior (el build "funcionaba"
# sin fastmcp instalado). Si algún paso falla de verdad, tiene que romper
# el build.
RUN python3 -m ensurepip --upgrade \
    && python3 -m pip install --no-cache-dir "fastmcp>=2.0.0" \
    && python3 -m pip uninstall -y pip setuptools

# El ENTRYPOINT (tini + entrypoint-slim.sh) y el resto de la imagen base se
# heredan tal cual — el modo MCP se activa vía "command:" en docker-compose
# (["mcp", "--transport", "streamable-http", ...]), no aquí, para no tener
# que reconstruir la imagen si algún día cambia solo el modo de arranque.
