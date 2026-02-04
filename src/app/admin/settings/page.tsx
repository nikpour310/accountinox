'use client';
import { useEffect, useState } from 'react';

export default function SettingsPage() {
  const [settings, setSettings] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch('/api/admin/settings').then((r) => r.json()).then(setSettings);
  }, []);

  async function toggleTailwind() {
    const newMode = settings?.tailwindMode === 'cdn' ? 'local' : 'cdn';
    setLoading(true);
    await fetch('/api/admin/settings', { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ tailwindMode: newMode }) });
    setSettings({ ...settings, tailwindMode: newMode });
    setLoading(false);
    // reload to apply new mode
    window.location.reload();
  }

  if (!settings) return <div>بارگذاری...</div>;
  return (
    <div>
      <h2 className="text-2xl font-bold mb-4">تنظیمات سایت</h2>
      <div className="p-4 border rounded">
        <div className="flex items-center justify-between">
          <div>Tailwind Mode</div>
          <div>
            <button onClick={toggleTailwind} className="px-4 py-2 rounded bg-primary text-white" disabled={loading}>
              {settings.tailwindMode === 'cdn' ? 'Switch to Local' : 'Switch to CDN'}
            </button>
            <div className="text-sm text-gray-500 mt-2">حالت فعلی: {settings.tailwindMode}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
