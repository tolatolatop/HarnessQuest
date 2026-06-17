export const TABS = ['dashboard', 'cases', 'sessions'] as const;
export type Tab = (typeof TABS)[number];
export type RouteState = { tab: Tab; caseId: string | null };

export function parseHash(value: string | null | undefined): RouteState {
  const [rawTab, rawId] = (value ?? '').replace(/^#/, '').split('/');
  const tab = TABS.includes(rawTab as Tab) ? (rawTab as Tab) : 'dashboard';
  return { tab, caseId: tab === 'cases' && rawId ? decodeURIComponent(rawId) : null };
}

export function currentRoute(): RouteState {
  return parseHash(window.location.hash);
}

export function routeHash(tab: Tab, caseId: string | null = null): string {
  return tab === 'cases' && caseId ? `#cases/${encodeURIComponent(caseId)}` : `#${tab}`;
}
