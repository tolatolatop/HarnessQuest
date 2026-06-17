import { useEffect, useState } from 'react';
import { MainLayout } from './layouts/MainLayout';
import { Login } from './modules/auth';
import { Cases } from './modules/cases';
import { Dashboard } from './modules/dashboard';
import { Sessions } from './modules/sessions';
import { request } from './core/api/client';
import { currentRoute, routeHash, type RouteState, type Tab } from './routes/hashRoute';
import type { User } from './types/domain';

export function App() {
  const [token, setToken] = useState(localStorage.getItem('hq_token'));
  const [route, setRoute] = useState<RouteState>(currentRoute);
  const [user, setUser] = useState<User | null>(null);
  const tab = route.tab;
  useEffect(() => {
    if (token) {
      void request<User>('/auth/me').then(setUser).catch(() => { localStorage.removeItem('hq_token'); setToken(null); });
    }
  }, [token]);
  useEffect(() => {
    const onHashChange = () => setRoute(currentRoute());
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);
  function navigate(nextTab: Tab, caseId: string | null = null) {
    const nextHash = routeHash(nextTab, caseId);
    if (window.location.hash === nextHash) {
      setRoute({ tab: nextTab, caseId: nextTab === 'cases' ? caseId : null });
      return;
    }
    window.location.hash = nextHash;
  }
  function logout() {
    localStorage.removeItem('hq_token');
    setToken(null);
  }
  if (!token) return <Login onLogin={() => setToken(localStorage.getItem('hq_token'))} />;
  const content = tab === 'dashboard' ? <Dashboard /> : tab === 'sessions' ? <Sessions /> : <Cases selectedCaseId={route.caseId} onSelectCase={caseId => navigate('cases', caseId)} />;
  return (
    <MainLayout tab={tab} user={user} onNavigate={navigate} onLogout={logout}>
      {content}
    </MainLayout>
  );
}
