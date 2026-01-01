import { useEffect, useState } from "react";

const API_BASE = "http://127.0.0.1:8000";  

function StatusBadge({ state }) {
  const colors = {
    RECEIVED: "#9ca3af",
    AI_ANALYZED: "#60a5fa",
    WAITING_FOR_APPROVAL: "#f59e0b",
    ACTION_EXECUTED: "#10b981",
    REJECTED: "#ef4444",
    AI_FAILED: "#dc2626",
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

export default function App() {
  const [workflows, setWorkflows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [actionInProgress, setActionInProgress] = useState(null);
  const [newRequest, setNewRequest] = useState("");
  const [creating, setCreating] = useState(false);

  const loadWorkflows = async () => {
    try {
      const res = await fetch(`${API_BASE}/workflows`);
      if (!res.ok) throw new Error("Failed to load workflows");
      const data = await res.json();
      setWorkflows(data);
    } catch (err) {
      setError("Failed to load workflows: " + err.message);
    } finally {
      setLoading(false);
    }
  };

  const createWorkflow = async () => {
    if (!newRequest.trim()) {
      setError("Request text cannot be empty");
      return;
    }

    setError(null);
    setCreating(true);

    try {
      const res = await fetch(`${API_BASE}/workflows`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: newRequest.trim() }),
      });

      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to create workflow");
      }

      const result = await res.json();
      console.log("Workflow created:", result);

      setNewRequest("");
      await loadWorkflows();
    } catch (err) {
      setError(err.message);
    } finally {
      setCreating(false);
    }
  };

  const approveWorkflow = async (id, decision) => {
    setError(null);
    setActionInProgress(id);

    try {
      const res = await fetch(`${API_BASE}/workflows/${id}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          decision,
          reviewer: "user@company.com",
          notes:
            decision === "approved"
              ? "Approved via UI"
              : "Rejected via UI",
        }),
      });

      if (!res.ok) {
        const errData = await res.json();
        console.error("Backend error:", errData);
        throw new Error(errData.detail || "Approval failed");
      }

      await loadWorkflows();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionInProgress(null);
    }
  };

  useEffect(() => {
    loadWorkflows();

    // Auto-refresh every 3 seconds
    const interval = setInterval(loadWorkflows, 3000);

    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div style={{ padding: 20, fontFamily: "sans-serif" }}>
        Loading workflows...
      </div>
    );
  }

  return (
    <div style={{ padding: 20, fontFamily: "sans-serif", maxWidth: "900px" }}>
      <h1>Workflow Dashboard</h1>

      {/* Error Display */}
      {error && (
        <div
          style={{
            backgroundColor: "#fee2e2",
            color: "#991b1b",
            padding: "10px",
            borderRadius: "6px",
            marginBottom: "12px",
          }}
        >
          {error}
        </div>
      )}

      {/* Create Workflow Form */}
      <div
        style={{
          border: "2px solid #e5e7eb",
          borderRadius: "8px",
          padding: "16px",
          marginBottom: "20px",
          backgroundColor: "#f9fafb",
        }}
      >
        <h3 style={{ marginTop: 0 }}>Create New Workflow</h3>
        <textarea
          value={newRequest}
          onChange={(e) => setNewRequest(e.target.value)}
          placeholder="Enter business request (e.g., 'Follow up with ABC Corp about pricing')"
          style={{
            width: "100%",
            minHeight: "80px",
            padding: "10px",
            fontSize: "14px",
            borderRadius: "6px",
            border: "1px solid #d1d5db",
            fontFamily: "sans-serif",
            resize: "vertical",
          }}
          disabled={creating}
        />
        <button
          onClick={createWorkflow}
          disabled={creating || !newRequest.trim()}
          style={{
            marginTop: "8px",
            padding: "8px 16px",
            backgroundColor: creating ? "#9ca3af" : "#3b82f6",
            color: "white",
            border: "none",
            borderRadius: "6px",
            cursor: creating ? "not-allowed" : "pointer",
            fontWeight: "500",
          }}
        >
          {creating ? "Creating..." : "Create Workflow"}
        </button>
      </div>

      {/* Workflows List */}
      <h2>Active Workflows</h2>

      {workflows.length === 0 && (
        <p style={{ color: "#6b7280" }}>
          No workflows yet. Create one above to get started.
        </p>
      )}

      {workflows.map((wf) => (
        <div
          key={wf.id}
          style={{
            border: "1px solid #e5e7eb",
            borderRadius: "8px",
            padding: "16px",
            marginBottom: "12px",
            backgroundColor: "white",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "start",
              marginBottom: "8px",
            }}
          >
            <strong style={{ flex: 1 }}>{wf.request_text}</strong>
            <StatusBadge state={wf.state} />
          </div>

          {wf.ai_output && (
            <div
              style={{
                marginTop: 8,
                padding: "8px",
                backgroundColor: "#f3f4f6",
                borderRadius: "4px",
                fontSize: "14px",
              }}
            >
              <div>
                <strong>Intent:</strong> {wf.ai_output.intent}
              </div>
              <div>
                <strong>Recommended Action:</strong>{" "}
                {wf.ai_output.recommended_action}
              </div>
              <div>
                <strong>Confidence:</strong>{" "}
                {Math.round(wf.ai_output.confidence * 100)}%
              </div>
            </div>
          )}

          {wf.state === "WAITING_FOR_APPROVAL" && (
            <div style={{ marginTop: 12, display: "flex", gap: "8px" }}>
              <button
                onClick={() => approveWorkflow(wf.id, "approved")}
                disabled={actionInProgress === wf.id}
                style={{
                  padding: "6px 12px",
                  backgroundColor:
                    actionInProgress === wf.id ? "#9ca3af" : "#10b981",
                  color: "white",
                  border: "none",
                  borderRadius: "4px",
                  cursor:
                    actionInProgress === wf.id ? "not-allowed" : "pointer",
                  fontWeight: "500",
                }}
              >
                Approve
              </button>

              <button
                onClick={() => approveWorkflow(wf.id, "rejected")}
                disabled={actionInProgress === wf.id}
                style={{
                  padding: "6px 12px",
                  backgroundColor:
                    actionInProgress === wf.id ? "#9ca3af" : "#ef4444",
                  color: "white",
                  border: "none",
                  borderRadius: "4px",
                  cursor:
                    actionInProgress === wf.id ? "not-allowed" : "pointer",
                  fontWeight: "500",
                }}
              >
                Reject
              </button>
            </div>
          )}

          {wf.human_decision && (
            <div
              style={{
                marginTop: 12,
                fontSize: "13px",
                color: "#6b7280",
              }}
            >
              <strong>Decision:</strong> {wf.human_decision.decision} by{" "}
              {wf.human_decision.reviewer}
              {wf.human_decision.notes && ` - ${wf.human_decision.notes}`}
            </div>
          )}

          <div
            style={{
              marginTop: 8,
              fontSize: "12px",
              color: "#9ca3af",
            }}
          >
            ID: {wf.id.substring(0, 8)}... | Created:{" "}
            {new Date(wf.created_at).toLocaleString()}
          </div>
        </div>
      ))}
    </div>
  );
}