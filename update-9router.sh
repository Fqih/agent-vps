#!/usr/bin/env bash
# Update 9router to the newest version tag on Docker Hub, with backup and rollback.
# headroom (unversioned :latest) is refreshed first, with rollback to the previous image.
#   ./update.sh            update if a newer tag exists (quiet when up to date)
#   ./update.sh --check    only print current and latest version
#   ./update.sh 0.5.91     switch to a specific tag (also used for manual rollback)
set -euo pipefail
cd "$(dirname "$0")"

COMPOSE=docker-compose.yml
REPO=decolua/9router
HEALTH_URL=http://127.0.0.1:20128/

notify() {
  local env="$HOME/.hermes/hermes.env"
  [[ -r $env ]] || return 0
  # shellcheck disable=SC1090
  ( set -a; . "$env"; curl -s -o /dev/null --max-time 15 \
      "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${TELEGRAM_CHAT_ID}" --data-urlencode "text=$1" ) || true
}

latest_tag() {
  curl -fsS --max-time 20 "https://hub.docker.com/v2/repositories/$REPO/tags?page_size=50" |
    python3 -c 'import json,re,sys
tags=[t["name"] for t in json.load(sys.stdin)["results"] if re.fullmatch(r"\d+\.\d+\.\d+",t["name"])]
print(max(tags,key=lambda t:tuple(map(int,t.split(".")))))'
}

healthy() {  # healthy URL: any 2xx/3xx within 90s
  for _ in $(seq 30); do
    code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "$1" || true)
    [[ $code =~ ^[23] ]] && return 0
    sleep 3
  done
  return 1
}

update_headroom() {
  local image=ghcr.io/chopratejas/headroom:latest old new
  old=$(docker inspect -f '{{.Image}}' headroom)
  docker pull -q "$image" >/dev/null || return 0
  new=$(docker image inspect -f '{{.Id}}' "$image")
  [[ $new == "$old" ]] && return 0
  docker tag "$old" headroom:rollback
  if docker compose up -d headroom && healthy http://127.0.0.1:8787/health; then
    docker rmi headroom:rollback >/dev/null
    docker image prune -f >/dev/null
    notify "headroom diupdate (${new:7:12})."
  else
    docker tag headroom:rollback "$image"
    docker compose up -d headroom
    notify "headroom update gagal, dikembalikan ke image lama (${old:7:12})."
  fi
}

[[ ${1:-} == --check ]] || update_headroom

current=$(sed -n "s|^\s*image: $REPO:\(.*\)$|\1|p" "$COMPOSE")
target=${1:-}
if [[ -z $target || $target == --check ]]; then
  latest=$(latest_tag)
  if [[ $target == --check ]]; then echo "current $current, latest $latest"; exit 0; fi
  target=$latest
fi
[[ $target == "$current" ]] && exit 0

echo "9router: $current -> $target"
day="$HOME/backups/$(date +%F)"
mkdir -p "$day"
backup="$day/9router-pre-$target.tar.gz"
python3 - "$day/9router-pre-$target.sqlite" <<'PY'
import sqlite3, sys
from pathlib import Path
src = Path.home() / "9router/data/db/data.sqlite"
with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s, sqlite3.connect(sys.argv[1]) as d:
    s.backup(d)
PY
tar -czf "$backup" -C "$day" "9router-pre-$target.sqlite" -C "$PWD" "$COMPOSE" .env \
  data/jwt-secret data/machine-id data/auth
rm "$day/9router-pre-$target.sqlite"
chmod 600 "$backup"
cp "$COMPOSE" "$COMPOSE.bak-$current"

sed -i "s|image: $REPO:$current|image: $REPO:$target|" "$COMPOSE"
if docker compose pull 9router && docker compose up -d 9router && healthy "$HEALTH_URL"; then
  # Keep only the new tag and the previous one (rollback); drop older tags and dangling layers.
  docker images "$REPO" --format '{{.Repository}}:{{.Tag}}' |
    grep -v -e ":$target\$" -e ":$current\$" -e ':<none>$' | xargs -r docker rmi >/dev/null || true
  docker image prune -f >/dev/null
  notify "9router diupdate $current -> $target. Backup: $backup"
  echo "ok, backup $backup"
else
  cp "$COMPOSE.bak-$current" "$COMPOSE"
  docker compose up -d 9router
  if healthy "$HEALTH_URL"; then state="rollback ke $current berhasil"; else state="ROLLBACK GAGAL, cek manual"; fi
  notify "9router update ke $target gagal, $state. Backup: $backup"
  echo "update failed, $state" >&2
  exit 1
fi
