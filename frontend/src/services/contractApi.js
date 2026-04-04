const API_BASE = import.meta.env.VITE_API_BASE_URL || "";
const CONTRACT_ROOT = `${API_BASE}/api/contract`;

async function request(path, options = {}) {
  const response = await fetch(`${CONTRACT_ROOT}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload.detail || payload.message || message;
    } catch {
      // no-op
    }
    throw new Error(message);
  }

  if (response.status === 204) return null;
  return response.json();
}

export const contractApi = {
  getStores(platform) {
    const qs = platform ? `?platform=${encodeURIComponent(platform)}` : "";
    return request(`/stores${qs}`);
  },
  createWorker(payload) {
    return request("/workers", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  quotePolicy(payload) {
    return request("/policies/quote", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  purchasePolicy(payload) {
    return request("/policies/purchase", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  getWorkerPolicy(workerId) {
    return request(`/workers/${workerId}/policy`);
  },
  getWorkerDashboard(workerId) {
    return request(`/workers/${workerId}/dashboard`);
  },
  getWorkerClaims(workerId, limit = 100) {
    return request(`/workers/${workerId}/claims?limit=${limit}`);
  },
  getWorkerWallet(workerId, recentLimit = 10) {
    return request(`/workers/${workerId}/wallet?recent_limit=${recentLimit}`);
  },
  cashoutWallet(workerId) {
    return request(`/workers/${workerId}/wallet/cashout`, { method: "POST" });
  },
  demoActivatePolicy(workerId) {
    return request(`/demo/workers/${workerId}/activate-policy`, { method: "POST" });
  },
  demoFireTrigger(payload) {
    return request("/demo/triggers/fire", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  },
  demoRunClaims(payload) {
    return request("/demo/claims/run", {
      method: "POST",
      body: JSON.stringify(payload)
    });
  }
};
