# Deploying Aegis — step by step, from zero

Written for someone who has never deployed anything. Follow it top to bottom.
**Total time: about 45–60 minutes**, most of it waiting for builds.

You are deploying **5 things**:

| # | What | Where | Why |
|---|---|---|---|
| 1 | Fraud Shield | Render | scam detection |
| 2 | Counterfeit Vision | Render | fake-note scanning |
| 3 | Fraud Graph | Render | mule-ring detection |
| 4 | Command Centre (backend) | Render | ties the three together |
| 5 | Dashboard | Vercel | the website people see |

You do **not** need the Gateway. The dashboard talks to services 1–4 directly.

**Order matters.** Do 1, 2, 3 first (they are independent), then 4 (it needs their
web addresses), then 5 (it needs 4's address).

---

## Before you start

**A word about the free tier — read this, it bit us once already.**

Render gives each account **750 free hours per month**. You are running 4 services.
If all 4 stay awake 24/7 that is 4 × 730 = ~2,920 hours, so a single account runs
out in **about a week**.

To avoid that:
- **Do not** run a keep-warm pinger except on demo day.
- Let services sleep. They wake in 50–90 seconds when someone opens the site.
- If you run out again, put 2 services on one account and 2 on another.

**Good news:** the scam detection now runs *in the browser*, so even if Render is
asleep, typing a message and getting a verdict still works instantly.

---

## Part 1 — Push your code to GitHub

Already done. Render and Vercel read from `github.com/prayag-1771/Aegis`.

---

## Part 2 — Create the Render account

1. Go to **https://render.com**
2. Click **Get Started** → **GitHub**
3. Sign in with the GitHub account that owns the repo
4. When it asks for repository access, allow it to see **Aegis**

---

## Part 3 — Deploy the three ML services

You will repeat the same 8 clicks three times. Here they are once, then a table
with what changes each time.

### The 8 steps (do these for each service)

1. On the Render dashboard, click **+ New** (top right) → **Web Service**
2. Find **Aegis** in the repo list → click **Connect**
3. **Name** — type the name from the table below
4. **Region** — pick **Singapore** (closest to India)
5. **Branch** — `main`
6. **Root Directory** — copy from the table. *This is the most common mistake — get it exactly right.*
7. **Runtime** — should auto-detect **Python 3**
8. **Build Command** and **Start Command** — copy from the table
9. **Instance Type** — **Free**
10. Click **Create Web Service**

Then wait. The first build takes **5–15 minutes** (Counterfeit is the slowest — it
installs PyTorch, which is large).

### Service 1 — Fraud Shield

| Field | Value |
|---|---|
| Name | `aegis-fraud-shield` |
| Root Directory | `fraud-shield-nlp` |
| Build Command | `pip install -e ".[dev]" && python -m aegis_fraud_shield.cli train` |
| Start Command | `uvicorn aegis_fraud_shield.api:app --app-dir src --host 0.0.0.0 --port $PORT` |

*(It trains its own small model during the build — that is normal and takes ~1 minute.)*

### Service 2 — Counterfeit Vision

| Field | Value |
|---|---|
| Name | `aegis-counterfeat` |
| Root Directory | `counterfeit-vision` |
| Build Command | `pip install -e .` |
| Start Command | `uvicorn aegis_counterfeit.api:app --app-dir src --host 0.0.0.0 --port $PORT` |

**Add one environment variable now** (scroll down to *Environment* before creating,
or add it after under the **Environment** tab):

```
COUNTERFEIT_LOW_MEMORY = 1
```

Without this, scanning a note crashes the service on the free tier.
No training needed — the trained model ships inside the repo.

### Service 3 — Fraud Graph

| Field | Value |
|---|---|
| Name | `aegis-fraud-graph` |
| Root Directory | `fraud-graph-ml` |
| Build Command | `pip install -e . && python -m aegis_fraud_graph.cli train` |
| Start Command | `uvicorn aegis_fraud_graph.api:app --app-dir src --host 0.0.0.0 --port $PORT` |

### After all three finish

Each service page shows a web address at the top, like:

```
https://aegis-fraud-shield-21e3.onrender.com
```

**Write all three down.** You need them in the next part.

Check each one works: open `<that address>/health` in your browser. You should see
some text with `"status":"ok"`. First load takes ~60 seconds (it is waking up).

---

## Part 4 — Deploy the Command Centre backend

Same 8 steps, with these values:

| Field | Value |
|---|---|
| Name | `aegis-backend` |
| Root Directory | `command-centre/backend` |
| Build Command | `pip install -e . -e ../fusion -e ../geospatial -e ../supply_trail` |
| Start Command | `uvicorn aegis_command.api:app --app-dir src --host 0.0.0.0 --port $PORT` |

### Environment variables for this one

Go to the **Environment** tab and add these. Click **Add Environment Variable** for each.

**Required — the three addresses from Part 3:**

```
FRAUD_SHIELD_URL = https://aegis-fraud-shield-21e3.onrender.com
COUNTERFEIT_URL  = https://aegis-counterfeat-n6ct.onrender.com
FRAUD_GRAPH_URL  = https://aegis-fraud-graph-viay.onrender.com
```

*(Use YOUR addresses, not these — they must match exactly, no trailing slash.)*

**For the AI summaries:**

```
GEMINI_API_KEY = <your Gemini key>
```

**Optional but recommended:**

```
AEGIS_PII_SALT = <any long random text you invent>
SARVAM_API_KEY = <your Sarvam key>          (Hindi/Tamil translation)
MONGODB_URI    = <your Atlas connection string>   (shared AI summaries)
```

**About Groq:** you can add `GROQ_API_KEY`, but it is currently blocked on your
network — it returns "Access denied" even with no key at all. Gemini is doing the
work. Adding Groq costs nothing and it may work from Render's network, so it is
worth putting in.

Click **Save Changes**. Render redeploys automatically (~3 minutes).

### Check it worked

Open `https://aegis-backend-rtk1.onrender.com/health`

You want to see all three modules saying **"up"**:

```json
{"status":"ok","modules":{"fraud-shield":"up","counterfeit-vision":"up","fraud-graph":"up"}}
```

If any says **"down"**, the URL for that service is wrong — check for typos and a
trailing slash. If it says **"error"**, that service is still waking up; wait a
minute and refresh.

---

## Part 5 — Tell the two citizen services where the backend is

Go back to **aegis-fraud-shield** → **Environment**, and add:

```
COMMAND_CENTRE_URL = https://aegis-backend-rtk1.onrender.com
```

Do the same for **aegis-counterfeat**, and also add:

```
COUNTERFEIT_PUBLIC_URL = https://aegis-counterfeat-n6ct.onrender.com
```

*(That is its own address — it needs it so scanned images display correctly.)*

Save each. They redeploy on their own.

---

## Part 6 — Deploy the dashboard on Vercel

1. Go to **https://vercel.com** → **Sign Up** → **Continue with GitHub**
2. Click **Add New…** → **Project**
3. Find **Aegis** → **Import**
4. **Root Directory** — click **Edit** and select `command-centre/frontend`
   *(This is the step people miss. It must not be the repo root.)*
5. **Framework Preset** — should say **Next.js** automatically
6. Open **Environment Variables** and add these three:

```
NEXT_PUBLIC_API_BASE            = https://aegis-backend-rtk1.onrender.com
NEXT_PUBLIC_FRAUD_SHIELD_URL    = https://aegis-fraud-shield-21e3.onrender.com
NEXT_PUBLIC_COUNTERFEIT_URL     = https://aegis-counterfeat-n6ct.onrender.com
```

7. Click **Deploy**

Wait ~2 minutes. You get an address like `https://aegis-xxxx.vercel.app`.

> **Important:** these `NEXT_PUBLIC_` values are baked in when the site is built.
> If you change one later, you must **redeploy** for it to take effect —
> Vercel → your project → **Deployments** → **⋯** on the newest one → **Redeploy**.

---

## Part 7 — Final check

Open your Vercel address and confirm:

- [ ] Map loads with markers on it
- [ ] The wifi icon in the top-right is **green** (backend reachable)
- [ ] **Modules** tab — all three modules show as up
- [ ] **Research Lab** tab — three cards with charts
- [ ] **Alerts & Analytics** — cards appear
- [ ] Open `https://aegis-fraud-shield-21e3.onrender.com/` — paste a scam message,
      you should get a verdict with a green **🔒 edgeAI answer** badge
- [ ] Open `https://aegis-counterfeat-n6ct.onrender.com/` — upload a note photo, get a verdict

**If the first page load is slow or shows errors: that is normal.** The free services
are asleep. Refresh after a minute.

---

## Demo-day routine

**15 minutes before you present:**

1. Open all four Render `/health` pages once, to wake them:
   - `https://aegis-fraud-shield-21e3.onrender.com/health`
   - `https://aegis-counterfeat-n6ct.onrender.com/health`
   - `https://aegis-fraud-graph-viay.onrender.com/health`
   - `https://aegis-backend-rtk1.onrender.com/health`
2. Open your Vercel site and click through each tab once (this warms the caches
   and downloads the on-device model).
3. Leave the tab open. Do not close it.

**The airplane-mode moment:** load the scam page first, *then* turn off wifi, then
paste a scam message. It still detects it — because the model is running in the
browser. That is your strongest privacy proof.

---

## When something goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Build fails immediately | Root Directory wrong | Settings → check it matches the table exactly |
| `/health` shows a module "down" | Wrong URL in env var | Check for typos and trailing slashes |
| Note scan crashes the service | Out of memory | Add `COUNTERFEIT_LOW_MEMORY = 1` |
| Dashboard shows no data | Vercel env vars wrong or not rebuilt | Fix them, then **Redeploy** |
| Everything 503 | Free hours used up | Wait for the monthly reset, or use a second account |
| First load takes a minute | Services asleep | Normal on free tier — wake them before demoing |

**Where to see errors:** Render → your service → **Logs** tab. The actual reason a
build failed is always in there.
