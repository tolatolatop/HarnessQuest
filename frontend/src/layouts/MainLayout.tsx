import { BarChart3, Bot, ClipboardList, LogOut } from 'lucide-react';
import { t } from '../config/i18n';
import type { User } from '../types/domain';
import type { Tab } from '../routes/hashRoute';

function pageSubtitle(tab: string): string {
  if (tab === 'dashboard') return t.dashboardSubtitle;
  if (tab === 'cases') return t.casesSubtitle;
  return t.sessionsSubtitle;
}

function pageTitle(tab: string): string {
  if (tab === 'dashboard') return t.dashboard;
  if (tab === 'cases') return t.cases;
  return t.sessions;
}

export function MainLayout({
  tab,
  user,
  children,
  onNavigate,
  onLogout,
}: {
  tab: Tab;
  user: User | null;
  children: React.ReactNode;
  onNavigate: (tab: Tab) => void;
  onLogout: () => void;
}) {
  return (
    <main className="app">
      <aside>
        <div className="brandBlock">
          <h1>HarnessQuest</h1>
          <span>{t.workspaceKicker}</span>
        </div>
        <button className={tab === 'dashboard' ? 'active' : ''} onClick={() => onNavigate('dashboard')}><BarChart3 size={18} /> {t.dashboard}</button>
        <button className={tab === 'cases' ? 'active' : ''} onClick={() => onNavigate('cases')}><ClipboardList size={18} /> {t.cases}</button>
        <button className={tab === 'sessions' ? 'active' : ''} onClick={() => onNavigate('sessions')}><Bot size={18} /> {t.sessions}</button>
        <div className="spacer" />
        <p><span>{t.activeOperator}</span>{user?.display_name}</p>
        <button onClick={onLogout}><LogOut size={18} /> {t.logout}</button>
      </aside>
      <section className="content">
        <header className="workspaceHeader">
          <div>
            <p>{t.workspaceKicker}</p>
            <h2>{pageTitle(tab)}</h2>
          </div>
          <span>{pageSubtitle(tab)}</span>
        </header>
        {children}
      </section>
    </main>
  );
}
