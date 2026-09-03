# 01 — Primeros pasos

## Login

Accede a `https://grafana.404labo.net`. Verás un formulario con usuario y contraseña — la cuenta administradora es `admin`, con la contraseña definida en `GF_ADMIN_PASSWORD` (`pi-obs/config/grafana/`, no es un secreto que deba compartirse en este manual). Si necesitas acceso y no tienes esa contraseña, pídesela a quien administre el clúster.

Una vez dentro, verás la pantalla de inicio:

![Pantalla de inicio de Grafana](../assets/grafana-manual/01-grafana-home.jpg)

## Tour de la barra lateral

La barra lateral izquierda es el punto de partida para todo. De arriba a abajo, lo que vas a usar de verdad en este clúster:

- **Home** — la pantalla de inicio, con accesos a los dashboards vistos recientemente.
- **Starred** — dashboards marcados como favoritos (con la ⭐ que aparece al pasar el ratón por cualquier dashboard de una lista).
- **Dashboards** — el listado completo de dashboards, organizados en carpetas. Es donde pasarás más tiempo. Ver documento 03.
- **Explore** — consultas puntuales a Prometheus/Loki sin necesidad de guardar nada. Ver documento 02.
- **Alerting** — reglas de alerta, contact points (a dónde se notifica), notification policies (qué regla va a qué contact point). Ver documento 05.
- **Connections → Data sources** — las 3 fuentes de datos conectadas (Prometheus, Loki, Tempo). Ver documento 06.
- **Administration** — usuarios, permisos, plugins. En este clúster, de un solo operador, casi nunca hace falta tocarla.

## Buscador rápido

`Ctrl+K` (o el campo "Search or jump to..." en la parte superior) abre un buscador que salta directamente a cualquier dashboard, panel o página de configuración por nombre — más rápido que navegar por la barra lateral una vez que ya conoces los nombres de las cosas.

## Conceptos clave, explicados desde cero

Estos cinco términos aparecen constantemente en el resto del manual — vale la pena tenerlos claros antes de seguir:

- **Datasource (fuente de datos)** — de dónde vienen los datos que se muestran. En este clúster: Prometheus (métricas), Loki (logs), Tempo (trazas). Un panel siempre consulta a una datasource concreta.
- **Dashboard** — una página con uno o varios paneles, guardada con un nombre, organizada dentro de una carpeta. Es la unidad que se comparte y se reutiliza.
- **Panel** — un único gráfico, tabla, número grande (stat) o cualquier otra visualización dentro de un dashboard. Cada panel tiene su propia query (consulta) a una datasource.
- **Variable** — un valor sustituible dentro de las queries de un dashboard (por ejemplo, "qué nodo"), que se muestra como un desplegable en la parte superior del dashboard. Permite que un mismo dashboard sirva para los 7 nodos sin duplicar nada. Se explica con un ejemplo real en el documento 04.
- **Carpeta (folder)** — cómo se organizan los dashboards. En este clúster existen las carpetas `Homelab` (dashboards propios del clúster) y `Homelab Alerts` (donde viven las reglas de alerta), además de los dashboards importados de la comunidad, que están sueltos sin carpeta.

## Cómo saber qué usuario tienes activo

El icono de la esquina superior derecha (avatar) abre un menú con el nombre de usuario actual, cambio de contraseña y cierre de sesión. Útil para confirmar con qué cuenta estás trabajando si el clúster llega a tener más de un usuario en el futuro.

Con esto ya puedes moverte por la interfaz. El siguiente documento entra en cómo consultar datos reales sin necesidad de crear nada todavía.
