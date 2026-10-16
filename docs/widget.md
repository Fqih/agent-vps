# Phone widget

The Hub widget is a native Android app in `android-widget/`. Build,
install and phone setup: `android-widget/README.md`.

The widget reads `/status?token=<STATUS_TOKEN>` from hub-status over
Tailscale every 30 minutes and on the ⟳ button. To get the URL onto the
phone without typing the token, publish it once from the VPS to the
`tasks` topic and copy it from the ntfy notification.
