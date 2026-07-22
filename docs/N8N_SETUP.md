# Setting up n8n + the review workflow (local, free)

This runs entirely on your own Mac — no cloud account, no cost, no execution
limits. Follow these steps in order.

## 1. Install Docker Desktop

1. Go to https://www.docker.com/products/docker-desktop/ and download Docker
   Desktop for Mac (choose Apple Silicon, since you're on an M1).
2. Open the downloaded file and drag Docker into Applications, then launch it.
3. Wait for the little whale icon in your menu bar to show "Docker Desktop is
   running" (first launch can take a minute or two).
4. Verify it worked — open Terminal and run:

   ```
   docker --version
   ```

   You should see a version number, not a "command not found" error.

## 2. Run n8n

In Terminal, run:

```
docker run -it --rm --name n8n -p 5678:5678 -v n8n_data:/home/node/.n8n docker.n8n.io/n8nio/n8n
```

What this does: downloads n8n (first time only, takes a few minutes), starts
it, and keeps your workflows saved in a Docker volume (`n8n_data`) so they
survive even if you stop and restart the container later.

Once it's running, open **http://localhost:5678** in your browser. n8n will
ask you to create a local account (email/password — this stays on your
machine, it's not sent anywhere). Skip any "connect to n8n cloud" prompts —
we're running fully self-hosted and free.

To stop n8n later: go back to that Terminal window and press `Ctrl+C`. To
start it again: run the same `docker run` command — your workflows are
still there.

## 3. Run the FastAPI wrapper alongside it

In a **separate** Terminal tab/window (leave the n8n one running):

```
cd receipt-review-automation
source venv/bin/activate      # or: python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt   (first time only)
uvicorn api.main:app --host 0.0.0.0 --port 8811
```

Leave this running too. You can open **http://localhost:8811** in your
browser any time to see the dashboard directly.

**Important:** n8n runs inside a Docker container, which can't reach
`localhost:8811` the normal way — from inside the container, your Mac itself
is reachable at the special address `host.docker.internal` instead. So
whenever you build an HTTP Request node in n8n that calls your API, use:

```
http://host.docker.internal:8811/process
```

not `http://localhost:8811/process`.

## 4. Connect Google Drive in n8n

1. In the n8n editor (http://localhost:5678), create a new workflow.
2. Add a **Google Drive Trigger** node.
3. Click "Create new credential" and follow n8n's prompt — it walks you
   through a normal Google sign-in and permission screen (read-only access
   to Drive is enough). This is a one-time setup per Google account.
4. Set the trigger to watch a specific folder (create one in Drive first,
   e.g. "Receipts Inbox") for **file created** events, polling every
   15–30 minutes (your call — more often for a live demo, less often to
   conserve Drive API quota).

## 5. The rest of the workflow (we'll build this together next)

Once steps 1–4 are done and both n8n and the API are running, tell me and
we'll wire up the remaining nodes together: pulling the new file(s) from
Drive, sending them to `/process`, checking the `flagged_count` in the
response, and posting to Slack only when it's greater than zero.
