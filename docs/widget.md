# Phone widget (KWGT)

The widget reads `/status` from hub-status over Tailscale. Use the tailnet
URL and the token from `hermes.env`:

    URL = http://<agent-vps tailnet name>:8090/status?token=<STATUS_TOKEN>

1. Install KWGT (Pro is needed to load presets; building from scratch
   works in the free version) and add a 4x2 widget.
2. Add four text rows and one small "updated" text. Each value is a KWGT
   web-get formula (`$wg(URL, json, path)$`):

| Row | Formula |
|---|---|
| Jobs | `🎯 $wg(URL, json, ".jobs.new_matches")$ baru · Aktif $wg(URL, json, ".jobs.active")$ · Interview $wg(URL, json, ".jobs.interview")$ · Follow-up $wg(URL, json, ".jobs.followup_due")$` |
| Today | `📅 $wg(URL, json, ".today.items[0].time")$ $wg(URL, json, ".today.items[0].title")$` (repeat with `[1]` for a second line) |
| Queue | `⚙️ $wg(URL, json, ".queue.running")$ jalan · $wg(URL, json, ".queue.queued")$ antri · $wg(URL, json, ".queue.failed")$ gagal` |
| VPS | `VPS $wg(URL, json, ".vps.cpu")$% CPU · $wg(URL, json, ".vps.ram")$% RAM · $wg(URL, json, ".vps.disk")$% disk · ag $wg(URL, json, ".router.ag")$` |
| Updated | `$tf(wg(URL, json, ".updated"), "HH:mm")$` |

3. Status color: set the VPS row color to
   `$if(wg(URL, json, ".level")=crit, #E53935, wg(URL, json, ".level")=warn, #FDD835, #43A047)$`.
4. Touch actions: jobs row opens the Telegram jobs bot; VPS row opens
   `http://<agent-vps tailnet name>:8090/?token=<STATUS_TOKEN>` in the browser.
5. KWGT settings: refresh interval 15 minutes. Exclude KWGT from battery
   optimization and add it to the Tailscale split-tunnel app list.

When `/status` cannot be reached KWGT keeps the last values; the
"updated" time shows how old they are.
