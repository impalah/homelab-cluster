#!/bin/sh
# NOTIFYCMD de upsmon -- deja cada evento NUT (ONBATT, ONLINE, LOWBATT,
# FSD...) en stdout del contenedor, que Loki recoge igual que el resto del
# clúster (driver de logging `loki`, ver docs/04-servicios-comunes.md).
# Pendiente de conectar a un canal proactivo real (ntfy) en cuanto exista
# la mejora 4 (docs/22-mejoras-futuras.md) -- de momento solo queda en
# Loki/Grafana, sin push.
echo "$(date -Is) nut-notify: $*"
