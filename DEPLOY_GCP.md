# Deploying Meridian AI to Google Cloud

This guide covers deploying Meridian AI to **Cloud Run** with **Vertex AI Vector Search**, **Cloud Storage** and **Secret Manager**, using the GitHub Actions workflow in [.github/workflows/deploy.yml](.github/workflows/deploy.yml).

**Effort:** about 30 minutes of setup, plus 30–60 minutes of waiting on the first run (Vector Search provisioning).

---

## Deployment architecture

```
GitHub (push to main)
   │  GitHub Actions, authenticated as the github-deployer service account
   ▼
deploy.yml
   ├─ enable APIs
   ├─ Cloud Storage bucket  <project>-vector-staging
   ├─ Vertex AI Vector Search index + endpoint (bootstrapped with generate_json.py)
   ├─ Secret Manager: GOOGLE_API_KEY  +  runtime IAM grants
   ├─ Cloud Build ─► gcr.io/<project>/meridian-ai-cloud-run
   └─ Cloud Run service  meridian-ai-cloud-run  (public, max 3 instances)
                          runs as the default compute service account
```

Two service accounts are involved:

| Service account | Used by | Authenticates with |
|---|---|---|
| `github-deployer@<project>.iam.gserviceaccount.com` | GitHub Actions, to create resources and deploy | A JSON key stored as a GitHub secret |
| `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` | Cloud Build (image build) and Cloud Run (the running app) | No key: IAM roles only |

---

## Costs

| Service | Billing |
|---|---|
| **Vertex AI Vector Search** | **Per hour while the index is deployed, even with no traffic.** This is the main cost. Check https://cloud.google.com/vertex-ai/pricing. |
| Cloud Run | Per request; light use usually stays within the free tier |
| Cloud Storage, Cloud Build, Secret Manager, Artifact Registry | Cents, or within free allowances |
| Gemini API | Free tier available; content on the free tier may be used by Google to improve products, so use only the fictional sample documents |

- New Google Cloud customers receive **$300 credit for 90 days**. A card is required for verification, and you are not charged automatically when the trial ends.
- **Set a budget alert** before deploying (Step 2). Alerts notify you but do not stop spending.
- **Undeploy Vector Search when you are done** (see [Tear down](#tear-down)). Re-creating it takes 30–60 minutes.

---

## Prerequisites

- A Google account and a GitHub account
- The `gcloud` CLI: https://cloud.google.com/sdk/docs/install (or use **Cloud Shell** in the Console, which has it pre-installed)
- A Gemini API key (Step 5)

---

## Step 1 · Create the project

1. In https://console.cloud.google.com/, open the project picker and choose **New project**.
2. Note the **Project ID** (for example `meridian-ai-123456`) and the **Project number** (on the project dashboard). Commands below use both.

## Step 2 · Link billing and set a budget

1. **Billing** → link a billing account to the project.
2. **Billing → Budgets & alerts → Create budget**, for example $20 with e-mail alerts.

## Step 3 · Create the deployer service account

Run as the project Owner (Cloud Shell, or a terminal after `gcloud auth login`):

```bash
PROJECT_ID=YOUR_PROJECT_ID
DEPLOYER=github-deployer@${PROJECT_ID}.iam.gserviceaccount.com

gcloud config set project $PROJECT_ID
gcloud iam service-accounts create github-deployer --display-name="GitHub Actions Deployer"

for ROLE in \
  roles/editor \
  roles/resourcemanager.projectIamAdmin \
  roles/secretmanager.admin \
  roles/storage.admin; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${DEPLOYER}" --role="$ROLE" --condition=None
done

gcloud iam service-accounts keys create github-deployer-key.json --iam-account=$DEPLOYER
```

| Role | Why the workflow needs it |
|---|---|
| `roles/editor` | Create the bucket, Vector Search index/endpoint, secret, Cloud Build job and Cloud Run service |
| `roles/resourcemanager.projectIamAdmin` | Grant `roles/aiplatform.user` to the Cloud Run service account |
| `roles/secretmanager.admin` | Grant the Cloud Run service account access to the `GOOGLE_API_KEY` secret. Editor cannot change a secret's IAM policy. |
| `roles/storage.admin` | Grant the Cloud Run service account access to the bucket. Editor cannot change a bucket's IAM policy. |

`github-deployer-key.json` is a credential. Paste it only into the GitHub secret in Step 6, then delete the local file. If it leaks, delete the key under **IAM & Admin → Service accounts → github-deployer → Keys**.

> These roles are broad to keep a prototype deployment simple. For production, use Workload Identity Federation instead of a JSON key, and a custom role with only the permissions listed above.

## Step 4 · Grant the build/runtime service account its roles

Newer projects, and projects inside an organisation, no longer give the default compute service account the Editor role automatically. Cloud Build runs the image build as this account, so it needs these roles:

```bash
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
COMPUTE_SA=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com

for ROLE in \
  roles/cloudbuild.builds.builder \
  roles/artifactregistry.createOnPushWriter \
  roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:${COMPUTE_SA}" --role="$ROLE" --condition=None
done
```

| Role | Why |
|---|---|
| `roles/cloudbuild.builds.builder` | Read the uploaded source from the `<project>_cloudbuild` bucket and run the build |
| `roles/artifactregistry.createOnPushWriter` | Push the image to `gcr.io/<project>/…`, which is backed by Artifact Registry, and create that repository on the first push |
| `roles/logging.logWriter` | Write build logs |

The runtime roles (`roles/aiplatform.user`, `roles/storage.objectAdmin` on the bucket and `roles/secretmanager.secretAccessor` on the secret) are granted by the workflow itself.

IAM changes can take a few minutes to apply. Wait 2–3 minutes before running the workflow.

## Step 5 · Get a Gemini API key

1. Go to https://aistudio.google.com/apikey and choose **Create API key**.
2. Under **API restrictions**, restrict the key to the **Generative Language API**. Leave **Application restrictions** at **None**, because Cloud Run has no fixed outbound IP.

> **Organisation policy:** if the Console says *"API keys are disallowed. Your organisation's security policy disallows API keys"*, your project is in an organisation that blocks key creation. Either create the key in a project outside that organisation (an API key works from any project; usage is billed to the project that owns the key), or ask an organisation admin to override the policy for this project only.

## Step 6 · Add GitHub secrets

In the GitHub repository: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | The Project ID from Step 1 |
| `GCP_CREDENTIALS_JSON` | The entire contents of `github-deployer-key.json`, including the braces |
| `GOOGLE_API_KEY` | The Gemini key from Step 5 |

## Step 7 · Run the workflow

The workflow runs on every push to `main`, or manually from **Actions → Deploy to GCP Cloud Run → Run workflow**.

| Step in deploy.yml | What it does |
|---|---|
| Authenticate / Set up Cloud SDK | Signs in as `github-deployer` |
| Enable Required GCP APIs | Enables Vertex AI, Cloud Run, Secret Manager, Storage, Cloud Build, Artifact Registry, IAM and others, then waits 90 s for propagation |
| Ensure Storage Buckets Exist | Creates `<project>-vector-staging` (uniform access, public access prevented) |
| Ensure Initial Embeddings File Exists | Runs `generate_json.py` to write one 768-dim bootstrap vector, then uploads it to the bucket |
| Provision Vector Search Index & Endpoint | Creates index `financial-docs-production` (768 dims, dot product, stream updates) and endpoint `financial-docs-endpoint`, deploys the index as `deployed_financial_docs`, then removes the bootstrap vector. **This is the long wait.** |
| Ensure Secret Manager Has API Key | Stores `GOOGLE_API_KEY` as a new secret version and grants the Cloud Run service account its runtime roles |
| Build and Push Docker Image | `gcloud builds submit` builds the multi-stage Dockerfile |
| Deploy to Cloud Run | Deploys `meridian-ai-cloud-run` with `APP_MODE=cloud`, the index and endpoint IDs, and the secret |
| Allow Public Access to Cloud Run | Grants `allUsers` the invoker role and prints the IAM policy |

Every step is idempotent: existing resources are detected and skipped, so a failed run can simply be re-run.

## Step 8 · Verify

1. In the **Deploy to Cloud Run** log, open the `Service URL: https://meridian-ai-cloud-run-….run.app`.
2. Check `https://<service-url>/api/health`. It should return `{"status": "ok", "mode": "cloud"}`.
3. Upload the PDFs from `sample_uploaded_docs/` and ask one of the test questions from the [README](README.md#try-it).

> The service is **public with no authentication**. Anyone with the URL can use your Gemini quota and upload files. Do not upload confidential documents.

## Optional · Run locally against the cloud resources

Get the index and endpoint IDs:

```bash
gcloud ai indexes list --region=us-central1
gcloud ai index-endpoints list --region=us-central1
```

Set these in `.env`:

```
APP_MODE=cloud
GCP_PROJECT_ID=YOUR_PROJECT_ID
GCP_REGION=us-central1
GCS_BUCKET_NAME=YOUR_PROJECT_ID-vector-staging
GCS_PREFIX=uploads/
VECTOR_SEARCH_INDEX_ID=<index id>
VECTOR_SEARCH_INDEX_ENDPOINT_ID=<endpoint id>
GOOGLE_API_KEY=<your Gemini key>
```

Authenticate with `gcloud auth application-default login`. If `GCP_SERVICE_ACCOUNT_PATH` points to an existing key file, that file is used instead; remove the line to use your own login. Your account needs `roles/aiplatform.user` and access to the bucket.

---

## Tear down

**Vector Search (the hourly cost):**

```bash
REGION=us-central1
gcloud ai index-endpoints undeploy-index ENDPOINT_ID --deployed-index-id=deployed_financial_docs --region=$REGION
gcloud ai index-endpoints delete ENDPOINT_ID --region=$REGION
gcloud ai indexes delete INDEX_ID --region=$REGION
```

**Cloud Run service:**

```bash
gcloud run services delete meridian-ai-cloud-run --region=us-central1
```

**Everything:** `gcloud projects delete YOUR_PROJECT_ID`. The project stays recoverable for 30 days.

Also delete the `github-deployer` key, the local `github-deployer-key.json` and the three GitHub secrets. The next day, check **Billing → Reports** to confirm daily cost is near zero.

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `python: can't open file '…/generate_json.py'` | Bootstrap script missing from the repo | Make sure `generate_json.py` is committed at the repository root |
| `Permission 'secretmanager.secrets.setIamPolicy' denied` (as `github-deployer`) | Editor cannot change a secret's IAM policy | Grant `roles/secretmanager.admin` to the deployer (Step 3) |
| `Permission 'storage.buckets.setIamPolicy' denied` (as `github-deployer`) | Editor cannot change a bucket's IAM policy | Grant `roles/storage.admin` to the deployer (Step 3) |
| `<number>-compute@… does not have storage.objects.get access` on `<project>_cloudbuild` | Cloud Build runs as the compute service account, which has no roles | Step 4 |
| Build fails pushing to `gcr.io` ("permission denied" / "repository does not exist") | Missing Artifact Registry permission | `roles/artifactregistry.createOnPushWriter` (Step 4) |
| Build `TIMEOUT` after 3600 s during `pip install` | Unpinned dependencies make pip backtrack | Keep `requirements.txt` runtime-only and pinned; dev tools belong in `requirements-dev.txt` |
| "API keys are disallowed" | Organisation policy | See the note in Step 5 |
| Fails at authentication | `GCP_CREDENTIALS_JSON` is incomplete | Paste the whole JSON file, including `{ }` |
| "API has not been used … or it is disabled" | API enablement still propagating | Wait a few minutes and re-run |
| "Billing account not enabled" | No billing linked | Step 2 |
| App loads but answers fail | Bad Gemini key, retired model name, or index not yet deployed | Check Cloud Run **Logs**; set `VERTEX_LLM_MODEL_NAME` to a current model (https://ai.google.dev/gemini-api/docs/models) |
| First request is slow | Cloud Run scales to zero | Expected cold start |
