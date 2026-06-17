import type { ReactNode } from 'react';

export function Stat({ label, value, icon }: { label: string; value: string | number; icon: ReactNode }) {
  return <div className="stat"><div className="statIcon">{icon}</div><div><span>{label}</span><strong>{value}</strong></div></div>;
}
