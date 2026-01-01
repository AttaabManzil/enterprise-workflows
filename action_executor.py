import os
import json
import psycopg
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# -------------------------------------------------------------------
# Database Configuration
# -------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ai_workflows",
    "user": "postgres",
    "password": "postgres",  # local dev only
}

# -------------------------------------------------------------------
# SendGrid Configuration
# -------------------------------------------------------------------

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL = os.getenv("SENDGRID_FROM_EMAIL")
TO_EMAIL = os.getenv("DEFAULT_EMAIL_TO")

if not SENDGRID_API_KEY:
    raise RuntimeError("SENDGRID_API_KEY is not set")

if not FROM_EMAIL:
    raise RuntimeError("SENDGRID_FROM_EMAIL is not set")

if not TO_EMAIL:
    raise RuntimeError("DEFAULT_EMAIL_TO is not set")

# -------------------------------------------------------------------
# Event Helpers
# -------------------------------------------------------------------

def log_event(workflow_id: str, event_type: str, event_data: dict | None = None):
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflow_events (workflow_id, event_type, event_data)
                VALUES (%s, %s, %s);
                """,
                (workflow_id, event_type, json.dumps(event_data))
            )
        conn.commit()


def email_already_sent(workflow_id: str) -> bool:
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM workflow_events
                WHERE workflow_id = %s
                  AND event_type = 'EMAIL_SENT'
                LIMIT 1;
                """,
                (workflow_id,)
            )
            return cur.fetchone() is not None

# -------------------------------------------------------------------
# Email Execution (Idempotent)
# -------------------------------------------------------------------

def send_email_once(workflow_id: str, request_text: str):
    if email_already_sent(workflow_id):
        log_event(
            workflow_id,
            "EMAIL_SKIPPED_DUPLICATE",
            {"reason": "Email already sent"}
        )
        print(f"[EMAIL] Skipped duplicate for workflow {workflow_id}")
        return

    subject = "Workflow Approved: Action Required"
    body = f"""
A workflow has been approved and requires action.

Workflow ID:
{workflow_id}

Request:
{request_text}
""".strip()

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=TO_EMAIL,
        subject=subject,
        plain_text_content=body,
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        log_event(
            workflow_id,
            "EMAIL_SENT",
            {
                "to": TO_EMAIL,
                "status_code": response.status_code
            }
        )

        print(f"[EMAIL] Sent successfully for workflow {workflow_id}")

    except Exception as e:
        log_event(
            workflow_id,
            "EMAIL_FAILED",
            {"error": str(e)}
        )
        print(f"[EMAIL] Failed for workflow {workflow_id}: {e}")
        raise

# -------------------------------------------------------------------
# Public Action Executor
# -------------------------------------------------------------------

def execute_action(action: str, workflow_id: str, request_text: str):
    if action == "send_email":
        send_email_once(
            workflow_id=workflow_id,
            request_text=request_text
        )

    elif action == "create_task":
        log_event(
            workflow_id,
            "TASK_CREATED",
            {"note": "Task creation not implemented yet"}
        )
        print(f"[TASK] Created task for workflow {workflow_id}")

    else:
        log_event(
            workflow_id,
            "NO_ACTION",
            {"reason": f"Unknown action: {action}"}
        )
        print(f"[ACTION] No action executed for workflow {workflow_id}")
