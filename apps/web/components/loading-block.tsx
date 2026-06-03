export function LoadingBlock({ label = "Loading..." }: { label?: string }) {
  return <div className="panel muted">{label}</div>;
}

