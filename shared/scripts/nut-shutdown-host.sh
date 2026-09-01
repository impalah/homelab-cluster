#!/bin/sh
# SHUTDOWNCMD de upsmon -- se ejecuta DENTRO de un contenedor cuando el SAI
# ordena un apagado real (batería crítica), ver docs/33-nut-sai.md. Usa
# D-Bus (logind) sobre el socket del HOST compartido por bind-mount
# (/run/dbus/system_bus_socket) para apagar el sistema operativo REAL, no
# el contenedor -- root dentro del contenedor + socket D-Bus del host
# compartido basta para que logind acepte la orden sin polkit de por medio.
#
# Validado en vivo en un nodo de bajo riesgo (pinchi) antes de generalizarlo
# al resto -- si esto no apaga el host real en un nodo nuevo, revisar
# docs/33-nut-sai.md antes de asumir que "funciona en los demás" implica
# que funciona aquí también (permisos D-Bus, logind ausente, etc. pueden
# variar entre nodos).
set -e
echo "$(date -Is) nut-shutdown: SAI en batería crítica -- apagando el host real vía logind"
dbus-send --system --print-reply \
    --dest=org.freedesktop.login1 /org/freedesktop/login1 \
    org.freedesktop.login1.Manager.PowerOff boolean:true
