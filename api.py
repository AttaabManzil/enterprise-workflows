import json
import uuid
import psycopg
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from openai import OpenAI

from action_executor import execute_action


# -------------------------------------------------------------------
# Configuration
# -------------------------------------------------------------------

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ai_workflows",
    "user": "postgres",
    "password": "postgres",  # local dev only
}

client = OpenAI()


# -------------------------------------------------------------------
# App Initialization
# -------------------------------------------------------------------

app = FastAPI(title="Enterprise AI Workflow API")

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
    decision: str  # "approved" | "rejected"
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
# Event Logger
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


# -------------------------------------------------------------------
# AI Analyzer
# -------------------------------------------------------------------

def run_ai_analysis(request_text: str) -> dict:
    """
    Runs AI analysis and returns validated AI output.
    Must return a dict with recommended_action.
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You analyze business requests.\n"
                    "Return ONLY valid JSON with this schema:\n"
                    "{\n"
                    '  "intent": string,\n'
                    '  "recommended_action": "send_email" | "create_task" | "reject",\n'
                    '  "confidence": number\n'
                    "}"
                )
            },
            {"role": "user", "content": request_text}
        ],
    )

    content = response.choices[0].message.content

    try:
        ai_output = json.loads(content)
    except json.JSONDecodeError:
        raise ValueError("AI returned invalid JSON")

    if "recommended_action" not in ai_output:
        raise ValueError("Missing recommended_action")

    return ai_output


# -------------------------------------------------------------------
# Health Check
# -------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "Workflow API running"}


# -------------------------------------------------------------------
# Create Workflow
# -------------------------------------------------------------------

@app.post("/workflows")
def create_workflow(request: CreateWorkflowRequest):

    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Request text cannot be empty")

    workflow_id = str(uuid.uuid4())
    request_text = request.text.strip()

    # ---- CREATE WORKFLOW ----
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO workflows (id, request_text, state)
                VALUES (%s, %s, 'RECEIVED');
                """,
                (workflow_id, request_text)
            )
        conn.commit()

    log_event(workflow_id, "CREATED", {"request_text": request_text})

    # ---- RUN AI ANALYSIS ----
    try:
        ai_output = run_ai_analysis(request_text)
    except Exception as e:
        log_event(
            workflow_id,
            "AI_ANALYSIS_FAILED",
            {"error": str(e)}
        )
        raise HTTPException(status_code=500, detail="AI analysis failed")

    # ---- SAVE AI OUTPUT + TRANSITION ----
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE workflows
                SET ai_output = %s,
                    state = 'AI_ANALYZED',
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (json.dumps(ai_output), workflow_id)
            )
        conn.commit()

    log_event(workflow_id, "AI_OUTPUT_SAVED", ai_output)
    log_event(
        workflow_id,
        "STATE_TRANSITION",
        {"from": "RECEIVED", "to": "AI_ANALYZED"}
    )

    return {
        "workflow_id": workflow_id,
        "state": "AI_ANALYZED",
        "message": "Workflow created and analyzed"
    }


# -------------------------------------------------------------------
# Approval Endpoint (Human-in-the-loop)
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

            cur.execute(
                """
                SELECT state, ai_output, request_text
                FROM workflows
                WHERE id = %s;
                """,
                (workflow_id,)
            )
            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Workflow not found")

            state, ai_output, request_text = row

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

            # -------- REJECTED --------
            if approval.decision == "rejected":

                log_event(workflow_id, "ACTION_REJECTED", human_decision)

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

            # -------- APPROVED --------
            recommended_action = ai_output["recommended_action"]

            log_event(
                workflow_id,
                "ACTION_APPROVED",
                {
                    "action": recommended_action,
                    "reviewer": approval.reviewer
                }
            )

            try:
                execute_action(
                    action=recommended_action,
                    workflow_id=workflow_id,
                    request_text=request_text
                )
            except Exception as e:
                log_event(
                    workflow_id,
                    "ACTION_FAILED",
                    {"error": str(e)}
                )

                cur.execute(
                    """
                    UPDATE workflows
                    SET state = 'ACTION_FAILED',
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (workflow_id,)
                )
                conn.commit()

                raise HTTPException(
                    status_code=500,
                    detail="Action execution failed"
                )

            # -------- SUCCESS --------
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
# Read APIs (UI)
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

    return [
        WorkflowResponse(
            id=str(r[0]),
            request_text=r[1],
            state=r[2],
            ai_output=r[3],
            human_decision=r[4],
            created_at=r[5].isoformat(),
            updated_at=r[6].isoformat(),
        )
        for r in rows
    ]


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

    return [
        WorkflowEventResponse(
            event_type=r[0],
            event_data=r[1],
            created_at=r[2].isoformat()
        )
        for r in rows
    ]
