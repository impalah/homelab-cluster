#!/bin/bash
# Arranca los 3 procesos NUT (driver usbhid-ups, upsd, upsmon local en modo
# "primary") en un solo contenedor -- están fuertemente acoplados (el
# driver y upsd se hablan por socket en /run/nut, efímero por diseño, no se
# persiste entre reinicios del contenedor) y siempre corren en el mismo
# nodo físico, así que no aporta nada separarlos en contenedores distintos.
set -eu

: "${NUT_MONUSER_PASSWORD:?falta NUT_MONUSER_PASSWORD}"
: "${NUT_ADMIN_PASSWORD:?falta NUT_ADMIN_PASSWORD}"

envsubst '${NUT_MONUSER_PASSWORD} ${NUT_ADMIN_PASSWORD}' \
    < /etc/nut/upsd.users.template > /etc/nut/upsd.users
chown root:nut /etc/nut/upsd.users
chmod 640 /etc/nut/upsd.users

envsubst '${NUT_MONUSER_PASSWORD}' \
    < /etc/nut/upsmon.conf.template > /etc/nut/upsmon.conf
chown root:nut /etc/nut/upsmon.conf
chmod 640 /etc/nut/upsmon.conf

upsdrvctl start

# -u root: mismo motivo que "user = root" en ups.conf -- ver comentario ahi.
upsd -u root

UPSMON_PID=""
term_handler() {
    echo "Señal de apagado recibida -- parando NUT limpio"
    if [ -n "${UPSMON_PID}" ]; then
        kill -TERM "${UPSMON_PID}" 2>/dev/null || true
        wait "${UPSMON_PID}" 2>/dev/null || true
    fi
    upsd -c stop || true
    upsdrvctl stop || true
    exit 0
}
trap term_handler TERM INT

upsmon -F &
UPSMON_PID=$!
wait "${UPSMON_PID}"
