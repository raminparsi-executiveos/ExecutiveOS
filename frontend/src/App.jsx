import { useEffect, useState } from 'react';

const sections = [
  { key: 'capture', label: 'Capture' },
  { key: 'briefing', label: 'Morning Briefing' },
  { key: 'prep', label: 'Meeting Prep' },
  { key: 'search', label: 'Search / Ask' },
];

function App() {
  const [active, setActive] = useState('capture');
  const [briefing, setBriefing] = useState(null);

  useEffect(() => {
    fetch('http://127.0.0.1:8000/briefing')
      .then((res) => res.json())
      .then(setBriefing)
      .catch(() => setBriefing({ error: 'Backend unavailable' }));
  }, []);

  return (
    <div style={{ fontFamily: 'Inter, sans-serif', padding: 24, maxWidth: 960, margin: '0 auto' }}>
      <h1>ExecutiveOS</h1>
      <p>AI-first executive memory and decision platform.</p>
      <div style={{ display: 'flex', gap: 12, marginBottom: 24 }}>
        {sections.map((section) => (
          <button
            key={section.key}
            onClick={() => setActive(section.key)}
            style={{ padding: '8px 12px', borderRadius: 8, border: active === section.key ? '2px solid #0f172a' : '1px solid #cbd5e1' }}
          >
            {section.label}
          </button>
        ))}
      </div>

      {active === 'capture' && (
        <section>
          <h2>Capture</h2>
          <textarea rows={6} style={{ width: '100%', padding: 12 }} defaultValue="Julio is now responsible for PM quality and high-priority clients. His pay is increasing from $14.42/hr to $17.50/hr." />
          <button style={{ marginTop: 12, padding: '10px 14px' }}>Approve suggested updates</button>
        </section>
      )}

      {active === 'briefing' && (
        <section>
          <h2>Morning Briefing</h2>
          {briefing ? (
            <pre style={{ whiteSpace: 'pre-wrap', background: '#f8fafc', padding: 16, borderRadius: 12 }}>
              {JSON.stringify(briefing, null, 2)}
            </pre>
          ) : (
            <p>Loading briefing…</p>
          )}
        </section>
      )}

      {active === 'prep' && (
        <section>
          <h2>Meeting Prep</h2>
          <p>Prepare RYSE leadership meeting with agenda generated from memory.</p>
        </section>
      )}

      {active === 'search' && (
        <section>
          <h2>Search / Ask</h2>
          <input style={{ width: '100%', padding: 12 }} placeholder="Why did we promote Julio?" />
        </section>
      )}
    </div>
  );
}

export default App;
