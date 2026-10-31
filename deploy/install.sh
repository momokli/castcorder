#!/usr/bin/env bash
# Installiert den radio-zukka-Live-Würfel auf einem Raspberry Pi.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="/opt/zukka-wuerfel"
CONFIG_DIR="/etc/zukka-wuerfel"
SERVICE="zukka-wuerfel.service"

echo "==> Pakete installieren"
apt-get update
apt-get install -y --no-install-recommends \
  ffmpeg alsa-utils python3-gpiozero python3-lgpio

echo "==> Benutzer und Gruppen"
getent group gpio >/dev/null || groupadd --system gpio
getent group audio >/dev/null || groupadd --system audio
getent group zukka >/dev/null || groupadd --system zukka

if ! id -u zukka >/dev/null 2>&1; then
  useradd --system \
    --home-dir "${APP_DIR}" \
    --shell /usr/sbin/nologin \
    --no-create-home \
    --gid zukka \
    zukka
fi
usermod -aG gpio,audio zukka

echo "==> Programmdateien nach ${APP_DIR}"
install -d -m 0755 -o root -g root "${APP_DIR}"
rm -rf "${APP_DIR}/zukka_wuerfel"
cp -a "${SCRIPT_DIR}/zukka_wuerfel" "${APP_DIR}/zukka_wuerfel"
find "${APP_DIR}/zukka_wuerfel" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "${APP_DIR}/zukka_wuerfel" -name '*.pyc' -delete
chown -R root:root "${APP_DIR}"

echo "==> Konfiguration"
install -d -m 0755 -o root -g root "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
  install -m 0644 "${SCRIPT_DIR}/config.example.toml" "${CONFIG_DIR}/config.toml"
  echo "    Neue Konfiguration: ${CONFIG_DIR}/config.toml (bitte prüfen!)"
else
  echo "    Vorhandene Konfiguration bleibt erhalten: ${CONFIG_DIR}/config.toml"
fi

if [[ ! -f "${CONFIG_DIR}/streamer.env" ]]; then
  install -m 0600 -o root -g root /dev/null "${CONFIG_DIR}/streamer.env"
  {
    echo "# Passwort des AzuraCast-Streamer-/DJ-Accounts."
    echo "# Datei bleibt root:root 0600; systemd liest sie vor dem Drop der Rechte."
    echo "ZUKKA_STREAMER_PASSWORD="
  } > "${CONFIG_DIR}/streamer.env"
  chmod 0600 "${CONFIG_DIR}/streamer.env"
  echo "    Neue Secret-Datei: ${CONFIG_DIR}/streamer.env (Passwort eintragen!)"
else
  echo "    Vorhandene Secret-Datei bleibt erhalten: ${CONFIG_DIR}/streamer.env"
  chown root:root "${CONFIG_DIR}/streamer.env"
  chmod 0600 "${CONFIG_DIR}/streamer.env"
fi

echo "==> systemd-Service"
install -m 0644 "${SCRIPT_DIR}/deploy/${SERVICE}" "/etc/systemd/system/${SERVICE}"
systemctl daemon-reload
systemctl enable "${SERVICE}"

if grep -q '^ZUKKA_STREAMER_PASSWORD=.\+' "${CONFIG_DIR}/streamer.env"; then
  systemctl restart "${SERVICE}"
else
  echo "    Passwort noch leer – Service wird noch nicht gestartet."
  echo "    Nach dem Eintragen in ${CONFIG_DIR}/streamer.env:"
  echo "      sudo systemctl restart ${SERVICE}"
fi

echo
echo "Fertig. Logs ansehen:"
echo "  journalctl -u ${SERVICE} -f"
echo
echo "Voraussetzungen prüfen (liest streamer.env als root):"
echo "  sudo bash -c 'set -a; . ${CONFIG_DIR}/streamer.env; set +a; cd ${APP_DIR}; \\"
echo "    exec /usr/bin/python3 -m zukka_wuerfel --config ${CONFIG_DIR}/config.toml --check'"
