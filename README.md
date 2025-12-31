# Enterprise AI Workflow Engine

I built this to figure out how you'd actually use AI in a system where mistakes matter. Most AI demos just let the model do whatever it recommends, but that's not how real businesses work. This system treats AI as an advisor that makes recommendations, then pauses and waits for a human to approve before doing anything.

## What it does

The workflow is pretty straightforward. You send in a business request like "follow up with ABC Logistics about pricing" and the system calls OpenAI to figure out what action makes sense. It returns something like "send_email" with a confidence score. But here's the key part: nothing happens automatically. The workflow goes into a WAITING_FOR_APPROVAL state and just sits there until someone hits an API endpoint to approve or reject it.

If approved, the system executes exactly one action and logs everything to PostgreSQL. If rejected, it marks the workflow as rejected and stops. Either way, you have a complete audit trail of what was requested, what AI recommended, what the human decided, and what actually happened.

## Why I built it this way

I wanted to understand how you'd build a system that's both intelligent and safe. The constraint I gave myself was: AI can never execute actions on its own. It can analyze, recommend, and score confidence, but a human always makes the final call.

This forced me to think about state management differently than a typical API. The workflow needs to remember where it is even if the server crashes, so everything gets persisted to PostgreSQL immediately. Each state transition is an explicit database write.

## How it works

The system has three main pieces:

**run_workflow.py** handles the AI analysis. It queries the database for workflows in the AI_ANALYZED state, sends the request text to OpenAI, validates the response, and updates the workflow to WAITING_FOR_APPROVAL. I'm using GPT-4.1-mini with a strict system prompt that forces JSON output so I can validate the schema before using it.

**api.py** is the approval interface. It's a FastAPI server with one endpoint: POST /workflows/{id}/approve. You send it a decision (approved or rejected), a reviewer name, and optional notes. If approved, it executes the action and updates the state to ACTION_EXECUTED. If rejected, it just marks it rejected and stops.

**PostgreSQL** stores the entire workflow state. Every workflow has an id, current state, the original request text, AI output as JSON, human decision as JSON, and timestamps. This means if the server dies halfway through, you can restart and pick up exactly where you left off.

## State transitions

The workflow goes through these states in order:

RECEIVED → AI_ANALYZED → WAITING_FOR_APPROVAL → ACTION_EXECUTED (or REJECTED)

Each transition is explicit and gets written to the database immediately. There's no way to skip states or go backwards. This makes the system predictable and easy to reason about.

## What's actually implemented

Right now the action execution is mocked - it just prints to the terminal. In a real system this would send actual emails or create tasks in a project management tool. But the hard part (state management, AI integration, approval pause, audit logging) is all working.

The system successfully:
- Analyzes requests with OpenAI and validates the JSON response
- Persists state to PostgreSQL at every step
- Pauses workflows until human approval is received
- Executes actions only after explicit approval
- Logs the complete audit trail (request, AI output, human decision, final state)

## Tech stack

Python, FastAPI for the API server, PostgreSQL for state persistence, psycopg for database access, and OpenAI's API for the AI analysis.

## What I learned

The biggest challenge was figuring out how to make the approval mechanism work. At first I was thinking about websockets or long polling, but that adds a lot of complexity. I ended up with a simple approach: the workflow runner updates the state to WAITING_FOR_APPROVAL and just stops. Then the API server handles the approval as a separate request. This keeps things simple and stateless.

I also learned that validating AI output is not optional. GPT sometimes returns malformed JSON or makes up action names that don't exist. You need to validate the schema and handle errors explicitly, otherwise bad AI responses will crash your workflow.

## Current status

The end-to-end flow works. You can run the workflow processor, approve via API, and see the complete state in the database. The next step would be replacing the mocked actions with real integrations (SendGrid for email, Linear/Asana for tasks) and adding retry logic for API failures.
