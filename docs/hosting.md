# Hosting the demo publicly

Goal: a public URL for the app, no domain purchased, paid from free-tier credits (AWS about $100, GCP about $300).
Status: **everything below the line "Verified locally" is built and tested on this machine; the cloud steps have not been
run yet** (they need the owner's cloud account).

## 1. Decision: Google Cloud Run + Cloud SQL (recommended)

| | GCP: Cloud Run + Cloud SQL (recommended) | AWS: App Runner + RDS | One small VM with Docker Compose |
|---|---|---|---|
| URL without a domain | `https://keleven-<hash>-<region>.a.run.app`, HTTPS included | `https://<hash>.<region>.awsapprunner.com`, HTTPS included | needs a trick for HTTPS (e.g. an `<ip>.sslip.io` name with Caddy) |
| Database | Cloud SQL for PostgreSQL, pgvector supported | RDS for PostgreSQL, pgvector supported | Postgres in a container you back up yourself |
| Rough monthly cost (check the pricing calculator) | database about $10-15, app about $5-10 with one warm instance | database about $12-15, app about $5-15 | about $7-15 |
| Credits | about $300 (the trial credit usually expires after 90 days) | about $100 (check the expiry date) | either |
| Servers to patch | none | none | yes |
| Why / why not | the larger credit and the least moving parts | fine, a smaller budget | cheapest, most work, easiest to get wrong |

Costs are estimates from list prices and are not verified. After the credits end the services bill your card unless you stop
them (section 7).

The database is only 65 MB and the traffic of a demo is small, so the smallest instance sizes are enough.

## 2. What the hosted app looks like

```
 visitor ──https──► Cloud Run service "keleven" (container from the Dockerfile; PUBLIC_MODE=1)
                       │ Cloud SQL connector (unix socket, IAM-controlled, no open database port)
                       ▼
                    Cloud SQL Postgres 17 + pgvector   (transcripts, vectors, graph; question log starts empty)
                       │
 outbound calls ───► Gemini API (answers)    Voyage API (query embeddings)
 secrets (Secret Manager): GEMINI_API_KEY, VOYAGE_API_KEY, ADMIN_PASSWORD, APP_DATABASE_URL
```

### Public mode (`PUBLIC_MODE=1`, set in the Dockerfile; code in `app/public.py`)
A public endpoint is open to everyone and every question spends model credits, and the transcripts are copyrighted.
A visitor (anyone without the admin password) therefore gets:

| Control | Default | Environment variable |
|---|---|---|
| Questions per IP per minute | 4 | `PUBLIC_RATE_PER_MIN` |
| Questions per IP per day | 40 | `PUBLIC_RATE_PER_DAY` |
| Questions per day across all visitors (a hard stop, counted in the database) | 300 | `PUBLIC_DAILY_CAP` |
| Version and answers to compute | free to choose (User and Dev views both open) | none |
| Retrieval settings (k, neighbours) | fixed at the defaults | admin only |
| Sources | short excerpts only (3 lines per scene, 160 characters per line) | fixed |
| Search hits, enhancer queries, SQL and graph rows | shown, with transcript text cut to excerpts | none |
| History and stored comparisons (other people's questions) | hidden | admin only |
| Answer length / question length | question 3-500 characters | existing |

The admin password lifts all of this (use it for your own testing and for the Dev view). To stop spending at once, set
`PUBLIC_DAILY_CAP=0` or delete the service.

Per question a visitor costs one enhancer call and up to three answer calls (the memory-only one is reused when the
question was asked before): roughly 3.7k input tokens for the enhancer and 8k input tokens for each transcript answer, so
about 20-30k input tokens. Set the daily cap from what you are willing to spend on the Gemini and Voyage keys, which are
billed separately from the cloud credits.

### Show media (owner decision, 2026-10-11: keep all of it)
The page ships the theme music (`app/static/audio/office-theme.mp3`), a Dwight image and character avatars
(`app/static/image/`), plus 326 public quotes (`app/static/quotes`, MIT licence). All of it is kept in the public image.
The music can still be left out with `--build-arg INCLUDE_THEME_AUDIO=0` (the page then hides its sound button). The
transcripts are never served whole (excerpts only, section 2).

## 3. Verified locally (done)

On a throwaway Postgres container with the same image as the project database:
- Migrations 001-017 apply on an empty database (24 tables, 7 views); they need the admin role to be named `office_admin`
  and the database `office_rag`.
- `deploy/export_data.sh` writes a 26 MB dump; `deploy/import_data.sh` restores it; row counts match the source
  (episodes 186, lines 57,973, chunks 4,658, embeddings 4,658, graph entities 104, characters 3,883, events 1,698,
  relations 325) and `graph_timeline_now` returns its 199 intervals.
- The `Dockerfile` builds (423 MB) and the container, pointed at the restored database, answers `/healthz`, `/api/info`
  (v3 default, 4,658 passages, public mode on), serves the page and the script, refuses `/api/history` and `/api/compare`
  to a visitor (403) and accepts the admin password, and runs a graph query.
- Rate limits (429 after the per-minute limit; another IP and the admin are unaffected) and excerpting are covered by tests
  on the code.
- **Not tested:** a real question through the container (it spends Gemini and Voyage credits), Cloud SQL itself, Cloud Run.

## 4. Steps on Google Cloud (not yet run)

Run from this repository. Replace the values in capitals. Region `asia-south1` (Mumbai) is the closest to the owner; any
region with Cloud Run and Cloud SQL works and prices differ slightly.

```bash
export PROJECT=keleven-demo-12345      # must be globally unique
export REGION=asia-south1

# 0. once: install the gcloud CLI, then
gcloud auth login
gcloud projects create $PROJECT && gcloud config set project $PROJECT
gcloud billing projects link $PROJECT --billing-account=YOUR_BILLING_ACCOUNT_ID
gcloud services enable run.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com

# 1. database (smallest shared-core size; check `gcloud sql tiers list` and the available versions)
gcloud sql instances create keleven-db --database-version=POSTGRES_17 --edition=ENTERPRISE --tier=db-f1-micro \
  --region=$REGION --storage-size=10GB --availability-type=zonal --backup-start-time=21:00
gcloud sql databases create office_rag --instance=keleven-db
gcloud sql users create office_admin --instance=keleven-db --password="$ADMIN_DB_PASSWORD"
# do not add any authorized network: only Cloud Run (through the connector) and the proxy below can reach it

# 2. schema and data, through the Cloud SQL Auth Proxy (a separate terminal; https://cloud.google.com/sql/docs/postgres/sql-proxy)
cloud-sql-proxy $PROJECT:$REGION:keleven-db --port 5555
for f in db/migrations/*.sql; do
  docker run --rm -i --add-host=host.docker.internal:host-gateway pgvector/pgvector:0.8.7-pg17 \
    psql "postgresql://office_admin:$ADMIN_DB_PASSWORD@host.docker.internal:5555/office_rag" \
    -v ON_ERROR_STOP=1 -q -v app_password="$APP_DB_PASSWORD" < "$f"
done
set -a; source .env; set +a; bash deploy/export_data.sh          # on the machine that has the local database
TARGET_URL="postgresql://office_admin:$ADMIN_DB_PASSWORD@host.docker.internal:5555/office_rag" bash deploy/import_data.sh

# 3. secrets
printf %s "$GEMINI_API_KEY"    | gcloud secrets create gemini-api-key --data-file=-
printf %s "$VOYAGE_API_KEY"    | gcloud secrets create voyage-api-key --data-file=-
printf %s "$ADMIN_PASSWORD"    | gcloud secrets create admin-password --data-file=-
printf %s "postgresql://office_app:$APP_DB_PASSWORD@/office_rag?host=/cloudsql/$PROJECT:$REGION:keleven-db" \
  | gcloud secrets create app-database-url --data-file=-
# (Cloud Run's service account needs the "Secret Manager Secret Accessor" and "Cloud SQL Client" roles)

# 4. build and deploy (Cloud Build builds the Dockerfile; .gcloudignore keeps the data out of the upload)
gcloud run deploy keleven --source . --region $REGION --allow-unauthenticated \
  --add-cloudsql-instances $PROJECT:$REGION:keleven-db \
  --min-instances 1 --max-instances 2 --memory 1Gi --cpu 1 --concurrency 20 --timeout 120 \
  --set-env-vars POSTGRES_DB=office_rag,PUBLIC_MODE=1,PUBLIC_DAILY_CAP=150 \
  --set-secrets GEMINI_API_KEY=gemini-api-key:latest,VOYAGE_API_KEY=voyage-api-key:latest,ADMIN_PASSWORD=admin-password:latest,APP_DATABASE_URL=app-database-url:latest
```

`--min-instances 1` keeps one instance warm so the keyword index (built from the database at start-up, about a second) is
ready and the first visitor does not wait. `--max-instances 2` bounds the cost, and the in-memory per-IP limit is per
instance, which is why the global daily cap is counted in the database instead.

### After deploying
1. Open the URL from `gcloud run deploy`; check `/healthz` and that the page loads.
2. Ask one real question yourself (this is the first test that spends credits) and one in the Dev view with the admin password.
3. Create a budget with alerts (Billing > Budgets) at, say, $20 and $50, and a quota or spending limit on the Gemini and
   Voyage keys.
4. Check the logs (Cloud Run > Logs) for errors and 429s.

## 5. AWS equivalent (not prepared in detail)
Push the image to ECR (`docker build --platform linux/amd64`), create an RDS for PostgreSQL 17 instance (db.t4g.micro,
not public), enable the `vector` extension, run the same migrations and `import_data.sh` through a temporary bastion or an
SSM tunnel, store the four secrets in Secrets Manager, and create an App Runner service from the ECR image with a VPC
connector to the database. The app needs no code change: only `APP_DATABASE_URL` and the other environment variables.

## 6. Before it goes public: checklist
- [ ] The repository stays **private** (it contains the raw transcripts); the image and the build upload exclude them.
- [ ] A strong `ADMIN_PASSWORD`; the keys live in Secret Manager only and are not in the image or the repository.
- [ ] `PUBLIC_DAILY_CAP` set from the spending you accept; budget alerts on.
- [ ] The database has no public access (no authorized networks).
- [ ] One real question tested end to end in the deployed service.
- [ ] The page says that questions are logged (it does, in public mode) and shows excerpts only.
- [ ] Decide how long it stays up: credits expire; see below.

## 7. Turning it off
```bash
gcloud run services delete keleven --region $REGION                   # stops the app, and the cost
gcloud sql instances patch keleven-db --activation-policy=NEVER       # stops the database (storage still billed)
gcloud sql instances delete keleven-db                                # removes it; the local database keeps everything
```
