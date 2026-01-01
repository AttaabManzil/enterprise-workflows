import os
import json
import time
import psycopg
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

DB_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "dbname": "ai_workflows",
    "user": "postgres",
    "password": "postgres",  
}

SYSTEM_PROMPT = """
You are an assistant that analyzes business requests.

Return ONLY valid JSON with this exact schema:
{
  "intent": string,
  "recommended_action": "send_email" | "create_task" | "reject",
  "confidence": number between 0 and 1
}
"""


def validate_ai_output(output: dict) -> dict:
    """
    Validates AI output matches expected schema.
    Raises ValueError if invalid.
    """
    required_fields = ["intent", "recommended_action", "confidence"]
    for field in required_fields:
        if field not in output:
            raise ValueError(f"Missing required field: {field}")
    
    valid_actions = {"send_email", "create_task", "reject"}
    if output["recommended_action"] not in valid_actions:
        raise ValueError(f"Invalid action: {output['recommended_action']}")
    
    if not isinstance(output["confidence"], (int, float)) or not (0 <= output["confidence"] <= 1):
        raise ValueError(f"Invalid confidence: {output['confidence']}")
    
    return output


def analyze_request(text: str) -> dict:
    """
    Calls OpenAI to analyze a business request.
    Returns validated AI output.
    """
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        temperature=0
    )

    raw_output = response.choices[0].message.content
    
    try:
        ai_output = json.loads(raw_output)
        return validate_ai_output(ai_output)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse AI response as JSON: {e}")
        print(f"[ERROR] Raw response: {raw_output}")
        raise
    except ValueError as e:
        print(f"[ERROR] AI output validation failed: {e}")
        raise


def log_event(workflow_id: str, event_type: str, event_data: dict = None):
    """
    Logs a workflow event to the database.
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


def process_one_workflow() -> bool:
    """
    Processes a single workflow that's in AI_ANALYZED state.
    Returns True if a workflow was processed, False if none found.
    """
    
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:

            # Find a workflow ready for AI analysis
            cur.execute(
                """
                SELECT id, request_text
                FROM workflows
                WHERE state = 'AI_ANALYZED'
                ORDER BY created_at ASC
                LIMIT 1;
                """
            )
            row = cur.fetchone()

            if not row:
                return False  # No workflows to process

            workflow_id, request_text = row
            print(f"\n[WORKFLOW] Processing {workflow_id}")
            print(f"[REQUEST] {request_text}")

            try:
                # Call AI
                ai_output = analyze_request(request_text)
                print(f"[AI] Recommendation: {ai_output['recommended_action']} (confidence: {ai_output['confidence']:.2f})")

                # Update workflow with AI output
                cur.execute(
                    """
                    UPDATE workflows
                    SET ai_output = %s,
                        state = 'WAITING_FOR_APPROVAL',
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (json.dumps(ai_output), workflow_id)
                )
                
                # Commit FIRST so workflow exists before logging
                conn.commit()
                
                # Log events AFTER commit (outside the with cursor block)
                log_event(workflow_id, "AI_ANALYZED", ai_output)
                log_event(workflow_id, "STATE_TRANSITION", {
                    "from": "AI_ANALYZED",
                    "to": "WAITING_FOR_APPROVAL"
                })
                
                print(f"[WORKFLOW] {workflow_id} now WAITING_FOR_APPROVAL")
                return True

            except Exception as e:
                print(f"[ERROR] Failed to process workflow {workflow_id}: {e}")
                
                # Mark workflow as failed
                cur.execute(
                    """
                    UPDATE workflows
                    SET state = 'AI_FAILED',
                        updated_at = NOW()
                    WHERE id = %s;
                    """,
                    (workflow_id,)
                )
                
                conn.commit()
                
                # Log failure event
                log_event(workflow_id, "AI_FAILED", {"error": str(e)})
                
                return False


def run_workflow_loop():
    """
    Continuously processes workflows that need AI analysis.
    Runs until manually stopped.
    """
    print("=" * 60)
    print("WORKFLOW PROCESSOR STARTED")
    print("=" * 60)
    print("Watching for workflows in AI_ANALYZED state...")
    print("Press Ctrl+C to stop\n")
    
    consecutive_empty_polls = 0
    
    while True:
        try:
            processed = process_one_workflow()
            
            if processed:
                # Successfully processed a workflow
                consecutive_empty_polls = 0
                time.sleep(0.5)  # Brief pause, then check for more
            else:
                # No workflows found
                consecutive_empty_polls += 1
                
                # Only print "idle" message every 10 empty polls to reduce noise
                if consecutive_empty_polls % 10 == 1:
                    print(f"[IDLE] No workflows to process... (checking every 3s)")
                
                time.sleep(3)  # Wait before checking again
                
        except KeyboardInterrupt:
            print("\n\n[SHUTDOWN] Workflow processor stopped by user")
            break
            
        except Exception as e:
            print(f"\n[ERROR] Unexpected error in workflow loop: {e}")
            print("[RETRY] Waiting 10 seconds before retry...\n")
            time.sleep(10)


if __name__ == "__main__":
    run_workflow_loop()