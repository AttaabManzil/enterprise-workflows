import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";

const API_BASE = "http://127.0.0.1:8000";

export default function WorkflowDetails() {
  const { id } = useParams();
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    async function loadEvents() {
      try {
        const res = await fetch(`${API_BASE}/workflows/${id}/events`);
        if (!res.ok) throw new Error("Failed to load timeline");
        const data = await res.json();
        setEvents(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadEvents();
  }, [id]);

  return (
    <div style={{ padding: 20, fontFamily: "sans-serif", maxWidth: "800px" }}>
      <Link to="/">← Back to workflows</Link>

      <h2 style={{ marginTop: 20 }}>Workflow Timeline</h2>

      {loading && <p>Loading timeline…</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}

      {events.length === 0 && <p>No events found.</p>}

      {events.map((event, index) => (
        <div
          key={index}
          style={{
            borderLeft: "3px solid #3b82f6",
            paddingLeft: 12,
            marginBottom: 16,
          }}
        >
          <div style={{ fontSize: 14, fontWeight: "bold" }}>
            {event.event_type}
          </div>

          <div style={{ fontSize: 12, color: "#6b7280" }}>
            {new Date(event.created_at).toLocaleString()}
          </div>

          {event.event_data && (
            <pre
              style={{
                backgroundColor: "#f3f4f6",
                padding: 8,
                marginTop: 6,
                borderRadius: 4,
                fontSize: 12,
                overflowX: "auto",
              }}
            >
              {JSON.stringify(event.event_data, null, 2)}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
