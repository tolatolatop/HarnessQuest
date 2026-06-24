import { useCallback, useEffect, useRef, useState } from 'react';
import { useEditor, EditorContent, type Editor } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import ImageExtension from '@tiptap/extension-image';
import Placeholder from '@tiptap/extension-placeholder';
import { API_BASE_URL } from '../config/env';

type RichTextEditorProps = {
  value: string;
  onChange: (html: string) => void;
  placeholder?: string;
  editable?: boolean;
};

function ToolbarButton({
  editor,
  label,
  icon,
  action,
  isActive,
}: {
  editor: Editor;
  label: string;
  icon: React.ReactNode;
  action: () => void;
  isActive?: (editor: Editor) => boolean;
}) {
  const active = isActive?.(editor) ?? false;
  return (
    <button
      type="button"
      className={`rteToolbarBtn${active ? ' active' : ''}`}
      aria-label={label}
      title={label}
      onClick={(e) => {
        e.preventDefault();
        action();
      }}
    >
      {icon}
    </button>
  );
}

async function uploadImage(file: File, editor: Editor) {
  const token = localStorage.getItem('hq_token');
  const formData = new FormData();
  formData.set('file', file);

  const headers: Record<string, string> = {};
  if (token) {
    headers['Authorization'] = 'Bearer ' + token;
  }

  const res = await fetch(API_BASE_URL + '/api/v1/uploads/images', {
    method: 'POST',
    headers,
    body: formData,
  });

  if (!res.ok) throw new Error('Upload failed');

  const data = (await res.json()) as { url: string };
  editor.chain().focus().setImage({ src: data.url }).run();
}

function Toolbar({ editor }: { editor: Editor }) {
  const [uploading, setUploading] = useState(false);

  const addImage = useCallback(() => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = 'image/*';
    input.onchange = async () => {
      const file = input.files?.[0];
      if (!file) return;
      setUploading(true);
      try {
        await uploadImage(file, editor);
      } catch {
        // silent
      } finally {
        setUploading(false);
      }
    };
    input.click();
  }, [editor]);

  return (
    <div className="rteToolbar">
      <ToolbarButton
        editor={editor}
        label="粗体"
        icon={<strong>B</strong>}
        action={() => editor.chain().focus().toggleBold().run()}
        isActive={(e) => e.isActive('bold')}
      />
      <ToolbarButton
        editor={editor}
        label="斜体"
        icon={<em>I</em>}
        action={() => editor.chain().focus().toggleItalic().run()}
        isActive={(e) => e.isActive('italic')}
      />
      <ToolbarButton
        editor={editor}
        label="标题"
        icon={<span style={{ fontWeight: 800, fontSize: 15 }}>H</span>}
        action={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
        isActive={(e) => e.isActive('heading', { level: 3 })}
      />
      <ToolbarButton
        editor={editor}
        label="无序列表"
        icon={<span>&#8226;</span>}
        action={() => editor.chain().focus().toggleBulletList().run()}
        isActive={(e) => e.isActive('bulletList')}
      />
      <ToolbarButton
        editor={editor}
        label="有序列表"
        icon={<span>1.</span>}
        action={() => editor.chain().focus().toggleOrderedList().run()}
        isActive={(e) => e.isActive('orderedList')}
      />
      <span className="rteSeparator" />
      <ToolbarButton
        editor={editor}
        label={uploading ? '上传中...' : '插入图片'}
        icon={uploading ? <span>..</span> : <span>+</span>}
        action={addImage}
      />
    </div>
  );
}

export function RichTextEditor({ value, onChange, placeholder, editable = true }: RichTextEditorProps) {
  const prevValueRef = useRef(value);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [3] },
      }),
      ImageExtension.configure({ inline: false, allowBase64: false }),
      Placeholder.configure({ placeholder: placeholder ?? '' }),
    ],
    content: value || '',
    editable,
    onUpdate: ({ editor: ed }) => {
      onChange(ed.getHTML());
    },
    editorProps: {
      handlePaste: (_view, event) => {
        const items = event.clipboardData?.items;
        if (!items) return false;

        for (let i = 0; i < items.length; i++) {
          const item = items[i];
          if (item.type.startsWith('image/')) {
            event.preventDefault();
            const file = item.getAsFile();
            if (!file) continue;

            const token = localStorage.getItem('hq_token');
            const formData = new FormData();
            formData.set('file', file);

            const headers: Record<string, string> = {};
            if (token) {
              headers['Authorization'] = 'Bearer ' + token;
            }

            fetch(API_BASE_URL + '/api/v1/uploads/images', {
              method: 'POST',
              headers,
              body: formData,
            })
              .then((r) => (r.ok ? r.json() : Promise.reject()))
              .then((data: { url: string }) => {
                editor?.chain().focus().setImage({ src: data.url }).run();
              })
              .catch(() => {});

            return true;
          }
        }
        return false;
      },
    },
  });

  // Sync external value changes into the editor (fixes empty content on async load)
  useEffect(() => {
    if (!editor) return;
    if (editor.isDestroyed) return;

    const currentHtml = editor.getHTML();
    const newValue = value || '';

    // Avoid overwriting user edits and avoid infinite loops
    if (newValue !== currentHtml && newValue !== prevValueRef.current) {
      editor.commands.setContent(newValue, { emitUpdate: false });
    }
    prevValueRef.current = newValue;
  }, [editor, value]);

  // Update editable state dynamically
  useEffect(() => {
    if (!editor || editor.isDestroyed) return;
    editor.setEditable(editable);
  }, [editor, editable]);

  return (
    <div className={'rteContainer' + (editable ? '' : ' rteReadonly')}>
      {editable && editor && <Toolbar editor={editor} />}
      <EditorContent editor={editor} className="rteContent" />
    </div>
  );
}
