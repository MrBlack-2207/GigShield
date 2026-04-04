import { createContext, useContext, useMemo, useState } from "react";

const STORAGE_KEY = "gigshield_demo_session";

const WorkerSessionContext = createContext(null);

function loadInitialSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { workerId: "", workerName: "" };
    const parsed = JSON.parse(raw);
    return {
      workerId: parsed.workerId || "",
      workerName: parsed.workerName || ""
    };
  } catch {
    return { workerId: "", workerName: "" };
  }
}

export function WorkerSessionProvider({ children }) {
  const [session, setSession] = useState(loadInitialSession);

  const value = useMemo(
    () => ({
      workerId: session.workerId,
      workerName: session.workerName,
      setWorkerSession(next) {
        const payload = {
          workerId: next.workerId || "",
          workerName: next.workerName || ""
        };
        setSession(payload);
        localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
      },
      clearWorkerSession() {
        const payload = { workerId: "", workerName: "" };
        setSession(payload);
        localStorage.removeItem(STORAGE_KEY);
      }
    }),
    [session]
  );

  return <WorkerSessionContext.Provider value={value}>{children}</WorkerSessionContext.Provider>;
}

export function useWorkerSession() {
  const ctx = useContext(WorkerSessionContext);
  if (!ctx) {
    throw new Error("useWorkerSession must be used inside WorkerSessionProvider");
  }
  return ctx;
}
