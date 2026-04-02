#!/bin/bash
# ============================================================
# GCP Audit Log → Jira Ticket Alerting Pipeline Setup
# ============================================================
set -euo pipefail

gcloud config set core/disable_prompts True

# --- NON-SENSITIVE CONFIG — safe as env vars ---
PROJECT_ID=$(gcloud config get-value project)
REGION="us-east4"
TOPIC_NAME="audit-log-topic"
SINK_NAME="audit-log-sink"
SCHEDULER_TOPIC="reminder-topic"

JIRA_DOMAIN="evonence-team.atlassian.net"       # ← ye daalo
JIRA_PROJECT_KEY="GCP"            # ← ye daalo
JIRA_USER_EMAIL="utkarsh.pandey@evonence.com"       # ← ye daalo

# --- SENSITIVE CONFIG — set in terminal before running ---
# export JIRA_API_TOKEN="your_token"
# export GCHAT_WEBHOOK_URL="your_webhook_url"
: "${JIRA_API_TOKEN:?❌ Please run: export JIRA_API_TOKEN=your_token}"
: "${GCHAT_WEBHOOK_URL:?❌ Please run: export GCHAT_WEBHOOK_URL=your_webhook_url}"

echo "🚀 Starting deployment in project: $PROJECT_ID"

# 1. Enable Required APIs
echo "📦 Enabling APIs..."
gcloud services enable \
    logging.googleapis.com \
    pubsub.googleapis.com \
    cloudfunctions.googleapis.com \
    cloudbuild.googleapis.com \
    cloudscheduler.googleapis.com \
    secretmanager.googleapis.com \
    --project="$PROJECT_ID"

# 2. Store Sensitive Values in Secret Manager
echo "🔐 Storing secrets in Secret Manager..."

store_secret() {
    local SECRET_NAME=$1
    local SECRET_VALUE=$2
    if gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
        echo "  Updating: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets versions add "$SECRET_NAME" --data-file=- --project="$PROJECT_ID"
    else
        echo "  Creating: $SECRET_NAME"
        echo -n "$SECRET_VALUE" | gcloud secrets create "$SECRET_NAME" --data-file=- --project="$PROJECT_ID"
    fi
}

store_secret "JIRA_API_TOKEN" "$JIRA_API_TOKEN"
store_secret "GCHAT_WEBHOOK_URL" "$GCHAT_WEBHOOK_URL"

# 3. Grant Cloud Function Service Account access to secrets
echo "🔑 Granting Secret Manager access to Cloud Function..."

# Gen2 functions run on Cloud Run — service account is compute default
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
# Try both service accounts (appspot for gen1, compute for gen2)
SA_APPSPOT="${PROJECT_ID}@appspot.gserviceaccount.com"
SA_COMPUTE="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

for SA in "$SA_APPSPOT" "$SA_COMPUTE"; do
    for SECRET in JIRA_API_TOKEN GCHAT_WEBHOOK_URL; do
        gcloud secrets add-iam-policy-binding "$SECRET" \
            --member="serviceAccount:${SA}" \
            --role="roles/secretmanager.secretAccessor" \
            --project="$PROJECT_ID" \
            --quiet 2>/dev/null || true
    done
done
echo "  ✅ Secret access granted"

# 4. Create Pub/Sub Topics
echo "📣 Creating Pub/Sub topics..."
gcloud pubsub topics describe "$TOPIC_NAME" >/dev/null 2>&1 || gcloud pubsub topics create "$TOPIC_NAME"
gcloud pubsub topics describe "$SCHEDULER_TOPIC" >/dev/null 2>&1 || gcloud pubsub topics create "$SCHEDULER_TOPIC"

# 5. Create / Update Logging Sink
echo "📥 Creating/Updating Logging Sink..."
SINK_FILTER='protoPayload.@type="type.googleapis.com/google.cloud.audit.AuditLog"
AND (
  protoPayload.methodName="storage.buckets.create"
  OR protoPayload.methodName="google.pubsub.v1.Publisher.CreateTopic"
  OR protoPayload.methodName="google.pubsub.v1.Subscriber.CreateSubscription"
  OR protoPayload.methodName="google.bigquery.v2.DatasetService.InsertDataset"
  OR protoPayload.methodName="google.bigquery.v2.TableService.InsertTable"
  OR protoPayload.methodName="google.cloud.functions.v1.CloudFunctionsService.CreateFunction"
  OR protoPayload.methodName="google.cloud.functions.v2.FunctionService.CreateFunction"
  OR protoPayload.methodName="google.cloud.run.v1.Services.CreateService"
  OR protoPayload.methodName="google.cloud.run.v2.Services.CreateService"
  OR protoPayload.methodName="google.cloud.run.v2.Jobs.CreateJob"
  OR protoPayload.methodName="google.container.v1.ClusterManager.CreateCluster"
  OR protoPayload.methodName="google.container.v1.ClusterManager.CreateNodePool"
  OR protoPayload.methodName="google.spanner.admin.instance.v1.InstanceAdmin.CreateInstance"
  OR protoPayload.methodName="google.spanner.admin.database.v1.DatabaseAdmin.CreateDatabase"
  OR protoPayload.methodName="cloudsql.instances.create"
  OR protoPayload.methodName="google.dataflow.v1b3.Jobs.CreateJob"
  OR protoPayload.methodName="google.cloud.dataproc.v1.ClusterController.CreateCluster"
  OR protoPayload.methodName="google.iam.admin.v1.CreateServiceAccount"
  OR protoPayload.methodName="google.iam.admin.v1.CreateRole"
  OR protoPayload.methodName="google.cloud.secretmanager.v1.SecretManagerService.CreateSecret"
  OR protoPayload.methodName="google.cloud.scheduler.v1.CloudScheduler.CreateJob"
  OR protoPayload.methodName="google.cloud.tasks.v2.CloudTasks.CreateQueue"
  OR protoPayload.methodName="google.cloud.redis.v1.CloudRedis.CreateInstance"
  OR protoPayload.methodName="google.cloud.memcache.v1.CloudMemcache.CreateInstance"
  OR protoPayload.methodName="google.bigtable.admin.v2.BigtableInstanceAdmin.CreateInstance"
  OR protoPayload.methodName="google.bigtable.admin.v2.BigtableTableAdmin.CreateTable"
  OR protoPayload.methodName="google.cloud.aiplatform.v1.DatasetService.CreateDataset"
  OR protoPayload.methodName="google.cloud.aiplatform.v1.EndpointService.CreateEndpoint"
  OR protoPayload.methodName="google.cloud.aiplatform.v1.PipelineService.CreateTrainingPipeline"
  OR protoPayload.methodName="google.cloud.notebooks.v1.NotebookService.CreateInstance"
  OR protoPayload.methodName="google.cloud.composer.v1.Environments.CreateEnvironment"
  OR protoPayload.methodName="google.cloud.kms.v1.KeyManagementService.CreateKeyRing"
  OR protoPayload.methodName="google.cloud.kms.v1.KeyManagementService.CreateCryptoKey"
  OR protoPayload.methodName="dns.managedZones.create"
  OR protoPayload.methodName="google.cloud.filestore.v1.CloudFilestoreManager.CreateInstance"
  OR protoPayload.methodName="google.cloud.artifactregistry.v1.ArtifactRegistry.CreateRepository"
  OR protoPayload.methodName="v1.compute.instances.insert"
  OR protoPayload.methodName="beta.compute.instances.insert"
  OR protoPayload.methodName="v1.compute.disks.insert"
  OR protoPayload.methodName="v1.compute.networks.insert"
  OR protoPayload.methodName="v1.compute.subnetworks.insert"
  OR protoPayload.methodName="v1.compute.firewalls.insert"
  OR protoPayload.methodName="v1.compute.routers.insert"
  OR protoPayload.methodName="v1.compute.addresses.insert"
  OR protoPayload.methodName="v1.compute.snapshots.insert"
  OR protoPayload.methodName="v1.compute.images.insert"
  OR protoPayload.methodName="v1.compute.instanceTemplates.insert"
  OR protoPayload.methodName="v1.compute.forwardingRules.insert"
)
AND NOT protoPayload.authenticationInfo.principalEmail=~".*gserviceaccount\.com"
AND severity != ERROR'

if gcloud logging sinks describe "$SINK_NAME" &>/dev/null; then
    echo "Sink exists — updating filter..."
    gcloud logging sinks update "$SINK_NAME" --log-filter="$SINK_FILTER"
else
    gcloud logging sinks create "$SINK_NAME" \
        pubsub.googleapis.com/projects/"$PROJECT_ID"/topics/"$TOPIC_NAME" \
        --log-filter="$SINK_FILTER"
    SINK_SA=$(gcloud logging sinks describe "$SINK_NAME" --format='value(writerIdentity)')
    gcloud pubsub topics add-iam-policy-binding "$TOPIC_NAME" \
        --member="$SINK_SA" \
        --role="roles/pubsub.publisher"
fi

# 6. Deploy Cloud Functions (Gen 2)
# Only non-sensitive values in env vars — secrets fetched from Secret Manager at runtime
echo "⚡ Deploying Cloud Functions (Gen 2)..."
ENV_VARS="JIRA_DOMAIN=$JIRA_DOMAIN,JIRA_PROJECT_KEY=$JIRA_PROJECT_KEY,JIRA_USER_EMAIL=$JIRA_USER_EMAIL"

gcloud functions deploy audit-log-handler \
    --entry-point audit_log_handler \
    --runtime python310 \
    --trigger-topic "$TOPIC_NAME" \
    --region "$REGION" \
    --set-env-vars "$ENV_VARS" \
    --gen2 \
    --allow-unauthenticated

gcloud functions deploy reminder-handler \
    --entry-point reminder_handler \
    --runtime python310 \
    --trigger-topic "$SCHEDULER_TOPIC" \
    --region "$REGION" \
    --set-env-vars "$ENV_VARS" \
    --gen2 \
    --allow-unauthenticated

# 7. Create Cloud Scheduler Job
echo "⏰ Creating Cloud Scheduler Job..."
if ! gcloud scheduler jobs describe reminder-job --location "$REGION" &>/dev/null; then
    gcloud scheduler jobs create pubsub reminder-job \
        --schedule="0 * * * *" \
        --topic="$SCHEDULER_TOPIC" \
        --message-body="check" \
        --location="$REGION"
fi

echo ""
echo "✅ Deployment complete!"
echo "🔐 Sensitive values secured in Secret Manager — not exposed in source code."
echo "👉 Create any GCP resource — Jira ticket + GChat alert will fire within 1-2 minutes."