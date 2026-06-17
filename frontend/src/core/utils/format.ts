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
