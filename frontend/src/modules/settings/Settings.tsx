import { Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { t } from '../../config/i18n';
import { request } from '../../core/api/client';

type OwnerDto = { id: string; name: string };

export function Settings() {
  const [owners, setOwners] = useState<OwnerDto[]>([]);
  const [newName, setNewName] = useState('');
  const [message, setMessage] = useState('');

  const load = useCallback(() => {
    request<OwnerDto[]>('/responsible-owners').then(setOwners).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function addOwner() {
    const name = newName.trim();
    if (!name) return;
    setMessage('');
    try {
      await request<OwnerDto>('/responsible-owners', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
      setNewName('');
      await load();
    } catch {
      setMessage('添加失败');
    }
  }

  async function deleteOwner(ownerId: string) {
    try {
      await request(`/responsible-owners/${ownerId}`, { method: 'DELETE' });
      setMessage('');
      await load();
    } catch {
      setMessage('删除失败');
    }
  }

  return (
    <section className="panel">
      <div className="panelHeader">
        <h2>{t.responsibleOwner}</h2>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center' }}>
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void addOwner(); } }}
          placeholder={t.responsibleOwnerSelectPlaceholder}
          style={{ flex: 1, maxWidth: 300 }}
        />
        <button onClick={() => void addOwner()}>{t.add}</button>
      </div>

      {message && <p className="muted">{message}</p>}

      {owners.length === 0 && <p className="muted">暂无责任人</p>}

      <table style={{ width: '100%', maxWidth: 500 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>名称</th>
            <th style={{ width: 80 }}></th>
          </tr>
        </thead>
        <tbody>
          {owners.map(o => (
            <tr key={o.id}>
              <td>{o.name}</td>
              <td>
                <button
                  className="iconButton"
                  type="button"
                  aria-label={`delete ${o.name}`}
                  title={`delete ${o.name}`}
                  onClick={() => void deleteOwner(o.id)}
                >
                  <Trash2 size={16} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
