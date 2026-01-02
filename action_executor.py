import os
import json
import psycopg
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

from linear_client import create_issue

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
# Event Logger
# -------------------------------------------------------------------

def log_event(workflow_id: str, event_type: str, event_data: dict | None = None):
    """
    Writes an event to workflow_events table.
    """
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

# -------------------------------------------------------------------
# Idempotency Guards
# -------------------------------------------------------------------

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


def task_already_created(workflow_id: str) -> bool:
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM workflow_events
                WHERE workflow_id = %s
                  AND event_type = 'TASK_CREATED'
                LIMIT 1;
                """,
                (workflow_id,)
            )
            return cur.fetchone() is not None

# -------------------------------------------------------------------
# Email Execution (Idempotent)
# -------------------------------------------------------------------

def send_email_once(workflow_id: str, content: str):
    """
    Sends an email exactly once per workflow.
    """

    if email_already_sent(workflow_id):
        log_event(
            workflow_id,
            "EMAIL_SKIPPED_DUPLICATE",
            {"reason": "Email already sent"}
        )
        print(f"[EMAIL] Skipped duplicate for workflow {workflow_id}")
        return

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=TO_EMAIL,
        subject="Workflow Approved – Action Required",
        plain_text_content=content,
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)

        log_event(
            workflow_id,
            "EMAIL_SENT",
            {
                "to": TO_EMAIL,
                "status_code": response.status_code,
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
# Task Creation (Linear – Idempotent)
# -------------------------------------------------------------------

def create_task_once(workflow_id: str, request_text: str):
    """
    Creates a Linear task exactly once per workflow.
    """

    if task_already_created(workflow_id):
        log_event(
            workflow_id,
            "TASK_SKIPPED_DUPLICATE",
            {"reason": "Task already created"}
        )
        print(f"[TASK] Skipped duplicate for workflow {workflow_id}")
        return

    try:
        issue = create_issue(
            title=f"Workflow Task {workflow_id[:8]}",
            description=request_text or "Created from approved workflow",
        )

        log_event(
            workflow_id,
            "TASK_CREATED",
            {
                "linear_id": issue["id"],
                "identifier": issue["identifier"],
                "url": issue["url"],
            }
        )

        print(f"[TASK] Created Linear issue {issue['identifier']}")

    except Exception as e:
        log_event(
            workflow_id,
            "TASK_FAILED",
            {"error": str(e)}
        )
        print(f"[TASK] Failed for workflow {workflow_id}: {e}")
        raise

# -------------------------------------------------------------------
# Public Action Executor
# -------------------------------------------------------------------

def execute_action(action: str, workflow_id: str, request_text: str | None = None):
    """
    Executes approved real-world actions.
    This is the ONLY place side effects are allowed.
    """

    if action == "send_email":
        send_email_once(
            workflow_id=workflow_id,
            content=request_text or "Approved workflow action"
        )

    elif action == "create_task":
        create_task_once(
            workflow_id=workflow_id,
            request_text=request_text or "Created from approved workflow"
        )

    else:
        log_event(
            workflow_id,
            "NO_ACTION",
            {"reason": f"Unknown action: {action}"}
        )
        print(f"[ACTION] No action executed for workflow {workflow_id}")
