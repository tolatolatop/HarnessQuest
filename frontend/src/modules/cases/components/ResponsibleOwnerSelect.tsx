import { useCallback, useEffect, useRef, useState } from 'react';
import { X } from 'lucide-react';
import { t } from '../../../config/i18n';
import { request } from '../../../core/api/client';

type ResponsibleOwnerDto = { id: string; name: string };

type ResponsibleOwnerSelectProps = {
  value: string;
  onChange: (value: string) => void;
};

export function ResponsibleOwnerSelect({ value, onChange }: ResponsibleOwnerSelectProps) {
  const [owners, setOwners] = useState<ResponsibleOwnerDto[]>([]);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(() => {
    request<ResponsibleOwnerDto[]>('/responsible-owners').then(setOwners).catch(() => {});
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (adding && inputRef.current) {
      inputRef.current.focus();
    }
  }, [adding]);

  async function addNew() {
    const name = newName.trim();
    if (!name) return;
    try {
      const created = await request<ResponsibleOwnerDto>('/responsible-owners', {
        method: 'POST',
        body: JSON.stringify({ name }),
      });
      onChange(created.name);
      setNewName('');
      setAdding(false);
      await load();
    } catch {
      // ignore
    }
  }

  function handleSelect(e: React.ChangeEvent<HTMLSelectElement>) {
    const val = e.target.value;
    if (val === '__add_new__') {
      setAdding(true);
      return;
    }
    onChange(val);
  }

  return (
    <div className="responsibleOwnerSelect">
      <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
        <select value={value} onChange={handleSelect} style={{ flex: 1 }}>
          <option value="">—</option>
          {owners.map(o => (
            <option key={o.id} value={o.name}>
              {o.name}
            </option>
          ))}
          <option value="__add_new__">+ {t.addResponsibleOwner}</option>
        </select>
        {value && (
          <button
            className="iconButton"
            type="button"
            aria-label="clear"
            title="clear"
            onClick={() => onChange('')}
          >
            <X size={16} />
          </button>
        )}
      </div>
      {adding && (
        <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
          <input
            ref={inputRef}
            value={newName}
            onChange={e => setNewName(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter') {
                e.preventDefault();
                void addNew();
              }
              if (e.key === 'Escape') {
                setAdding(false);
                setNewName('');
              }
            }}
            placeholder={t.responsibleOwnerSelectPlaceholder}
            style={{ flex: 1 }}
          />
          <button type="button" onClick={() => void addNew()}>
            {t.add}
          </button>
          <button type="button" onClick={() => { setAdding(false); setNewName(''); }}>
            {t.close}
          </button>
        </div>
      )}
    </div>
  );
}
