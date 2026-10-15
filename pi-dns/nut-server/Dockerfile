# Imagen mínima con Network UPS Tools para el SAI (Salicru SPS 2200 SOHO+)
# conectado por USB a este nodo -- driver usbhid-ups, subdriver
# "Phoenixtec/Liebert HID" confirmado en vivo contra el hardware real (ver
# docs/33-nut-sai.md). Se construye y ejecuta SIEMPRE en pi-obs (arm64) --
# no se distribuye por registry.404labo.net, tiene un único consumidor
# (este mismo nodo), así que no hace falta el build multi-arch que sí
# necesitan apikey-service/markitdown-service.
FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        nut-server \
        nut-client \
        gettext-base \
        dbus \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
