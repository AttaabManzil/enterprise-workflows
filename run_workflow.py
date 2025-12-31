import os
import json
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

def analyze_request(text: str) -> dict:
    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text}
        ],
        temperature=0
    )

    return json.loads(response.choices[0].message.content)

def run_workflow():
    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:

            cur.execute(
                """
                SELECT id, request_text
                FROM workflows
                WHERE state = 'AI_ANALYZED'
                LIMIT 1;
                """
            )
            row = cur.fetchone()

            if not row:
                print("No workflows in AI_ANALYZED state.")
                return

            workflow_id, request_text = row
            print(f"Analyzing workflow {workflow_id}")

            # 2. Call AI
            ai_output = analyze_request(request_text)
            print("AI output:", ai_output)

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

        conn.commit()

    print(f"Workflow {workflow_id} is now WAITING_FOR_APPROVAL")

if __name__ == "__main__":
    run_workflow()
