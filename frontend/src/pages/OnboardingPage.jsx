import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import PageShell from "../components/PageShell";
import { ErrorState, InfoState, LoadingState } from "../components/StatusState";
import { contractApi } from "../services/contractApi";
import { useWorkerSession } from "../session/WorkerSessionContext";

const PLATFORM_OPTIONS = [
  { value: "zepto", label: "Zepto" },
  { value: "blinkit", label: "Blinkit" }
];

const DEFAULT_FORM = {
  full_name: "",
  phone: "",
  income_tier: 600,
  platform: "zepto",
  home_store_id: "",
  external_worker_id: "",
  aadhaar: ""
};

export default function OnboardingPage() {
  const navigate = useNavigate();
  const { workerId, workerName, setWorkerSession } = useWorkerSession();
  const [form, setForm] = useState(DEFAULT_FORM);
  const [stores, setStores] = useState([]);
  const [loadingStores, setLoadingStores] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    async function loadStores() {
      setLoadingStores(true);
      setError("");
      try {
        const rows = await contractApi.getStores(form.platform);
        setStores(rows);
        if (rows.length > 0) {
          setForm((prev) => ({
            ...prev,
            home_store_id: rows.some((s) => s.id === prev.home_store_id) ? prev.home_store_id : rows[0].id
          }));
        } else {
          setForm((prev) => ({ ...prev, home_store_id: "" }));
        }
      } catch (err) {
        setError(err.message);
        setStores([]);
      } finally {
        setLoadingStores(false);
      }
    }

    loadStores();
  }, [form.platform]);

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    setSuccess("");
    setSubmitting(true);
    try {
      const payload = {
        full_name: form.full_name.trim(),
        phone: form.phone.trim(),
        income_tier: Number(form.income_tier),
        platform: form.platform,
        home_store_id: form.home_store_id,
        external_worker_id: form.external_worker_id.trim() || null,
        aadhaar: form.aadhaar.trim() || null
      };
      const worker = await contractApi.createWorker(payload);
      setWorkerSession({ workerId: worker.worker_id, workerName: worker.full_name });
      setSuccess("Worker registered. Continue to policy purchase.");
      navigate("/policy");
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <PageShell title="Onboarding" subtitle="Register worker and lock platform + home store">
      {workerId ? (
        <InfoState message={`Current worker: ${workerName || "Worker"} (${workerId.slice(0, 8)}...)`} />
      ) : null}
      <ErrorState error={error} />
      <InfoState message={success} />

      <form className="card form-grid" onSubmit={handleSubmit}>
        <label>
          Full Name
          <input
            required
            value={form.full_name}
            onChange={(e) => setForm((prev) => ({ ...prev, full_name: e.target.value }))}
          />
        </label>

        <label>
          Phone
          <input
            required
            value={form.phone}
            onChange={(e) => setForm((prev) => ({ ...prev, phone: e.target.value }))}
          />
        </label>

        <label>
          Income Tier (INR/day)
          <select
            value={form.income_tier}
            onChange={(e) => setForm((prev) => ({ ...prev, income_tier: Number(e.target.value) }))}
          >
            <option value={400}>400</option>
            <option value={600}>600</option>
            <option value={800}>800</option>
          </select>
        </label>

        <label>
          Platform
          <select
            value={form.platform}
            onChange={(e) => setForm((prev) => ({ ...prev, platform: e.target.value }))}
          >
            {PLATFORM_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label>
          Dark Store
          <select
            required
            value={form.home_store_id}
            onChange={(e) => setForm((prev) => ({ ...prev, home_store_id: e.target.value }))}
          >
            {stores.map((store) => (
              <option key={store.id} value={store.id}>
                {store.name} ({store.zone_id})
              </option>
            ))}
          </select>
          {loadingStores ? <LoadingState label="Loading stores..." /> : null}
        </label>

        <label>
          External Worker ID (optional)
          <input
            value={form.external_worker_id}
            onChange={(e) => setForm((prev) => ({ ...prev, external_worker_id: e.target.value }))}
          />
        </label>

        <label>
          Aadhaar (optional)
          <input
            value={form.aadhaar}
            onChange={(e) => setForm((prev) => ({ ...prev, aadhaar: e.target.value }))}
          />
        </label>

        <div className="form-actions">
          <button disabled={submitting || loadingStores || !form.home_store_id} type="submit">
            {submitting ? "Registering..." : "Register Worker"}
          </button>
          {workerId ? (
            <button type="button" className="ghost-btn" onClick={() => navigate("/dashboard")}>
              Continue with Existing Worker
            </button>
          ) : null}
        </div>
      </form>
    </PageShell>
  );
}
