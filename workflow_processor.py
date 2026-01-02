import time
import json
import psycopg
from psycopg.rows import dict_row
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ai_workflows",
    "user": "postgres",
    "password": "postgres",
}

POLL_INTERVAL_SECONDS = 5


def log_event(cur, workflow_id, event_type, event_data=None):
    cur.execute(
        """
        INSERT INTO workflow_events (workflow_id, event_type, event_data, created_at)
        VALUES (%s, %s, %s, %s)
        """,
        (
            workflow_id,
            event_type,
            json.dumps(event_data) if event_data else None,
            datetime.utcnow(),
        ),
    )


def validate_ai_output(ai_output: dict) -> bool:
    if not isinstance(ai_output, dict):
        return False

    if "recommended_action" not in ai_output:
        return False

    if ai_output["recommended_action"] not in {"send_email", "create_task", "reject"}:
        return False

    return True


def process_workflows():
    with psycopg.connect(**DB_CONFIG, row_factory=dict_row) as conn:
        while True:
            with conn.transaction():
                cur = conn.cursor()

                cur.execute(
                    """
                    SELECT *
                    FROM workflows
                    WHERE state = 'AI_ANALYZED'
                    ORDER BY created_at
                    LIMIT 10
                    """
                )

                workflows = cur.fetchall()

                for wf in workflows:
                    workflow_id = wf["id"]
                    ai_output = wf["ai_output"]

                    if not validate_ai_output(ai_output):
                        log_event(
                            cur,
                            workflow_id,
                            "AI_OUTPUT_INVALID",
                            {"ai_output": ai_output},
                        )

                        cur.execute(
                            """
                            UPDATE workflows
                            SET state = 'REJECTED',
                                updated_at = NOW()
                            WHERE id = %s
                            """,
                            (workflow_id,),
                        )

                        log_event(
                            cur,
                            workflow_id,
                            "STATE_TRANSITION",
                            {
                                "from": "AI_ANALYZED",
                                "to": "REJECTED",
                                "reason": "Invalid AI output",
                            },
                        )
                        continue

                    # Valid AI output → move to WAITING_FOR_APPROVAL
                    cur.execute(
                        """
                        UPDATE workflows
                        SET state = 'WAITING_FOR_APPROVAL',
                            updated_at = NOW()
                        WHERE id = %s
                        """,
                        (workflow_id,),
                    )

                    log_event(
                        cur,
                        workflow_id,
                        "STATE_TRANSITION",
                        {
                            "from": "AI_ANALYZED",
                            "to": "WAITING_FOR_APPROVAL",
                        },
                    )

            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    print("Workflow processor started...")
    process_workflows()
