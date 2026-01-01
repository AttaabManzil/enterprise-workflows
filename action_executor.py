import os
import json
import time
import psycopg
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ai_workflows",
    "user": "postgres",
    "password": "postgres",
}

SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

FROM_EMAIL = "no-reply@yourcompany.com"
DEFAULT_TO_EMAIL = "sales@yourcompany.com"

POLL_INTERVAL_SECONDS = 3

# -------------------------------------------------------------------
# Utilities
# -------------------------------------------------------------------

def log_event(workflow_id: str, event_type: str, event_data: dict | None = None):
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflow_events (workflow_id, event_type, event_data)
                VALUES (%s, %s, %s);
                """,
                (workflow_id, event_type, json.dumps(event_data)),
            )
        conn.commit()


# -------------------------------------------------------------------
# Action Implementations
# -------------------------------------------------------------------

def send_email(workflow_id: str, request_text: str):
    if not SENDGRID_API_KEY:
        raise RuntimeError("SENDGRID_API_KEY not set")

    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=DEFAULT_TO_EMAIL,
        subject=f"[Workflow] Action Required ({workflow_id[:8]})",
        plain_text_content=request_text,
    )

    sg = SendGridAPIClient(SENDGRID_API_KEY)
    sg.send(message)

    print(f"[EMAIL] Sent email for workflow {workflow_id}")


def execute_action(action_type: str, workflow_id: str, request_text: str):
    if action_type == "send_email":
        send_email(workflow_id, request_text)
    else:
        raise ValueError(f"Unsupported action_type: {action_type}")


# -------------------------------------------------------------------
# Core Executor Logic
# -------------------------------------------------------------------

def process_one_action() -> bool:
    """
    Processes exactly ONE pending action.
    Returns True if an action was processed.
    """

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:

            # Lock ONE workflow row safely
            cur.execute(
                """
                SELECT id, action_type, request_text
                FROM workflows
                WHERE action_status = 'PENDING'
                  AND state = 'ACTION_APPROVED'
                ORDER BY updated_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1;
                """
            )

            row = cur.fetchone()
            if not row:
                return False

            workflow_id, action_type, request_text = row

            print(f"\n[ACTION] Executing {action_type} for {workflow_id}")

            # Mark as EXECUTING (idempotency lock)
            cur.execute(
                """
                UPDATE workflows
                SET action_status = 'EXECUTING',
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (workflow_id,),
            )
            conn.commit()

            try:
                execute_action(action_type, workflow_id, request_text)

                cur.execute(
                    """
                    UPDATE workflows
                    SET action_status = 'COMPLETED',
                        state = 'ACTION_EXECUTED',
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (workflow_id,),
                )

                log_event(
                    workflow_id,
                    "ACTION_EXECUTED",
                    {"action": action_type},
                )

                conn.commit()

                print(f"[SUCCESS] Action completed for {workflow_id}")
                return True

            except Exception as e:
                conn.rollback()

                cur.execute(
                    """
                    UPDATE workflows
                    SET action_status = 'FAILED',
                        state = 'ACTION_FAILED',
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (workflow_id,),
                )

                log_event(
                    workflow_id,
                    "ACTION_FAILED",
                    {"error": str(e)},
                )

                conn.commit()

                print(f"[ERROR] Action failed for {workflow_id}: {e}")
                return True


# -------------------------------------------------------------------
# Runner Loop
# -------------------------------------------------------------------

def run_executor():
    print("=" * 60)
    print("ACTION EXECUTOR STARTED")
    print("=" * 60)
    print("Watching for approved workflows...\n")

    while True:
        try:
            processed = process_one_action()
            if not processed:
                time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Executor stopped")
            break

        except Exception as e:
            print(f"[FATAL] Unexpected error: {e}")
            time.sleep(10)


if __name__ == "__main__":
    run_executor()
