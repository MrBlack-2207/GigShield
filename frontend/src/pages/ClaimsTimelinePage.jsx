import { useEffect, useState } from "react";

import PageShell from "../components/PageShell";
import RequireWorker from "../components/RequireWorker";
import { ErrorState, LoadingState } from "../components/StatusState";
import { contractApi } from "../services/contractApi";
import { useWorkerSession } from "../session/WorkerSessionContext";

function ClaimsTimelineContent() {
  const { workerId } = useWorkerSession();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function loadClaims() {
    setLoading(true);
    setError("");
    try {
      const data = await contractApi.getWorkerClaims(workerId, 200);
      setItems(data.items || []);
    } catch (err) {
      setError(err.message);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadClaims();
  }, [workerId]);

  return (
    <PageShell title="Claims Timeline" subtitle="Payout and transparency trail">
      <ErrorState error={error} onRetry={loadClaims} />
      {loading ? <LoadingState label="Loading claims timeline..." /> : null}

      <section className="card">
        <div className="card-header">
          <h2>Claims</h2>
          <button className="ghost-btn" onClick={loadClaims}>
            Refresh
          </button>
        </div>
        {items.length === 0 && !loading ? <p>No claims found yet.</p> : null}
        {items.map((item) => (
          <article key={item.claim_id} className="claim-card">
            <div className="claim-head">
              <strong>{item.status}</strong>
              <span>INR {item.payout_amount}</span>
            </div>
            <p className="muted">{new Date(item.triggered_at).toLocaleString()}</p>
            <div className="kv-grid compact">
              <div>claim_id</div>
              <div>{item.claim_id}</div>
              <div>base_zdi</div>
              <div>{item.base_zdi ?? "-"}</div>
              <div>event_boost_total</div>
              <div>{item.event_boost_total ?? "-"}</div>
              <div>final_zdi</div>
              <div>{item.final_zdi ?? "-"}</div>
              <div>affected_hours_used</div>
              <div>
                {item.affected_hours_used} ({item.affected_hours_source})
              </div>
              <div>payout_rate_used</div>
              <div>
                {item.payout_rate_used} ({item.payout_rate_source})
              </div>
              <div>wallet_credited</div>
              <div>{item.wallet_credited ? "Yes" : "No"}</div>
            </div>
          </article>
        ))}
      </section>
    </PageShell>
  );
}

export default function ClaimsTimelinePage() {
  return (
    <RequireWorker>
      <ClaimsTimelineContent />
    </RequireWorker>
  );
}
