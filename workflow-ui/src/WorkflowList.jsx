import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const API_BASE = "http://127.0.0.1:8000";

function StatusBadge({ state }) {
  const colors = {
    RECEIVED: "#9ca3af",
    AI_ANALYZED: "#60a5fa",
    WAITING_FOR_APPROVAL: "#f59e0b",
    ACTION_APPROVED: "#6366f1",
    ACTION_EXECUTED: "#10b981",
    REJECTED: "#ef4444",
    AI_FAILED: "#dc2626",
    ACTION_FAILED: "#991b1b",
  };

  return (
    <span
      style={{
        padding: "4px 8px",
        borderRadius: "6px",
        backgroundColor: colors[state] || "#e5e7eb",
        color: "white",
        fontSize: "12px",
        fontWeight: "500",
      }}
    >
      {state}
    </span>
  );
}

export default function WorkflowList() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [newRequest, setNewRequest] = useState("");
  const [creating, setCreating] = useState(false);
  const [actionInProgress, setActionInProgress] = useState(null);

  const loadWorkflows = async () => {
    try {
      const res = await fetch(`${API_BASE}/workflows`);
      if (!res.ok) throw new Error("Failed to load workflows");
      const data = await res.json();
      setWorkflows(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const createWorkflow = async () => {
    if (!newRequest.trim()) return;
    setCreating(true);

    await fetch(`${API_BASE}/workflows`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: newRequest }),
    });

    setNewRequest("");
    setCreating(false);
    loadWorkflows();
  };

  const approveWorkflow = async (id, decision) => {
    setActionInProgress(id);

    await fetch(`${API_BASE}/workflows/${id}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        reviewer: "user@company.com",
      }),
    });

    setActionInProgress(null);
    loadWorkflows();
  };

  useEffect(() => {
    loadWorkflows();
    const i = setInterval(loadWorkflows, 3000);
    return () => clearInterval(i);
  }, []);

  if (loading) return <p>Loading workflows…</p>;

  return (
    <div style={{ padding: 20, fontFamily: "sans-serif", maxWidth: "900px" }}>
      <h1>Workflow Dashboard</h1>

      <textarea
        value={newRequest}
        onChange={(e) => setNewRequest(e.target.value)}
        placeholder="Enter business request"
        style={{ width: "100%", minHeight: 80 }}
      />

      <button onClick={createWorkflow} disabled={creating}>
        Create Workflow
      </button>

      <h2>Workflows</h2>

      {workflows.map((wf) => (
        <div key={wf.id} style={{ marginBottom: 16 }}>
          <Link to={`/workflows/${wf.id}`}>
            <strong>{wf.request_text}</strong>
          </Link>
          <div>
            <StatusBadge state={wf.state} />
          </div>

          {wf.state === "WAITING_FOR_APPROVAL" && (
            <>
              <button
                onClick={() => approveWorkflow(wf.id, "approved")}
                disabled={actionInProgress === wf.id}
              >
                Approve
              </button>
              <button
                onClick={() => approveWorkflow(wf.id, "rejected")}
                disabled={actionInProgress === wf.id}
              >
                Reject
              </button>
            </>
          )}
        </div>
      ))}
    </div>
  );
}
