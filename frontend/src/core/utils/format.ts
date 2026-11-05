import { t } from '../../config/i18n';

export function parseTags(value: string): string[] {
  return Array.from(new Set(value.split(/[,\s，]+/).map(item => item.trim()).filter(Boolean)));
}

export function relativeTime(value: string): string {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return '-';
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return t.justNow;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return t.minutesAgo.replace('{count}', String(minutes));
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t.hoursAgo.replace('{count}', String(hours));
  const days = Math.floor(hours / 24);
  if (days < 30) return t.daysAgo.replace('{count}', String(days));
  const months = Math.floor(days / 30);
  if (months < 12) return t.monthsAgo.replace('{count}', String(months));
  const years = Math.floor(days / 365);
  return t.yearsAgo.replace('{count}', String(years));
}

/** Local wall-clock time down to the second, e.g. 2026-11-05 15:04:09. */
export function formatLocalTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (part: number) => String(part).padStart(2, '0');
  const day = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
  const time = `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
  return `${day} ${time}`;
}
