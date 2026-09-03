# 03 — Recorrido por los dashboards ya desplegados

Antes de crear nada propio (documento 04), vale la pena conocer lo que ya existe — cubre la mayoría de preguntas del día a día sobre el clúster. Todos son accesibles desde **Dashboards** en la barra lateral:

![Lista de dashboards](../assets/grafana-manual/04-dashboards-lista.jpg)

Dos carpetas (`Homelab`, con el dashboard propio del clúster; `Homelab Alerts`, donde viven las reglas de alerta — ver documento 05) y cuatro dashboards importados de la comunidad de Grafana.com, sueltos sin carpeta.

## Node Exporter Full

El dashboard de referencia para la salud de un nodo: CPU, RAM, disco, red, procesos, temperatura... Un selector arriba a la izquierda (**Job**) elige de qué nodo se están viendo los datos:

![Node Exporter Full](../assets/grafana-manual/05-node-exporter-full.jpg)

Al hacer clic en el selector aparecen los 7 nodos del clúster (los 6 "de siempre" más `pinchi`):

![Selector de nodo en Node Exporter Full](../assets/grafana-manual/06-node-exporter-selector-nodo.jpg)

Úsalo para preguntas del tipo "¿por qué `ryzen` va lento ahora mismo?" o "¿cuánto disco le queda a `pi-sonar`?".

## Docker monitoring (cAdvisor)

Vista agregada de **todos los contenedores del clúster** — cuántos están corriendo, memoria/CPU/red totales, con filtros por Job/Service/Host/Container arriba:

![Docker monitoring](../assets/grafana-manual/07-docker-monitoring.jpg)

Útil para preguntas de conjunto ("¿ha subido el consumo de memoria de golpe?") más que para depurar un contenedor concreto — para eso, mejor Explore con Loki (documento 02) o el propio `docker service logs` por SSH.

## PostgreSQL Database

Métricas de `postgres-main` (el Postgres compartido por casi todo el clúster: n8n, SonarQube, authentik, apikey-service, Capataz...), desglosadas **por base de datos**:

![PostgreSQL Database](../assets/grafana-manual/08-postgresql-database.jpg)

Sesiones activas, transacciones, filas leídas/escritas — todo separado por base (`bifrost`, `authentik`, `n8n`, `sonarqube`...), lo que permite ver de un vistazo qué servicio está generando más carga sobre la base de datos compartida.

## Actualizaciones pendientes (propio del clúster)

El único dashboard construido específicamente para este homelab, no importado — carpeta `Homelab`. Combina dos vigilancias distintas (mejoras 6/8 y 36 del backlog, `docs/16-mantenimiento-actualizaciones.md`): imágenes Docker con una versión más nueva disponible en el registro, y parcheo de sistema operativo pendiente por nodo:

![Actualizaciones pendientes](../assets/grafana-manual/09-actualizaciones-pendientes.jpg)

La tabla "Detalle por contenedor" es útil para saber, contenedor a contenedor, si la imagen que corre hoy es la más reciente publicada. La sección inferior ("Parcheo del sistema operativo por nodo") muestra actualizaciones de seguridad de `apt` pendientes y si un nodo tiene un reinicio pendiente — ambas alimentan las alertas del documento 05.

## Servicio (genérico) — una vista por servicio, embebible por URL

Segundo dashboard propio del clúster, carpeta `Homelab` (mejora 45 del backlog, `docs/22-mejoras-futuras.md`) — en vez de un dashboard por cada uno de los ~38 servicios reales (25 stacks de Swarm más los contenedores de Compose clásico de los 6 nodos, incluido `ryzen`), una única plantilla parametrizable con el desplegable **Servicio** arriba: contenedores activos, reinicios recientes, uptime, CPU/memoria/red y logs (volumen + crudo), todo filtrado al servicio elegido.

Funciona igual para un stack de Swarm que para un contenedor de Compose clásico sin que haga falta saber cuál es cada uno — cada panel combina ambos esquemas de etiqueta internamente. La lista del desplegable es una lista fija mantenida a mano en el JSON (`pi-obs/config/grafana/dashboards/json/servicio-generico.json`), no derivada en vivo — un servicio nuevo no aparece solo.

**Embebido por iframe**, el caso de uso que motivó este diseño: la URL admite el valor de la variable como parámetro, sin necesidad de abrir el dashboard a mano primero —

```
https://grafana.404labo.net/d/homelab-servicio-generico/servicio-generico?orgId=1&var-servicio=infisical&kiosk
```

Cambiar `var-servicio=<nombre>` selecciona el servicio; `&kiosk` oculta la barra lateral y las cabeceras de Grafana, útil para un `<iframe>` embebido en otra página. Un panel embebido así respeta igualmente que Grafana esté solo en LAN/Tailscale (documento 00) — la página que lo embeba tiene que poder alcanzar `grafana.404labo.net`, no hay forma de saltarse eso desde fuera.

## apikey-service — el único con auditoría propia (OTLP)

Tercer dashboard propio del clúster, carpeta `Homelab` (mejora 45) — a diferencia de la plantilla genérica, este es a medida: `apikey-service` es el único servicio que manda registros estructurados por OTLP (`docs/01-topologia.md`), con el motivo exacto de cada validación fallida y la IP del peer que la hizo. Paneles: tasa de fallos en el tiempo, motivo del fallo, top de IPs de origen (la IP del peer TCP inmediato dentro de la red de Traefik, no necesariamente el cliente externo real — anotado en el propio panel), más CPU/memoria y el log crudo. Pese a que la documentación decía que también manda trazas por OTLP, se comprobó en vivo que Tempo no tiene ningún trace real almacenado — no hay panel de trazas por ese motivo, para no mostrar algo vacío.

## Qdrant — recursos, logs y métricas nativas reales

Cuarto dashboard propio (mejora 45) — CPU/memoria/red/logs del contenedor (`retaco`, único nodo donde corre) más las métricas propias de Qdrant, vía su `/metrics` real de Prometheus (protegido con una API key de solo lectura, conectado como un secret de Swarm dedicado): colecciones, puntos y vectores por colección (`articles`/`transcripts`), memoria real del proceso (comparada en el mismo panel con la del cgroup que reporta cAdvisor, por si divergen), cola de actualizaciones pendiente y versión de Qdrant. Esta versión de Qdrant no expone latencia de búsqueda ni contador de peticiones — no hay panel de eso, para no inventar un dato que no existe.

## Logs / App — un caso real de dashboard importado que no encaja del todo

Vale la pena mencionarlo con honestidad: este dashboard importado (ID 13639 de Grafana.com) espera que los logs lleven una etiqueta `app`, que **no existe** en las etiquetas reales de este clúster (aquí se usa `container_name`/`node`/`compose_project`, ver documento 02) — al abrirlo, el selector "App" solo ofrece "None" y no muestra datos. No está roto ni hace falta arreglarlo: para explorar logs en este clúster, **Explore con Loki** (documento 02) es la vía que sí funciona con las etiquetas reales. Se deja como ejemplo de que no todo dashboard importado de la comunidad encaja sin ajustes con el esquema de etiquetas propio de un clúster — antes de asumir que uno importado "no funciona", vale la pena comprobar qué etiquetas espera frente a las que existen de verdad.

El siguiente documento parte de aquí para construir un dashboard propio desde cero.
