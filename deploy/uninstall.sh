#!/usr/bin/env bash
# Entfernt den Service und die Programmdateien. Konfiguration/Secret bleiben liegen.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo $0" >&2
  exit 1
fi

SERVICE="castcorder.service"

systemctl disable --now "${SERVICE}" 2>/dev/null || true
rm -f "/etc/systemd/system/${SERVICE}"

systemctl daemon-reload
rm -rf /opt/castcorder /var/lib/castcorder

echo "Entfernt. Konfiguration und streamer.env bleiben unter /etc/castcorder/."
echo "Secret bei Bedarf löschen: sudo rm /etc/castcorder/streamer.env"
