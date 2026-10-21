# Vercel Deployment Reconsidered

The user correctly noted that Vercel Daemons and Cron Jobs are available on the free tier. After reviewing the current (October 2025) docs, here is an honest reassessment.

---

## What Vercel Now Offers

### Vercel Daemons (Public Beta)

- Run long-running containerized processes alongside your app
- Defined in `vercel.json` / `vercel.toml` with a `Dockerfile`
- Cannot receive inbound HTTP/TCP traffic — they pull work from queues or external APIs
- Hobby tier: **10 vCPU-hours per month** (enough for a daily job that takes seconds)
- Pro tier: 16 vCPUs running concurrently (the real tier for always-on daemons)
- **No persistent local storage** — state must live in Vercel Blob, KV, or an external database
- No preview deployments for daemons — they only run in production

### Vercel Cron Jobs

- Trigger a Vercel Function on a schedule
- Available on Hobby tier with limits
- Good for a daily push if the function is lightweight

---

## Can Daily Koan PWA Run on Vercel?

Yes, but it requires restructuring. Here is what would change:

| Current (Droplet) | Vercel Equivalent |
|---|---|
| Flask app + gunicorn | Vercel Function (or Service with `main:app` entrypoint) |
| SQLite (`subscriptions.db`) | **Must replace** with Vercel KV, Supabase, or Vercel Postgres |
| `push_sender.py` cron script | Vercel Cron Job or Daemon pulling from a queue |
| Local file reads (`koans.json`) | Fine — can be bundled at build time |
| `vapid_private.pem` file | Store in environment variable |
| Service Worker + PWA manifest | Same — static files served from Vercel |

### The Real Blocker: SQLite

This is the dealbreaker for the simplicity mandate. SQLite is a file on disk. Vercel Functions spin up fresh, stateless containers. Even Daemons explicitly document:

> **Persistent local storage:** Store state in Vercel Blob or a database from the Marketplace.

To move to Vercel, you must either:

1. **Vercel KV** (Redis-compatible): Store subscriptions as JSON strings keyed by endpoint hash. Simple, but adds a vendor dependency.
2. **Supabase/Neon Postgres**: Full SQL, but now you're managing a separate service.
3. **Vercel Blob**: Object storage for files, not ideal for querying subscriptions.

Any of these work. None are as simple as `sqlite3.connect('subscriptions.db')`.

### The Dockerfile Requirement

Daemons require a `Dockerfile`. Your Python app must be containerized:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "push_sender.py"]
```

For the web app, you'd use Vercel's Python function support or a Service with `main:app` entrypoint. This is a different deployment model from "SSH in and run gunicorn."

---

## Comparison: Existing Droplet vs. Vercel

| Factor | Existing Droplet | Vercel |
|---|---|---|
| **Monthly cost** | $0 (already paying) | $0 (Hobby) |
| **Setup complexity** | Low | Medium (new primitives, config format) |
| **Database** | SQLite, zero config | Requires external DB (KV/Postgres/Supabase) |
| **Push scheduling** | systemd timer, 2 lines | Cron Job + Function or Daemon |
| **Logs & debugging** | `journalctl`, SSH in | Vercel dashboard logs |
| **SSL** | certbot, auto-renewal | Automatic, zero config |
| **CI/CD** | `git pull && restart` | Automatic on push |
| **Learning curve** | Standard Linux sysadmin | Vercel-specific primitives |
| **Vendor lock-in** | Low (portable anywhere) | Higher (KV, Blob, config schema) |
| **Beta risk** | None | Daemons are in Public Beta |

---

## Recommendation

**Use the existing droplet.**

The simplicity mandate favors SQLite + systemd over re-architecting for serverless primitives. The existing droplet is already paid for, and adding a subdomain costs nothing. The only reason to choose Vercel is if you want to learn their platform or if you specifically want zero-config SSL and auto-deployment.

If you later want to migrate, the app is small enough that moving the SQLite subscriptions to Vercel KV or Supabase is a single-day refactor.

---

## If You Still Want Vercel

1. Sign up for Vercel Hobby (free)
2. Create a `vercel.json` with Services for the Flask app + a Daemon for the push worker
3. Replace SQLite with **Vercel KV** (simplest migration) or **Supabase** (if you want SQL)
4. Store VAPID keys in environment variables
5. Add a Cron Job that triggers the push function daily
6. Point `koan.alvarsirlin.dev` CNAME to Vercel

This is 2-3 days of work versus 30 minutes on the droplet.
