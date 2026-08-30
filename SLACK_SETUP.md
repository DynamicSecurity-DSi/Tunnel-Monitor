# Slack Setup

tunnel-monitor uses a Slack **Incoming Webhook** to post alerts and health reports. No bot tokens or OAuth scopes required.

---

## Create a Webhook

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click **Create New App**
2. Choose **From scratch**, name it (e.g., `tunnel-monitor`), select your workspace
3. In the left sidebar, click **Incoming Webhooks**
4. Toggle **Activate Incoming Webhooks** to On
5. Click **Add New Webhook to Workspace**
6. Choose the channel where alerts should post (e.g., `#infrastructure-alerts`)
7. Click **Allow**
8. Copy the **Webhook URL** — it looks like:
   ```
   https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX
   ```

---

## Add the Webhook to config.json

```json
{
  "slack_webhook": "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX",
  ...
}
```

---

## Recommended Channel Setup

| Channel | Purpose |
|---|---|
| `#infra-alerts` | State-change alerts (DOWN/UP/DEGRADED) |
| `#infra-health` | Hourly health reports |

To send alerts and reports to different channels, create two webhooks pointing to different channels and use the one that fits your preference. Currently tunnel-monitor uses a single webhook for both — split channel support can be added by adding a `report_webhook` key to config.json and updating the script.

---

## Test the Webhook

```bash
curl -X POST -H 'Content-type: application/json' \
  --data '{"text":"tunnel-monitor webhook test"}' \
  https://hooks.slack.com/services/YOUR/WEBHOOK/HERE
```

You should see `ok` returned and a message appear in your Slack channel.
