#!/bin/bash
# upsmon en modo "secondary" -- solo monitoriza el SAI remoto en pi-obs y
# apaga ESTE host si el SAI ordena un apagado por bateria critica. No
# gestiona ningun driver (eso solo existe en pi-obs/nut-server/).
set -eu

: "${NUT_MONUSER_PASSWORD:?falta NUT_MONUSER_PASSWORD}"

envsubst '${NUT_MONUSER_PASSWORD}' \
    < /etc/nut/upsmon.conf.template > /etc/nut/upsmon.conf
chown root:nut /etc/nut/upsmon.conf
chmod 640 /etc/nut/upsmon.conf

UPSMON_PID=""
term_handler() {
    echo "Senal de apagado recibida -- parando upsmon"
    if [ -n "${UPSMON_PID}" ]; then
        kill -TERM "${UPSMON_PID}" 2>/dev/null || true
        wait "${UPSMON_PID}" 2>/dev/null || true
    fi
    exit 0
}
trap term_handler TERM INT

upsmon -F &
UPSMON_PID=$!
wait "${UPSMON_PID}"
