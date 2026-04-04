export function LoadingState({ label = "Loading..." }) {
  return <p className="loading">{label}</p>;
}

export function ErrorState({ error, onRetry }) {
  if (!error) return null;
  return (
    <div className="error-box">
      <p>{error}</p>
      {onRetry ? (
        <button className="ghost-btn" onClick={onRetry}>
          Retry
        </button>
      ) : null}
    </div>
  );
}

export function InfoState({ message }) {
  if (!message) return null;
  return <div className="info-box">{message}</div>;
}
