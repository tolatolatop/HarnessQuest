import { Trash2 } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { t } from '../../config/i18n';
import { request } from '../../core/api/client';

type OwnerDto = { id: string; name: string; responsibility_area?: string | null };

export function Settings() {
  const [owners, setOwners] = useState<OwnerDto[]>([]);
  const [newName, setNewName] = useState('');
  const [newArea, setNewArea] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState('');
  const [editArea, setEditArea] = useState('');
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
        body: JSON.stringify({ name, responsibility_area: newArea.trim() || null }),
      });
      setNewName('');
      setNewArea('');
      await load();
    } catch {
      setMessage('添加失败');
    }
  }

  async function saveEdit(ownerId: string) {
    const name = editName.trim();
    if (!name) return;
    try {
      await request<OwnerDto>(`/responsible-owners/${ownerId}`, {
        method: 'PATCH',
        body: JSON.stringify({ name, responsibility_area: editArea.trim() || null }),
      });
      setEditingId(null);
      setMessage('');
      await load();
    } catch {
      setMessage('保存失败');
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

  function startEdit(o: OwnerDto) {
    setEditingId(o.id);
    setEditName(o.name);
    setEditArea(o.responsibility_area ?? '');
  }

  return (
    <section className="panel">
      <div className="panelHeader">
        <h2>{t.responsibleOwner}</h2>
      </div>

      <div style={{ display: 'flex', gap: 8, marginBottom: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void addOwner(); } }}
          placeholder="责任人名称"
          style={{ flex: 1, maxWidth: 200 }}
        />
        <input
          value={newArea}
          onChange={e => setNewArea(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); void addOwner(); } }}
          placeholder={t.responsibilityArea}
          style={{ flex: 1, maxWidth: 200 }}
        />
        <button onClick={() => void addOwner()}>{t.add}</button>
      </div>

      {message && <p className="muted">{message}</p>}

      {owners.length === 0 && <p className="muted">暂无责任人</p>}

      <table style={{ width: '100%', maxWidth: 650 }}>
        <thead>
          <tr>
            <th style={{ textAlign: 'left' }}>{t.responsibleOwner}</th>
            <th style={{ textAlign: 'left' }}>{t.responsibilityArea}</th>
            <th style={{ width: 120 }}></th>
          </tr>
        </thead>
        <tbody>
          {owners.map(o => (
            <tr key={o.id}>
              {editingId === o.id ? (
                <>
                  <td>
                    <input
                      value={editName}
                      onChange={e => setEditName(e.target.value)}
                      style={{ width: '100%' }}
                    />
                  </td>
                  <td>
                    <input
                      value={editArea}
                      onChange={e => setEditArea(e.target.value)}
                      style={{ width: '100%' }}
                    />
                  </td>
                  <td>
                    <button onClick={() => void saveEdit(o.id)}>保存</button>
                    <button className="iconButton" style={{ marginLeft: 4 }} onClick={() => setEditingId(null)}>取消</button>
                  </td>
                </>
              ) : (
                <>
                  <td>{o.name}</td>
                  <td>{o.responsibility_area ?? '—'}</td>
                  <td>
                    <button className="iconButton" type="button" onClick={() => startEdit(o)}>✏️</button>
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
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
