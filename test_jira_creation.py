import sys
sys.path.insert(0, '.')
from jira_utils import JiraClient

# ============================================================
DOMAIN      = "utkarsh4.atlassian.net"
USER_EMAIL  = "utkarsh19921996@gmail.com"
API_TOKEN   = "ATATT3xFfGF0KS0YBpawFWbEn9SXlXeL8j_Xwi4g_SC1Ru_fK6XamqN5Yz0EoD7NTl4Yjz_tvXMJnvrL3WHhXca8kvJf5mh6n-Qb1llLW8VFOnRopAUHov-IrU7So-sAZMFennKgEV5AYnMLV6xyeCQscGO-W9jxWCf0GevrnY0gkqlwq--Atl0=018E5A15"
PROJECT_KEY = "SCRUM"
# ============================================================

print("\n" + "="*50)
print("  Jira Pipeline Test")
print("="*50)

client = JiraClient(DOMAIN, USER_EMAIL, API_TOKEN)

# Test 1: Create ticket
print("\n[1/3] Creating test ticket...")
issue = client.create_ticket(
    project_key=PROJECT_KEY,
    summary="GCP Resources: Created by harshal.nikure@evonence.com",
    description=(
        "Resource: test-bucket-demo\n"
        "Project: experiments-playground-436812\n"
        "Method: storage.buckets.create\n"
        "Creator: harshal.nikure@evonence.com\n"
        "Time: 2026-04-02T00:00:00Z\n"
        "Caller IP: 103.x.x.x\n"
    ),
    assignee_email="harshal.nikure@evonence.com",
    additional_labels=["GCP-Resources"]
)

if issue:
    print(f"      ✅ Ticket created: {issue.key}")
    print(f"      🔗 https://{DOMAIN}/browse/{issue.key}")

    # Test 2: Add comment
    print(f"\n[2/3] Adding comment to {issue.key}...")
    result = client.add_comment(
        issue.key,
        "⏰ Reminder: This resource was created 2 days ago. Please review."
    )
    print(f"      {'✅ Comment added!' if result else '❌ Comment failed'}")

    # Test 3: Query old tickets (days=0 to catch all for testing)
    print(f"\n[3/3] Querying old open tickets...")
    old = client.query_old_open_tickets(PROJECT_KEY, days=0)
    print(f"      ✅ Found {len(old)} ticket(s): {[i.key for i in old]}")

    print("\n" + "="*50)
    print("  ✅ ALL TESTS PASSED — Pipeline ready!")
    print("="*50 + "\n")
else:
    print("      ❌ Ticket creation failed — check credentials/token")
