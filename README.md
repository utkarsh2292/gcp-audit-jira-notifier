# 🚨 GCP Audit Log → Jira Alerting Pipeline

An automated governance pipeline that detects **any GCP resource creation** and instantly creates a **Jira ticket**, assigns it to the creator, sets due dates, and sends a **Google Chat notification** — all without manual intervention.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Setup & Deployment](#setup--deployment)
- [How It Works](#how-it-works)
- [Supported Resources](#supported-resources)
- [Configuration](#configuration)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## Overview

When any team member creates a GCP resource (VM, Bucket, Cloud Function, etc.), this pipeline:

1. Captures the event via **Cloud Audit Logs**
2. Routes it through **Pub/Sub**
3. Triggers a **Cloud Function (Gen2)** that:
   - Creates a **Jira ticket** with full details
   - Assigns it to the creator
   - Sets start date & due date (2 days)
   - Moves it to **In Progress**
   - Sends a **Google Chat alert**
4. After 2 days, a **Cloud Scheduler** job sends reminders for unresolved tickets

---

## Architecture

```
GCP Resource Created
        │
        ▼
Cloud Audit Logs
        │
        ▼
Logging Sink (filter: create/insert events)
        │
        ▼
Pub/Sub Topic (audit-log-topic)
        │
        ▼
Cloud Function Gen2 (audit-log-handler)
        │
        ├──► Jira Ticket Created
        │         - Assignee = Creator
        │         - Start Date = Today
        │         - Due Date = Today + 2 days
        │         - Status = In Progress
        │
        └──► Google Chat Notification
                  - Resource Name & Type
                  - Project & Creator
                  - Direct Console Link
                  - Jira Ticket Link

Cloud Scheduler (every hour)
        │
        ▼
Pub/Sub Topic (reminder-topic)
        │
        ▼
Cloud Function Gen2 (reminder-handler)
        │
        ├──► Jira Comment on old tickets
        └──► Google Chat Reminder
```

---

## Features

- ✅ **Auto-detection** of any GCP resource creation
- ✅ **Jira ticket** with resource details, assignee, start & due dates
- ✅ **Auto-transition** to In Progress on ticket creation
- ✅ **Rich Google Chat notifications** with direct links
- ✅ **2-day reminders** for unresolved tickets
- ✅ **Secrets secured** via GCP Secret Manager
- ✅ **Cloud Functions Gen2** (faster, more reliable)
- ✅ **50+ GCP resource types** supported

---

## Prerequisites

Before deploying, make sure you have:

- [ ] GCP Project with billing enabled
- [ ] `gcloud` CLI installed and authenticated
- [ ] Jira account with a project created
- [ ] Jira API Token (from [id.atlassian.com](https://id.atlassian.com/manage-profile/security/api-tokens)) — use **Classic token**, not scoped
- [ ] Google Chat Space with Webhook configured

---

## Project Structure

```
.
├── main.py                  # Cloud Function entry points
├── jira_utils.py            # Jira REST API v3 client
├── deploy.sh                # GCP deployment script
├── requirements.txt         # Python dependencies
├── test_jira_creation.py    # Local test script
└── README.md
```

---

## Setup & Deployment

### Step 1 — Clone the repo

```bash
git clone https://github.com/your-org/gcp-audit-jira-pipeline.git
cd gcp-audit-jira-pipeline
```

### Step 2 — Configure non-sensitive values in `deploy.sh`

Open `deploy.sh` and update these 3 lines:

```bash
JIRA_DOMAIN="your_domain.atlassian.net"
JIRA_PROJECT_KEY="YOUR_PROJECT_KEY"
JIRA_USER_EMAIL="your_email@company.com"
```

### Step 3 — Export sensitive values in your terminal

> ⚠️ Never hardcode tokens in source files. These are stored in Secret Manager automatically.

```bash
export JIRA_API_TOKEN="your_jira_api_token"
export GCHAT_WEBHOOK_URL="your_google_chat_webhook_url"
```

### Step 4 — Run deployment

```bash
chmod +x deploy.sh
./deploy.sh
```

The script will automatically:
- Enable required GCP APIs
- Store secrets in **Secret Manager**
- Grant Cloud Function access to secrets
- Create Pub/Sub topics
- Set up Logging Sink with resource creation filter
- Deploy both Cloud Functions (Gen2)
- Create Cloud Scheduler job

### Step 5 — Test locally (optional but recommended)

```bash
pip install -r requirements.txt
python test_jira_creation.py
```

Expected output:
```
✅ Ticket created: PROJ-1
✅ Comment added!
✅ ALL TESTS PASSED — Pipeline ready!
```

---

## How It Works

### Ticket Creation Flow

When a resource is created:

| Field | Value |
|---|---|
| Summary | `[GCP ALERT] GCS Bucket created by user@company.com` |
| Assignee | Creator's email (if Jira user exists) |
| Start Date | Today |
| Due Date | Today + 2 days |
| Status | In Progress |
| Labels | `GCP-Alert`, `Governance`, `Automated-Response`, `GCP-Resources` |
| Priority | High |

### Google Chat Notification Format

```
🚨 New GCP Resource Created
━━━━━━━━━━━━━━━━━━━━━━━━━━
📦 Resource Name:  my-bucket
🏷️ Resource Type:  GCS Bucket
🗂️ Project:        my-project-123
👤 Created By:     user@company.com
🕐 Time:           2026-04-02T10:00:00Z
━━━━━━━━━━━━━━━━━━━━━━━━━━
🔗 Console:        https://console.cloud.google.com/...
📋 Jira Ticket:    https://your-domain.atlassian.net/browse/PROJ-1
```

### Reminder Flow

Every hour, the scheduler checks for Jira tickets older than 2 days that are still open:
- Adds a comment: *"This resource was created 2 days ago. Please remove or approve."*
- Sends a Google Chat reminder with the ticket link

---

## Supported Resources

| Category | Resources |
|---|---|
| **Storage** | GCS Bucket |
| **Compute** | VM Instance, Disk, Network, Subnet, Firewall, Router, IP, Snapshot, Image, Template, Forwarding Rule |
| **Serverless** | Cloud Function (v1 & v2), Cloud Run Service & Job |
| **Messaging** | Pub/Sub Topic, Subscription |
| **Database** | BigQuery Dataset & Table, Cloud SQL, Spanner, Bigtable, Redis, Memcache |
| **Containers** | GKE Cluster, Node Pool |
| **Data** | Dataflow Job, Dataproc Cluster |
| **AI/ML** | Vertex AI Dataset, Endpoint, Training Pipeline, Notebooks |
| **Security** | IAM Service Account & Role, KMS Key Ring & Crypto Key, Secret Manager |
| **DevOps** | Artifact Registry, Cloud Composer, Cloud Scheduler, Cloud Tasks |
| **Networking** | DNS Managed Zone, Filestore |

---

## Configuration

| Variable | Where | Description |
|---|---|---|
| `JIRA_DOMAIN` | `deploy.sh` | Your Atlassian domain e.g. `company.atlassian.net` |
| `JIRA_PROJECT_KEY` | `deploy.sh` | Jira project key e.g. `OPS` |
| `JIRA_USER_EMAIL` | `deploy.sh` | Email used for Jira API auth |
| `JIRA_API_TOKEN` | Secret Manager | Classic API token from id.atlassian.com |
| `GCHAT_WEBHOOK_URL` | Secret Manager | Google Chat Space webhook URL |

---

## Security

Sensitive values (`JIRA_API_TOKEN`, `GCHAT_WEBHOOK_URL`) are **never stored in source code or environment variables**. They are:

1. Stored in **GCP Secret Manager** during deployment
2. Fetched at **runtime** by the Cloud Function via the Secret Manager API
3. Cloud Function service account is granted **minimum required permissions** (`secretmanager.secretAccessor`)

```
Source Code   → ✅ No secrets
Env Variables → ✅ No secrets
Secret Manager → 🔐 Secrets stored here
Cloud Function → fetches at runtime
```

---

## Troubleshooting

### Jira ticket not creating
- Verify API token is a **Classic token** from `id.atlassian.com` (not organization/scoped token)
- Check Cloud Function logs: `GCP Console → Cloud Functions → audit-log-handler → Logs`
- Run `test_jira_creation.py` locally to verify credentials

### Secret Manager 403 error
```bash
# Manually grant access to compute service account
PROJECT_NUMBER=$(gcloud projects describe YOUR_PROJECT_ID --format="value(projectNumber)")
gcloud secrets add-iam-policy-binding JIRA_API_TOKEN \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### No alerts for new resources
- Check if Logging Sink is active: `GCP Console → Logging → Log Router`
- Verify the resource type is in the supported list above
- Check if the creator email ends with `gserviceaccount.com` — these are filtered out by design

### Too many duplicate alerts
- Ensure only one deployment method (manual or Terraform) is active
- Check for multiple Logging Sinks routing to the same topic

---

## Contributing

PRs welcome! If you add support for a new GCP resource type, add the method name mapping in `main.py` under `METHOD_TO_RESOURCE_TYPE` and the filter in `deploy.sh`.
