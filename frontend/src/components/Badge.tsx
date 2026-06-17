import { label } from '../config/i18n';

function toneClass(value: string | undefined): string {
  return (value ?? 'unknown').replace(/[^a-z0-9_-]/gi, '-').toLowerCase();
}

export function Badge({ value, type = 'neutral' }: { value: string | undefined; type?: 'status' | 'severity' | 'neutral' }) {
  return <span className={`badge ${type} ${toneClass(value)}`}>{label(value)}</span>;
}
