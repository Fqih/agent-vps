# Phone widget

The Hub widget is a native Android app in `android-widget/`. Build,
install and phone setup: `android-widget/README.md`.

The widget reads `/status?token=<STATUS_TOKEN>` from hub-status over
Tailscale every 30 minutes and on the ⟳ button. To get the URL onto the
phone without typing the token, publish it from the VPS to the `tasks`
topic and copy it from the ntfy notification "URL widget Hub". The URL
uses the VPS tailnet IP because the phone does not resolve MagicDNS names:

    ssh agent-vps 'cd ~/hermes_automation && U="http://$(tailscale ip -4 | head -1):8090/status?token=$(grep ^STATUS_TOKEN= ~/.hermes/hermes.env | cut -d= -f2)" PYTHONPATH=. python3 -c "import os; from digest import load_env; from hub import notify; print(notify.publish(load_env(), \"tasks\", \"URL widget Hub\", os.environ[\"U\"], \"low\", fallback=False))"'

The message keeps the token in the ntfy cache for 24 hours (tailnet-only,
read access for the phone user only).
