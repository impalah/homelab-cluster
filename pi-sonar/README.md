# pi-sonar — SonarQube + Bifrost

**IP:** `192.168.1.172`  
**Hardware:** Raspberry Pi 5 (8 GB RAM recomendado — SonarQube usa ~2.5 GB)

## Servicios

| Servicio | Puerto (host) | URL pública |
|---|---|---|
| sonarqube | 127.0.0.1:9000 | https://sonarqube.home.arpa |
| bifrost | 8080 | https://bifrost.home.arpa |

> La base de datos de SonarQube vive en `retaco` (`postgres-main`), no en este nodo — ver `docs/05-instalacion-retaco.md`.
> Bifrost es un gateway LLM hacia AWS Bedrock (sin base de datos externa, solo su propio SQLite en `bifrost/data/`) — ver `docs/23-bifrost-gateway-llm.md` para la instalación completa, la política IAM y el manual de operación.

## Prerrequisitos obligatorios del kernel

```bash
sudo sysctl -w vm.max_map_count=524288
sudo sysctl -w fs.file-max=131072
# Persistir:
sudo tee /etc/sysctl.d/99-homelab-sonar.conf <<'EOF'
vm.max_map_count=524288
fs.file-max=131072
EOF
```

## Arranque rápido

```bash
sudo bash /srv/homelab/shared/scripts/prepare-host.sh pi-sonar
cp .env.example .env
nano .env    # Ajustar SONARQUBE_DB_PASSWORD — debe coincidir con la creada en retaco
docker compose up -d
# El primer arranque tarda 3-5 minutos (inicialización de BD)
docker compose logs -f sonarqube
```

## Post-arranque

1. Acceder: `https://sonarqube.home.arpa` → admin / admin
2. **Cambiar la contraseña inmediatamente** (SonarQube lo obliga en el primer inicio de sesión)
3. Crear token de análisis: **My Account → Security → Generate Tokens**

## Análisis desde otro nodo

```bash
docker run --rm \
  -e SONAR_HOST_URL="https://sonarqube.home.arpa" \
  -e SONAR_TOKEN="<tu-token>" \
  -v "$(pwd):/usr/src" \
  sonarsource/sonar-scanner-cli
```

## Copia de seguridad de la base de datos

Se hace desde `retaco`, donde vive la base de datos (ver `docs/05-instalacion-retaco.md`):

```bash
bash /srv/homelab/shared/scripts/backup-postgres.sh retaco postgres-main sonarqube
```

## bifrost — arranque rápido

Detalle completo (política IAM, virtual keys, prueba manual, troubleshooting) en `docs/23-bifrost-gateway-llm.md`. Resumen:

```bash
mkdir -p /srv/homelab/pi-sonar/bifrost/data
sudo chown 1000:0 /srv/homelab/pi-sonar/bifrost/data && chmod 770 /srv/homelab/pi-sonar/bifrost/data
cp config/bifrost/config.json /srv/homelab/pi-sonar/bifrost/data/config.json
nano .env    # AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (usuario base) / AWS_ROLE_ARN / AWS_REGION / BIFROST_VIRTUAL_KEY
docker compose up -d bifrost
docker compose logs -f bifrost
```

> `/app/data` dentro del contenedor corre como UID:GID `1000:0` — el directorio del host debe ser propiedad de ese UID y escribible por el grupo 0, si no Bifrost falla al arrancar con `is not writable by UID:GID 1000:0`.

Prueba rápida (desde cualquier nodo del clúster):

```bash
curl -sk https://bifrost.home.arpa/v1/chat/completions \
  -H "Authorization: Bearer ${BIFROST_VIRTUAL_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model": "bedrock/eu.anthropic.claude-sonnet-4-6", "messages": [{"role": "user", "content": "di 'hola' y nada más"}]}'
```

`bifrost` **nunca se auto-actualiza** (sin label de watchtower, mismo criterio que `sonarqube`) — actualizar la versión de la imagen en `docker-compose.yml` a mano y de forma consciente.
