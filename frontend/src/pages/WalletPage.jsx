import { useEffect, useState } from "react";

import PageShell from "../components/PageShell";
import RequireWorker from "../components/RequireWorker";
import { ErrorState, InfoState, LoadingState } from "../components/StatusState";
import { contractApi } from "../services/contractApi";
import { useWorkerSession } from "../session/WorkerSessionContext";

function WalletContent() {
  const { workerId } = useWorkerSession();
  const [wallet, setWallet] = useState(null);
  const [loading, setLoading] = useState(false);
  const [cashingOut, setCashingOut] = useState(false);
  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  async function loadWallet() {
    setLoading(true);
    setError("");
    try {
      const data = await contractApi.getWorkerWallet(workerId, 20);
      setWallet(data);
    } catch (err) {
      setError(err.message);
      setWallet(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadWallet();
  }, [workerId]);

  async function handleCashout() {
    setCashingOut(true);
    setError("");
    setInfo("");
    try {
      const result = await contractApi.cashoutWallet(workerId);
      setInfo(`Cashout completed. Withdrawn INR ${result.withdrawn_amount}`);
      await loadWallet();
    } catch (err) {
      setError(err.message);
    } finally {
      setCashingOut(false);
    }
  }

  const balance = Number(wallet?.wallet_balance_inr || 0);

  return (
    <PageShell title="Wallet / Cashout" subtitle="Ledger-backed balance and full-balance withdrawal">
      <ErrorState error={error} onRetry={loadWallet} />
      <InfoState message={info} />
      {loading ? <LoadingState label="Loading wallet..." /> : null}

      <section className="card">
        <h2>Balance</h2>
        <p className="metric">INR {balance.toFixed(2)}</p>
        <div className="inline-controls">
          <button onClick={handleCashout} disabled={cashingOut || balance <= 0}>
            {cashingOut ? "Processing..." : "Cashout Full Balance"}
          </button>
          <button className="ghost-btn" onClick={loadWallet}>
            Refresh
          </button>
        </div>
      </section>

      <section className="card">
        <h2>Recent Ledger Entries</h2>
        {!wallet?.recent_entries?.length ? <p>No entries yet.</p> : null}
        {(wallet?.recent_entries || []).map((entry) => (
          <div className="list-row" key={entry.id}>
            <div>
              <p>
                <strong>{entry.entry_type}</strong> • INR {entry.amount_inr}
              </p>
              <p className="muted">ref: {entry.reference_id || "-"}</p>
            </div>
            <div className="right muted">{new Date(entry.created_at).toLocaleString()}</div>
          </div>
        ))}
      </section>
    </PageShell>
  );
}

export default function WalletPage() {
  return (
    <RequireWorker>
      <WalletContent />
    </RequireWorker>
  );
}
