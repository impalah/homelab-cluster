# Imagen ligera con el cliente NUT (upsmon/upsc, sin los drivers USB que sí
# lleva pi-obs/nut-server/) para monitorizar el SAI remoto en pi-obs
# (192.168.1.171:3493) desde el resto de nodos y apagarlos limpio si el SAI
# ordena un apagado por batería crítica -- ver docs/33-nut-sai.md.
#
# Se construye LOCALMENTE en cada nodo consumidor (mismo criterio que
# pi-obs/nut-server/) -- Dockerfile trivial basado en apt, no compensa la
# complejidad de multi-arch + registry.404labo.net para esto, aunque corra
# tanto en nodos amd64 (ryzen, retaco, pinchi) como arm64 (pi-dns, pi-sonar,
# pi-utils).
FROM ubuntu:24.04

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        nut-client \
        gettext-base \
        dbus \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
