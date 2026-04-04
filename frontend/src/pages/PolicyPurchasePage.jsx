import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import PageShell from "../components/PageShell";
import RequireWorker from "../components/RequireWorker";
import { ErrorState, InfoState, LoadingState } from "../components/StatusState";
import { contractApi } from "../services/contractApi";
import { useWorkerSession } from "../session/WorkerSessionContext";

function PolicyPurchaseContent() {
  const navigate = useNavigate();
  const { workerId } = useWorkerSession();
  const [tenureMonths, setTenureMonths] = useState(1);
  const [loadingPolicy, setLoadingPolicy] = useState(false);
  const [quoting, setQuoting] = useState(false);
  const [purchasing, setPurchasing] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");
  const [policyEnvelope, setPolicyEnvelope] = useState(null);
  const [quote, setQuote] = useState(null);

  async function refreshPolicy() {
    setLoadingPolicy(true);
    setError("");
    try {
      const response = await contractApi.getWorkerPolicy(workerId);
      setPolicyEnvelope(response);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoadingPolicy(false);
    }
  }

  useEffect(() => {
    refreshPolicy();
  }, [workerId]);

  async function handleQuote() {
    setQuoting(true);
    setError("");
    setInfo("");
    try {
      const response = await contractApi.quotePolicy({
        worker_id: workerId,
        tenure_months: tenureMonths
      });
      setQuote(response);
    } catch (err) {
      setError(err.message);
      setQuote(null);
    } finally {
      setQuoting(false);
    }
  }

  async function handlePurchase() {
    setPurchasing(true);
    setError("");
    setInfo("");
    try {
      await contractApi.purchasePolicy({
        worker_id: workerId,
        tenure_months: tenureMonths
      });
      setInfo("Policy purchased. First weekly premium collected. Policy starts in pending_activation.");
      setQuote(null);
      await refreshPolicy();
    } catch (err) {
      setError(err.message);
    } finally {
      setPurchasing(false);
    }
  }

  const activePolicy = policyEnvelope?.policy || null;

  return (
    <PageShell title="Policy Purchase" subtitle="Get quote and purchase weekly-billed policy">
      <ErrorState error={error} />
      <InfoState message={info} />

      <section className="card">
        <h2>Current Policy</h2>
        {loadingPolicy ? <LoadingState label="Loading current policy..." /> : null}
        {!loadingPolicy && !activePolicy ? <p>No policy yet.</p> : null}
        {activePolicy ? (
          <div className="kv-grid">
            <div>Status</div>
            <div>
              <strong>{activePolicy.effective_status}</strong> (stored: {activePolicy.status})
            </div>
            <div>Weekly Premium</div>
            <div>INR {activePolicy.weekly_premium_inr}</div>
            <div>Weekly Payout Cap</div>
            <div>INR {activePolicy.weekly_payout_cap_inr}</div>
            <div>Cooldown Ends</div>
            <div>{new Date(activePolicy.cooldown_ends_at).toLocaleString()}</div>
            <div>Next Premium Due</div>
            <div>{new Date(activePolicy.next_premium_due_at).toLocaleString()}</div>
            <div>Payout Eligible Now</div>
            <div>{activePolicy.payout_eligible_now ? "Yes" : "No"}</div>
          </div>
        ) : null}
      </section>

      <section className="card">
        <h2>Quote + Purchase</h2>
        <div className="inline-controls">
          <label>
            Tenure
            <select value={tenureMonths} onChange={(e) => setTenureMonths(Number(e.target.value))}>
              <option value={1}>1 month</option>
              <option value={3}>3 months</option>
              <option value={6}>6 months</option>
              <option value={12}>12 months</option>
            </select>
          </label>
          <button onClick={handleQuote} disabled={quoting || purchasing}>
            {quoting ? "Quoting..." : "Get Quote"}
          </button>
          <button onClick={handlePurchase} disabled={purchasing || quoting}>
            {purchasing ? "Purchasing..." : "Purchase Policy"}
          </button>
          <button className="ghost-btn" onClick={() => navigate("/dashboard")}>
            Go to Dashboard
          </button>
        </div>

        {quote ? (
          <div className="quote-box">
            <p>
              Weekly Premium: <strong>INR {quote.weekly_premium_inr}</strong>
            </p>
            <p>
              Weekly Payout Cap: <strong>INR {quote.weekly_payout_cap_inr}</strong>
            </p>
            <p>
              Coverage Ratio: <strong>{quote.coverage_ratio}</strong>
            </p>
            <p>
              Seasonal Disruption Days: <strong>{quote.seasonal_disruption_days}</strong> ({quote.disruption_days_source})
            </p>
            <p className="muted">First weekly premium is paid at purchase. Policy begins in pending_activation for 48 hours.</p>
          </div>
        ) : null}
      </section>
    </PageShell>
  );
}

export default function PolicyPurchasePage() {
  return (
    <RequireWorker>
      <PolicyPurchaseContent />
    </RequireWorker>
  );
}
