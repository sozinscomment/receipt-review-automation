# n8n workflow export

`receipt_review_workflow.json` is the actual exported workflow that was built
and tested for this project (Google Drive Trigger → Download file →
HTTP Request → If → Slack notification).

**This file has been redacted before publishing.** The original export
contained:

- A real Slack Incoming Webhook URL (replaced with
  `https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK`)
- A real Google Drive folder ID/URL (replaced with
  `YOUR_GOOGLE_DRIVE_FOLDER_ID`)
- Local n8n instance/credential identifiers (replaced with
  `YOUR_CREDENTIAL_ID`, or removed where they were purely instance metadata)

None of the removed values are needed to understand or reuse the workflow —
they're placeholders you'd replace with your own webhook URL, folder, and
Google Drive credential when importing this into your own n8n instance.

## To import this into your own n8n

1. In n8n, go to **Workflows → Import from File** (or use the "..." menu on
   the canvas → Import).
2. Select `receipt_review_workflow.json`.
3. Reconnect the two Google Drive nodes to your own Google Drive OAuth
   credential (n8n will prompt for this since the credential ID won't match
   an existing one in your instance).
4. Update the Google Drive Trigger's folder to point at your own Drive
   folder.
5. Update the final HTTP Request node's URL to your own Slack Incoming
   Webhook.
6. If your FastAPI wrapper isn't running via Docker on the same machine as
   n8n, update the middle HTTP Request node's URL accordingly (it currently
   targets `http://host.docker.internal:8811/process`, which assumes n8n
   is in Docker and the API is running on the host machine).

See `../N8N_SETUP.md` for the full setup guide this was built against.
