# pi-sonar — SonarQube

**IP:** `192.168.1.172`  
**Hardware:** Raspberry Pi 5 (8 GB RAM recomendado — SonarQube usa ~2.5 GB)

## Servicios

| Servicio | Puerto (host) | URL pública |
|---|---|---|
| sonarqube | 127.0.0.1:9000 | https://sonarqube.home.arpa |

> La base de datos vive en `retaco` (`postgres-main`), no en este nodo — ver `docs/05-instalacion-retaco.md`.

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
