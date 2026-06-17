import type { SyntheticEvent } from 'react';
import { useEffect, useState } from 'react';
import { API_BASE_URL } from '../../config/env';
import { t } from '../../config/i18n';
import { ApiError, request } from '../../core/api/client';

function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return t.loginInvalid;
    }
    if (err.status === 422) {
      return t.loginBadRequest;
    }
    return t.loginFailed;
  }
  return t.loginNetworkFailed;
}

export function Login({ onLogin }: { onLogin: () => void }) {
  const [username, setUsername] = useState('admin@harnessquest.local');
  const [password, setPassword] = useState('admin123456');
  const [error, setError] = useState('');
  const [oidcEnabled, setOidcEnabled] = useState(false);
  useEffect(() => {
    void fetch(`${API_BASE_URL}/api/v1/auth/oauth/status`)
      .then(res => res.json() as Promise<{ enabled: boolean }>)
      .then(data => setOidcEnabled(data.enabled))
      .catch(() => setOidcEnabled(false));
  }, []);
  async function submit(e: SyntheticEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    try {
      const data = await request<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
      localStorage.setItem('hq_token', data.access_token);
      onLogin();
    } catch (err) {
      setError(loginErrorMessage(err));
    }
  }
  return (
    <main className="login">
      <form className="loginPanel" onSubmit={submit}>
        <h1>HarnessQuest</h1>
        <p>{t.appSubtitle}</p>
        <label>{t.email}<input value={username} onChange={e => setUsername(e.target.value)} /></label>
        <label>{t.password}<input type="password" value={password} onChange={e => setPassword(e.target.value)} /></label>
        {error && <div className="error">{error}</div>}
        <button>{t.signIn}</button>
        {oidcEnabled && <a className="oauthButton" href={`${API_BASE_URL}/api/v1/auth/oauth/login`}>{t.signInWithOAuth}</a>}
      </form>
    </main>
  );
}
