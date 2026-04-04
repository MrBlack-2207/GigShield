import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import PageShell from "../components/PageShell";
import RequireWorker from "../components/RequireWorker";
import { ErrorState, InfoState, LoadingState } from "../components/StatusState";
import { contractApi } from "../services/contractApi";
import { useWorkerSession } from "../session/WorkerSessionContext";

function DashboardContent() {
  const { workerId } = useWorkerSession();
  const [dashboard, setDashboard] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState("");
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [showDemoControls, setShowDemoControls] = useState(false);

  async function refresh() {
    setLoading(true);
    setError("");
    try {
      const data = await contractApi.getWorkerDashboard(workerId);
      setDashboard(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [workerId]);

  useEffect(() => {
    function onKeyDown(event) {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "d") {
        setShowDemoControls((prev) => !prev);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  async function runAction(label, fn) {
    setError("");
    setInfo("");
    setActionLoading(label);
    try {
      const result = await fn();
      let summary = `${label} completed${result?.status ? `: ${result.status}` : ""}`;
      if (result && typeof result === "object") {
        if (typeof result.processed === "number") {
          summary += ` | processed=${result.processed}, flagged=${result.flagged ?? 0}, paid=${result.paid ?? 0}`;
        }
        if (result.target_zone_id) {
          summary += ` | zone=${result.target_zone_id}`;
        }
      }
      setInfo(summary);
      await refresh();
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading("");
    }
  }

  const policy = dashboard?.policy;
  const latestZdi = dashboard?.latest_zdi;
  const recentClaims = dashboard?.recent_claims || [];

  return (
    <PageShell title="Dashboard" subtitle="Main demo control center">
      <ErrorState error={error} />
      <InfoState message={info} />
      {loading ? <LoadingState label="Loading dashboard..." /> : null}

      {dashboard ? (
        <>
          <section className="card two-col">
            <div>
              <h2>Worker</h2>
              <p>{dashboard.full_name}</p>
              <p className="muted">
                {dashboard.platform} • Store {dashboard.home_store_id} • Zone {dashboard.primary_zone_id}
              </p>
            </div>
            <div>
              <h2>Wallet</h2>
              <p className="metric">INR {dashboard.wallet_balance_inr}</p>
              <p className="muted">
                Claims: {dashboard.claims_count} total • {dashboard.paid_claims_count} paid
              </p>
              <p className="muted">Total paid: INR {dashboard.total_payout_paid_inr}</p>
            </div>
          </section>

          <section className="card">
            <h2>Policy Status</h2>
            {!policy ? <p>No policy found yet.</p> : null}
            {policy ? (
              <div className="kv-grid">
                <div>Effective Status</div>
                <div>
                  <strong>{policy.effective_status}</strong> (stored: {policy.status})
                </div>
                <div>Weekly Premium</div>
                <div>INR {policy.weekly_premium_inr}</div>
                <div>Weekly Cap</div>
                <div>INR {policy.weekly_payout_cap_inr}</div>
                <div>Payout Eligible Now</div>
                <div>{policy.payout_eligible_now ? "Yes" : "No"}</div>
                <div>Cooldown Ends</div>
                <div>{new Date(policy.cooldown_ends_at).toLocaleString()}</div>
              </div>
            ) : null}
          </section>

          <section className="card">
            <h2>Latest ZDI Transparency</h2>
            {!latestZdi ? <p>No ZDI yet.</p> : null}
            {latestZdi ? (
              <div className="kv-grid">
                <div>base_zdi</div>
                <div>{latestZdi.base_zdi ?? "-"}</div>
                <div>event_boost_total</div>
                <div>{latestZdi.event_boost_total ?? "-"}</div>
                <div>final_zdi</div>
                <div>{latestZdi.final_zdi ?? "-"}</div>
                <div>timestamp</div>
                <div>{latestZdi.timestamp ? new Date(latestZdi.timestamp).toLocaleString() : "-"}</div>
              </div>
            ):null }
          </section>

          <section className="card">
            <div className="card-header">
              <h2>Recent Claims</h2>
              <Link to="/claims" className="link-btn">
                Open Timeline
              </Link>
            </div>
            {recentClaims.length === 0 ? <p>No claims yet.</p> : null}
            {recentClaims.map((item) => (
              <div className="list-row" key={item.claim_id}>
                <div>
                  <p>
                    <strong>{item.status}</strong> • INR {item.payout_amount}
                  </p>
                  <p className="muted">
                    payout_rate_used={item.payout_rate_used} ({item.payout_rate_source}) • affected_hours_used=
                    {item.affected_hours_used} ({item.affected_hours_source})
                  </p>
                </div>
                <div className="right muted">{new Date(item.triggered_at).toLocaleString()}</div>
              </div>
            ))}
          </section>
        </>
      ) : null}

      <section className="card">
        <div className="card-header">
          <h2>Demo Controls</h2>
          <button className="ghost-btn" onClick={() => setShowDemoControls((prev) => !prev)}>
            {showDemoControls ? "Hide" : "Show"}
          </button>
        </div>
        {!showDemoControls ? (
          <p className="muted">Hidden for demo flow. Shortcut: Ctrl+Shift+D</p>
        ) : (
          <div className="inline-controls stacked-mobile">
            <button
              onClick={() => runAction("Activate policy", () => contractApi.demoActivatePolicy(workerId))}
              disabled={!!actionLoading}
            >
              {actionLoading === "Activate policy" ? "Working..." : "Activate Policy"}
            </button>
            <button
              onClick={() =>
                runAction("Fire deterministic outage", () =>
                  (async () => {
                    await contractApi.demoFireTrigger({
                      worker_id: workerId,
                      scenario: "outage_on",
                      cycles: 1
                    });
                    return contractApi.demoFireTrigger({
                      worker_id: workerId,
                      scenario: "outage_off",
                      cycles: 1
                    });
                  })()
                )
              }
              disabled={!!actionLoading}
            >
              {actionLoading === "Fire deterministic outage" ? "Working..." : "Fire Deterministic Outage"}
            </button>
            <button
              onClick={() =>
                runAction("Run claims", () =>
                  contractApi.demoRunClaims({
                    worker_id: workerId,
                    skip_fraud_checks: true,
                    limit: 200
                  })
                )
              }
              disabled={!!actionLoading}
            >
              {actionLoading === "Run claims" ? "Working..." : "Run Claims (Flag + Credit Demo)"}
            </button>
            <button
              className="ghost-btn"
              onClick={() =>
                runAction("Run full demo flow", async () => {
                  await contractApi.demoActivatePolicy(workerId);
                  await contractApi.demoFireTrigger({
                    worker_id: workerId,
                    scenario: "outage_on",
                    cycles: 1
                  });
                  await contractApi.demoFireTrigger({
                    worker_id: workerId,
                    scenario: "outage_off",
                    cycles: 1
                  });
                  await contractApi.demoRunClaims({
                    worker_id: workerId,
                    skip_fraud_checks: true,
                    limit: 200
                  });
                  return contractApi.demoRunClaims({
                    worker_id: workerId,
                    skip_fraud_checks: true,
                    limit: 200
                  });
                })
              }
              disabled={!!actionLoading}
            >
              {actionLoading === "Run full demo flow" ? "Working..." : "One-Click Demo Claim"}
            </button>
            <button className="ghost-btn" onClick={refresh} disabled={loading || !!actionLoading}>
              Refresh Dashboard
            </button>
          </div>
        )}
      </section>
    </PageShell>
  );
}

export default function DashboardPage() {
  return (
    <RequireWorker>
      <DashboardContent />
    </RequireWorker>
  );
}
