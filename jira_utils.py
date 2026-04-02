import logging
import requests
from requests.auth import HTTPBasicAuth
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class JiraClient:
    def __init__(self, domain, user_email, api_token):
        self.base_url = f"https://{domain}/rest/api/3"
        self.auth = HTTPBasicAuth(user_email, api_token)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def _make_adf_description(self, text):
        """Convert plain text to Atlassian Document Format (ADF)."""
        paragraphs = []
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            paragraphs.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}]
            })
        if not paragraphs:
            paragraphs = [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]
        return {
            "type": "doc",
            "version": 1,
            "content": paragraphs
        }

    def _get_account_id(self, email):
        """Find Jira accountId by email address."""
        try:
            resp = requests.get(
                f"{self.base_url}/user/search",
                params={"query": email},
                headers=self.headers,
                auth=self.auth
            )
            users = resp.json()
            if users:
                logger.info(f"Found Jira user for {email}: {users[0].get('displayName')}")
                return users[0].get("accountId")
            else:
                logger.warning(f"No Jira user found for {email}")
                return None
        except Exception as e:
            logger.warning(f"Error searching user {email}: {e}")
            return None

    def _set_start_date(self, issue_key, start_date_str):
        """
        Set start date on an existing issue.
        Tries both field name variants used by different Jira project types.
        """
        for field_name in ["startdate", "startDate", "start_date"]:
            try:
                resp = requests.put(
                    f"{self.base_url}/issue/{issue_key}",
                    json={"fields": {field_name: start_date_str}},
                    headers=self.headers,
                    auth=self.auth
                )
                if resp.status_code == 204:
                    logger.info(f"Start date set via field '{field_name}' on {issue_key}")
                    return
                else:
                    logger.warning(f"Field '{field_name}' failed ({resp.status_code}): {resp.text[:100]}")
            except Exception as e:
                logger.warning(f"Error setting start date with field '{field_name}': {e}")

        logger.warning(f"Could not set start date on {issue_key} — field not supported in this project config")

    def create_ticket(self, project_key, summary, description, assignee_email=None, additional_labels=None):
        labels = ['GCP-Alert', 'Governance', 'Automated-Response']
        if additional_labels:
            labels.extend(additional_labels)

        # Start date = today, Due date = today + 2 days
        today    = datetime.utcnow().date()
        due_date = today + timedelta(days=2)

        # Resolve assignee accountId before creating ticket
        account_id = self._get_account_id(assignee_email) if assignee_email else None

        fields = {
            "project":     {"key": project_key},
            "summary":     f"[GCP ALERT] {summary}",
            "description": self._make_adf_description(description),
            "issuetype":   {"name": "Task"},
            "labels":      list(set(labels)),
            "priority":    {"name": "High"},
            "duedate":     str(due_date),
        }

        # Set assignee at creation time
        if account_id:
            fields["assignee"] = {"accountId": account_id}

        try:
            response = requests.post(
                f"{self.base_url}/issue",
                json={"fields": fields},
                headers=self.headers,
                auth=self.auth
            )
            response.raise_for_status()
            issue_key = response.json().get("key")
            logger.info(f"Created Jira ticket: {issue_key} | Assignee: {assignee_email} | Due: {due_date}")

            # Set start date via PUT (screen config workaround)
            self._set_start_date(issue_key, str(today))


            return type('Issue', (), {'key': issue_key})()

        except Exception as e:
            logger.error(f"Error creating Jira ticket: {e} | Response: {response.text if 'response' in locals() else 'N/A'}")
            return None

    def transition_to_in_progress(self, issue_key):
        """Move ticket to In Progress using Jira transition API."""
        try:
            # First fetch available transitions
            resp = requests.get(
                f"{self.base_url}/issue/{issue_key}/transitions",
                headers=self.headers,
                auth=self.auth
            )
            transitions = resp.json().get("transitions", [])
            logger.info(f"Available transitions for {issue_key}: {[t['name'] for t in transitions]}")

            # Find "In Progress" transition id
            transition_id = None
            for t in transitions:
                if t["name"].lower() in ["in progress", "start", "start progress", "in development"]:
                    transition_id = t["id"]
                    break

            if not transition_id:
                logger.warning(f"No In Progress transition found for {issue_key}")
                return False

            # Apply transition
            resp = requests.post(
                f"{self.base_url}/issue/{issue_key}/transitions",
                json={"transition": {"id": transition_id}},
                headers=self.headers,
                auth=self.auth
            )
            resp.raise_for_status()
            logger.info(f"Moved {issue_key} to In Progress")
            return True

        except Exception as e:
            logger.error(f"Error transitioning {issue_key} to In Progress: {e}")
            return False

    def add_comment(self, issue_key, comment_text):
        payload = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": comment_text}]}]
            }
        }
        try:
            response = requests.post(
                f"{self.base_url}/issue/{issue_key}/comment",
                json=payload,
                headers=self.headers,
                auth=self.auth
            )
            response.raise_for_status()
            logger.info(f"Added comment to {issue_key}")
            return True
        except Exception as e:
            logger.error(f"Error adding comment to {issue_key}: {e}")
            return False

    def query_old_open_tickets(self, project_key, days=2):
        # POST /search instead of GET (GET is 410 Gone in Jira API v3)
        jql = f'project = "{project_key}" AND created <= "-{days}d" AND statusCategory != "Done"'
        payload = {
            "jql": jql,
            "maxResults": 50,
            "fields": ["summary", "status", "assignee"]
        }
        try:
            response = requests.post(
                f"{self.base_url}/search",
                json=payload,
                headers=self.headers,
                auth=self.auth
            )
            response.raise_for_status()
            issues_data = response.json().get("issues", [])
            logger.info(f"Found {len(issues_data)} old open tickets")
            return [type('Issue', (), {'key': i['key']})() for i in issues_data]
        except Exception as e:
            logger.error(f"Error querying Jira: {e}")
            return []
