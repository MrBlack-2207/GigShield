import { Navigate } from "react-router-dom";
import { useWorkerSession } from "../session/WorkerSessionContext";

export default function RequireWorker({ children }) {
  const { workerId } = useWorkerSession();
  if (!workerId) return <Navigate to="/" replace />;
  return children;
}
