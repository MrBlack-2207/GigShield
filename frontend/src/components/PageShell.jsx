import { Link, NavLink } from "react-router-dom";
import { useWorkerSession } from "../session/WorkerSessionContext";

export default function PageShell({ title, subtitle, children }) {
  const { workerId, workerName, clearWorkerSession } = useWorkerSession();

  return (
    <div className="app-root">
      <header className="topbar">
        <div>
          <Link to="/" className="brand">
            GigShield Demo
          </Link>
          <p className="subtitle">{subtitle || "Parametric cover for Zepto/Blinkit workers"}</p>
        </div>
        <div className="session-pill">
          <span>{workerName || "No worker selected"}</span>
          {workerId ? <code>{workerId.slice(0, 8)}...</code> : null}
          {workerId ? (
            <button className="ghost-btn" onClick={clearWorkerSession}>
              Reset
            </button>
          ) : null}
        </div>
      </header>

      <nav className="tabs">
        <NavLink to="/" end>
          Onboarding
        </NavLink>
        <NavLink to="/policy">Policy</NavLink>
        <NavLink to="/dashboard">Dashboard</NavLink>
        <NavLink to="/claims">Claims</NavLink>
        <NavLink to="/wallet">Wallet</NavLink>
      </nav>

      <main className="page">
        <h1>{title}</h1>
        {children}
      </main>
    </div>
  );
}
