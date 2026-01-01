import json
import uuid
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

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
# App Initialization
# -------------------------------------------------------------------

app = FastAPI(title="Workflow Approval API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------

class CreateWorkflowRequest(BaseModel):
    text: str


class ApprovalRequest(BaseModel):
    decision: str            # "approved" | "rejected"
    reviewer: str
    notes: Optional[str] = None


class WorkflowResponse(BaseModel):
    id: str
    request_text: str
    state: str
    ai_output: Optional[dict]
    human_decision: Optional[dict]
    created_at: str
    updated_at: str


class WorkflowEventResponse(BaseModel):
    event_type: str
    event_data: Optional[dict]
    created_at: str


# -------------------------------------------------------------------
# Utility Functions
# -------------------------------------------------------------------

def execute_action(action: str, workflow_id: str):
    """
    Mocked action executor.
    Replace with real integrations later.
    """
    if action == "create_task":
        print(f"[ACTION] Created task for workflow {workflow_id}")
    elif action == "send_email":
        print(f"[ACTION] Sent email for workflow {workflow_id}")
    else:
        print(f"[ACTION] No action executed for workflow {workflow_id}")


def log_event(
    workflow_id: str,
    event_type: str,
    event_data: dict | None = None
):
    """
    Writes a workflow event to the event log.
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
# Health Check
# -------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "Workflow API running"}


# -------------------------------------------------------------------
# Create Workflow Endpoint
# -------------------------------------------------------------------

@app.post("/workflows")
def create_workflow(request: CreateWorkflowRequest):
    """
    Creates a new workflow and transitions it to AI_ANALYZED state.
    The workflow processor will pick it up from there.
    """
    
    if not request.text or len(request.text.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="Request text cannot be empty"
        )
    
    workflow_id = str(uuid.uuid4())
    
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # Create workflow in RECEIVED state
            cur.execute(
                """
                INSERT INTO workflows (id, request_text, state)
                VALUES (%s, %s, 'RECEIVED')
                RETURNING id;
                """,
                (workflow_id, request.text.strip())
            )
            
            # Immediately transition to AI_ANALYZED so processor picks it up
            cur.execute(
                """
                UPDATE workflows
                SET state = 'AI_ANALYZED', updated_at = NOW()
                WHERE id = %s;
                """,
                (workflow_id,)
            )
            
        # Commit FIRST so workflow exists before logging events
        conn.commit()
    
    # Log events AFTER workflow is committed to database
    log_event(workflow_id, "CREATED", {"request_text": request.text.strip()})
    log_event(workflow_id, "STATE_TRANSITION", {
        "from": "RECEIVED",
        "to": "AI_ANALYZED"
    })
    
    print(f"[WORKFLOW] Created {workflow_id} - ready for AI analysis")
    
    return {
        "workflow_id": workflow_id,
        "state": "AI_ANALYZED",
        "message": "Workflow created and queued for AI analysis"
    }


# -------------------------------------------------------------------
# Approval Endpoint
# -------------------------------------------------------------------

@app.post("/workflows/{workflow_id}/approve")
def approve_workflow(workflow_id: str, approval: ApprovalRequest):

    if approval.decision not in {"approved", "rejected"}:
        raise HTTPException(
            status_code=400,
            detail="decision must be 'approved' or 'rejected'"
        )

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:

            # Load workflow
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

            # ---------------------------------------------------------
            # Rejected
            # ---------------------------------------------------------
            if approval.decision == "rejected":

                log_event(
                    workflow_id,
                    "REJECTED",
                    {
                        "reviewer": approval.reviewer,
                        "notes": approval.notes
                    }
                )

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

            # ---------------------------------------------------------
            # Approved
            # ---------------------------------------------------------
            if not ai_output or "recommended_action" not in ai_output:
                raise HTTPException(
                    status_code=500,
                    detail="AI output missing recommended_action"
                )

            recommended_action = ai_output["recommended_action"]

            execute_action(recommended_action, workflow_id)

            log_event(
                workflow_id,
                "ACTION_EXECUTED",
                {
                    "action": recommended_action,
                    "reviewer": approval.reviewer
                }
            )

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


# -------------------------------------------------------------------
# Read APIs (UI uses these)
# -------------------------------------------------------------------

@app.get("/workflows", response_model=List[WorkflowResponse])
def list_workflows():
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    request_text,
                    state,
                    ai_output,
                    human_decision,
                    created_at,
                    updated_at
                FROM workflows
                ORDER BY created_at DESC;
                """
            )
            rows = cur.fetchall()

    workflows = []
    for row in rows:
        workflows.append(
            WorkflowResponse(
                id=str(row[0]),
                request_text=row[1],
                state=row[2],
                ai_output=row[3],
                human_decision=row[4],
                created_at=row[5].isoformat(),
                updated_at=row[6].isoformat(),
            )
        )

    return workflows


@app.get("/workflows/{workflow_id}", response_model=WorkflowResponse)
def get_workflow(workflow_id: str):
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    request_text,
                    state,
                    ai_output,
                    human_decision,
                    created_at,
                    updated_at
                FROM workflows
                WHERE id = %s;
                """,
                (workflow_id,)
            )
            row = cur.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Workflow not found")

    return WorkflowResponse(
        id=str(row[0]),
        request_text=row[1],
        state=row[2],
        ai_output=row[3],
        human_decision=row[4],
        created_at=row[5].isoformat(),
        updated_at=row[6].isoformat(),
    )


@app.get(
    "/workflows/{workflow_id}/events",
    response_model=List[WorkflowEventResponse]
)
def get_workflow_events(workflow_id: str):

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT event_type, event_data, created_at
                FROM workflow_events
                WHERE workflow_id = %s
                ORDER BY created_at ASC;
                """,
                (workflow_id,)
            )
            rows = cur.fetchall()

    events = []
    for row in rows:
        events.append(
            WorkflowEventResponse(
                event_type=row[0],
                event_data=row[1],
                created_at=row[2].isoformat()
            )
        )

    return events