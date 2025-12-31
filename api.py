import json
import psycopg
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,   
    "dbname": "ai_workflows",
    "user": "postgres",
    "password": "postgres", 
}

app = FastAPI(title="Workflow Approval API")

class ApprovalRequest(BaseModel):
    decision: str            
    reviewer: str            #
    notes: str | None = None


def execute_action(action: str, workflow_id: str):
    """
    Mocked action executor.
    In real systems this could send email, create task, etc.
    """
    if action == "create_task":
        print(f"[ACTION] Created task for workflow {workflow_id}")
    elif action == "send_email":
        print(f"[ACTION] Sent email for workflow {workflow_id}")
    else:
        print(f"[ACTION] No action executed for workflow {workflow_id}")


@app.post("/workflows/{workflow_id}/approve")
def approve_workflow(workflow_id: str, approval: ApprovalRequest):
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT state, ai_output
                FROM workflows
                WHERE id = %s;
                """,
                (workflow_id,)
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Workflow not found")

            state, ai_output = row

            if state != "WAITING_FOR_APPROVAL":
                raise HTTPException(
                    status_code=400,
                    detail=f"Workflow not in WAITING_FOR_APPROVAL (current: {state})"
                )

            human_decision = {
                "decision": approval.decision,
                "reviewer": approval.reviewer,
                "notes": approval.notes,
                "decided_at": datetime.utcnow().isoformat()
            }

            if approval.decision == "rejected":
                cur.execute(
                    """
                    UPDATE workflows
                    SET state = 'REJECTED',
                        human_decision = %s,
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (json.dumps(human_decision), workflow_id)
                )
                conn.commit()
                return {"status": "rejected", "workflow_id": workflow_id}

            recommended_action = ai_output["recommended_action"]
            execute_action(recommended_action, workflow_id)

            cur.execute(
                """
                UPDATE workflows
                SET state = 'ACTION_EXECUTED',
                    human_decision = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (json.dumps(human_decision), workflow_id)
            )

        conn.commit()

    return {
        "status": "approved",
        "action_executed": recommended_action,
        "workflow_id": workflow_id
    }
