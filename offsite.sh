#!/usr/bin/env bash
# Copy ~/backups to an encrypted Google Drive remote and keep 30 days there.
# Needs rclone remotes `gdrive` (drive) and `gdrive-crypt` (crypt over gdrive:vps-backups);
# exits quietly until they exist.
set -uo pipefail
REMOTE=gdrive-crypt:
KEEP=30d

notify() {
  ( set -a; . "$HOME/.hermes/hermes.env"; curl -s -o /dev/null --max-time 15 \
      "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$1" ) || true
}

if ! rclone listremotes | grep -qx "$REMOTE"; then
  echo "remote $REMOTE not configured, skipping"
  exit 0
fi

if rclone copy "$HOME/backups" "$REMOTE" --stats-one-line -v 2>&1 | tail -2 &&
   rclone delete "$REMOTE" --min-age "$KEEP" && rclone rmdirs "$REMOTE" --leave-root; then
  echo "offsite ok"
else
  notify "Backup offsite ke Google Drive gagal. Cek: journalctl -u offsite-backup"
  exit 1
fi
