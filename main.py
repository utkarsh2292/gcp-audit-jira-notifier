import os
import json
import logging
import base64
import requests
from jira_utils import JiraClient
from google.cloud import secretmanager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# -------------------------------------------------------
# Secret Manager helper
# -------------------------------------------------------
def get_project_id():
    """Get project ID from GCP metadata server (works in all Function generations)."""
    try:
        resp = requests.get(
            "http://metadata.google.internal/computeMetadata/v1/project/project-id",
            headers={"Metadata-Flavor": "Google"},
            timeout=3
        )
        return resp.text
    except Exception as e:
        logger.error(f"Could not fetch project ID: {e}")
        return None

def get_secret(secret_id):
    """Fetch secret value from GCP Secret Manager."""
    try:
        project_id = get_project_id()
        if not project_id:
            logger.error(f"Cannot fetch secret '{secret_id}' — project ID is None")
            return None
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.error(f"Failed to fetch secret '{secret_id}': {e}")
        return None


# -------------------------------------------------------
# Non-sensitive config — env vars
# -------------------------------------------------------
JIRA_DOMAIN      = os.environ.get('JIRA_DOMAIN')
JIRA_PROJECT_KEY = os.environ.get('JIRA_PROJECT_KEY')
JIRA_USER_EMAIL  = os.environ.get('JIRA_USER_EMAIL')

# -------------------------------------------------------
# Sensitive config — Secret Manager
# -------------------------------------------------------
JIRA_API_TOKEN    = get_secret('JIRA_API_TOKEN')
GCHAT_WEBHOOK_URL = get_secret('GCHAT_WEBHOOK_URL')

# Initialize Jira Client
jira_client = JiraClient(JIRA_DOMAIN, JIRA_USER_EMAIL, JIRA_API_TOKEN)


# -------------------------------------------------------
# Resource type mapping — method → human readable label
# -------------------------------------------------------
METHOD_TO_RESOURCE_TYPE = {
    "storage.buckets.create": "GCS Bucket",
    "google.pubsub.v1.Publisher.CreateTopic": "Pub/Sub Topic",
    "google.pubsub.v1.Subscriber.CreateSubscription": "Pub/Sub Subscription",
    "google.bigquery.v2.DatasetService.InsertDataset": "BigQuery Dataset",
    "google.bigquery.v2.TableService.InsertTable": "BigQuery Table",
    "google.cloud.functions.v1.CloudFunctionsService.CreateFunction": "Cloud Function",
    "google.cloud.functions.v2.FunctionService.CreateFunction": "Cloud Function (v2)",
    "google.cloud.run.v1.Services.CreateService": "Cloud Run Service",
    "google.cloud.run.v2.Services.CreateService": "Cloud Run Service (v2)",
    "google.cloud.run.v2.Jobs.CreateJob": "Cloud Run Job",
    "google.container.v1.ClusterManager.CreateCluster": "GKE Cluster",
    "google.container.v1.ClusterManager.CreateNodePool": "GKE Node Pool",
    "google.spanner.admin.instance.v1.InstanceAdmin.CreateInstance": "Spanner Instance",
    "google.spanner.admin.database.v1.DatabaseAdmin.CreateDatabase": "Spanner Database",
    "cloudsql.instances.create": "Cloud SQL Instance",
    "google.dataflow.v1b3.Jobs.CreateJob": "Dataflow Job",
    "google.cloud.dataproc.v1.ClusterController.CreateCluster": "Dataproc Cluster",
    "google.iam.admin.v1.CreateServiceAccount": "IAM Service Account",
    "google.iam.admin.v1.CreateRole": "IAM Role",
    "google.cloud.secretmanager.v1.SecretManagerService.CreateSecret": "Secret Manager Secret",
    "google.cloud.kms.v1.KeyManagementService.CreateKeyRing": "KMS Key Ring",
    "google.cloud.kms.v1.KeyManagementService.CreateCryptoKey": "KMS Crypto Key",
    "google.cloud.scheduler.v1.CloudScheduler.CreateJob": "Cloud Scheduler Job",
    "google.cloud.tasks.v2.CloudTasks.CreateQueue": "Cloud Tasks Queue",
    "google.cloud.redis.v1.CloudRedis.CreateInstance": "Cloud Redis Instance",
    "google.cloud.memcache.v1.CloudMemcache.CreateInstance": "Memcache Instance",
    "google.bigtable.admin.v2.BigtableInstanceAdmin.CreateInstance": "Bigtable Instance",
    "google.bigtable.admin.v2.BigtableTableAdmin.CreateTable": "Bigtable Table",
    "google.cloud.aiplatform.v1.DatasetService.CreateDataset": "Vertex AI Dataset",
    "google.cloud.aiplatform.v1.EndpointService.CreateEndpoint": "Vertex AI Endpoint",
    "google.cloud.aiplatform.v1.PipelineService.CreateTrainingPipeline": "Vertex AI Training Pipeline",
    "google.cloud.notebooks.v1.NotebookService.CreateInstance": "Notebook Instance",
    "google.cloud.composer.v1.Environments.CreateEnvironment": "Cloud Composer Environment",
    "dns.managedZones.create": "DNS Managed Zone",
    "google.cloud.filestore.v1.CloudFilestoreManager.CreateInstance": "Filestore Instance",
    "google.cloud.artifactregistry.v1.ArtifactRegistry.CreateRepository": "Artifact Registry Repo",
    "v1.compute.instances.insert": "Compute Instance (VM)",
    "beta.compute.instances.insert": "Compute Instance (VM)",
    "v1.compute.disks.insert": "Compute Disk",
    "v1.compute.networks.insert": "VPC Network",
    "v1.compute.subnetworks.insert": "VPC Subnetwork",
    "v1.compute.firewalls.insert": "Firewall Rule",
    "v1.compute.routers.insert": "Cloud Router",
    "v1.compute.addresses.insert": "External IP Address",
    "v1.compute.snapshots.insert": "Disk Snapshot",
    "v1.compute.images.insert": "Compute Image",
    "v1.compute.instanceTemplates.insert": "Instance Template",
    "v1.compute.forwardingRules.insert": "Forwarding Rule",
}

def get_resource_type(method_name):
    return METHOD_TO_RESOURCE_TYPE.get(method_name, method_name.split(".")[-1])


def send_gchat_notification(message):
    if not GCHAT_WEBHOOK_URL:
        logger.warning("GCHAT_WEBHOOK_URL secret not found. Skipping notification.")
        return
    try:
        response = requests.post(GCHAT_WEBHOOK_URL, json={"text": message})
        response.raise_for_status()
        logger.info("GChat notification sent.")
    except Exception as e:
        logger.error(f"Failed to send GChat notification: {e}")


def audit_log_handler(event, context):
    """Cloud Function triggered by Pub/Sub (Audit Log Sink)."""
    try:
        if 'data' not in event:
            logger.error("No data in Pub/Sub event.")
            return

        pubsub_message = base64.b64decode(event['data']).decode('utf-8')
        log_data = json.loads(pubsub_message)

        proto_payload   = log_data.get('protoPayload', {})
        resource_labels = log_data.get('resource', {}).get('labels', {})
        resource_type   = log_data.get('resource', {}).get('type', '')

        resource_name = (
            proto_payload.get('resourceName') or
            resource_labels.get('resource_id') or
            resource_labels.get('bucket_name') or
            resource_labels.get('instance_id') or
            'Unknown'
        )
        if '/' in resource_name:
            resource_name = resource_name.split('/')[-1]

        method_name         = proto_payload.get('methodName', 'Unknown Method')
        project_id          = resource_labels.get('project_id', 'Unknown Project')
        creator_email       = proto_payload.get('authenticationInfo', {}).get('principalEmail', 'Unknown')
        user_agent          = proto_payload.get('requestMetadata', {}).get('callerSuppliedUserAgent', 'Unknown')
        timestamp           = log_data.get('timestamp', 'Unknown')
        resource_type_label = get_resource_type(method_name)

        # Console link
        console_link = f"https://console.cloud.google.com/home/dashboard?project={project_id}"
        if "storage" in method_name.lower():
            console_link = f"https://console.cloud.google.com/storage/browser/{resource_name}?project={project_id}"
        elif "compute.instances" in method_name.lower():
            console_link = f"https://console.cloud.google.com/compute/instances?project={project_id}"
        elif "pubsub" in method_name.lower():
            console_link = f"https://console.cloud.google.com/cloudpubsub/topic/list?project={project_id}"
        elif "bigquery" in method_name.lower():
            console_link = f"https://console.cloud.google.com/bigquery?project={project_id}"
        elif "functions" in method_name.lower():
            console_link = f"https://console.cloud.google.com/functions/list?project={project_id}"
        elif "run" in method_name.lower():
            console_link = f"https://console.cloud.google.com/run?project={project_id}"
        elif "container" in method_name.lower():
            console_link = f"https://console.cloud.google.com/kubernetes/list?project={project_id}"
        elif "sql" in method_name.lower():
            console_link = f"https://console.cloud.google.com/sql/instances?project={project_id}"

        log_link = (
            f"https://console.cloud.google.com/logs/query;"
            f"query=resource.type%3D%22{resource_type}%22"
            f"%0Aresource.labels.project_id%3D%22{project_id}%22?project={project_id}"
        )

        logger.info(f"Processing: {resource_name} | {method_name} | {project_id}")

        description = (
            f"Resource Name: {resource_name}\n"
            f"Resource Type: {resource_type_label}\n"
            f"Project: {project_id}\n"
            f"Method: {method_name}\n"
            f"Creator: {creator_email}\n"
            f"Time: {timestamp}\n"
            f"User Agent: {user_agent}\n"
            f"Console Link: {console_link}\n"
            f"Logs Link: {log_link}"
        )

        # Create Jira Ticket
        issue = jira_client.create_ticket(
            project_key=JIRA_PROJECT_KEY,
            summary=f"{resource_type_label} created by {creator_email}",
            description=description,
            assignee_email=creator_email,
            additional_labels=['GCP-Resources']
        )

        # Move to In Progress
        if issue:
            jira_client.transition_to_in_progress(issue.key)

        jira_link = f"https://{JIRA_DOMAIN}/browse/{issue.key}" if issue else "Error creating Jira ticket"

        send_gchat_notification(
            f"🚨 *New GCP Resource Created*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 *Resource Name:* `{resource_name}`\n"
            f"🏷️ *Resource Type:* `{resource_type_label}`\n"
            f"🗂️ *Project:* `{project_id}`\n"
            f"👤 *Created By:* `{creator_email}`\n"
            f"🕐 *Time:* `{timestamp}`\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 *Console:* {console_link}\n"
            f"📋 *Jira Ticket:* {jira_link}"
        )

    except Exception as e:
        logger.error(f"Error processing audit log: {e}", exc_info=True)


def reminder_handler(event, context):
    """Cloud Function triggered by Cloud Scheduler."""
    try:
        logger.info("Starting reminder check...")
        old_issues = jira_client.query_old_open_tickets(JIRA_PROJECT_KEY, days=2)

        if not old_issues:
            logger.info("No old open tickets found.")
            return

        for issue in old_issues:
            jira_client.add_comment(
                issue.key,
                "⏰ Friendly Reminder: This resource was created 2 days ago. "
                "Please remove it if no longer required, or approve it to keep."
            )
            send_gchat_notification(
                f"⏰ *Pending Resource Review*\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"Ticket *{issue.key}* has been open for 2+ days.\n"
                f"Please review and take action.\n"
                f"🔗 https://{JIRA_DOMAIN}/browse/{issue.key}"
            )

    except Exception as e:
        logger.error(f"Error in reminder handler: {e}", exc_info=True)