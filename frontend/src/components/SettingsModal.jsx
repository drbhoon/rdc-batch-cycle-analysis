import React, { useState, useEffect } from 'react';
import { X, Save, RefreshCw, Loader, Settings } from 'lucide-react';

export default function SettingsModal({ onClose, onSave, backendUrl }) {
  const [steps, setSteps] = useState([]);
  const [overrides, setOverrides] = useState({ timeline: {}, benchmark: {} });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${backendUrl}/api/settings`)
      .then(res => res.json())
      .then(data => {
        setSteps(data.steps || []);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setLoading(false);
      });
  }, [backendUrl]);

  const handleOverrideChange = (type, id, val) => {
    setOverrides(prev => ({
      ...prev,
      [type]: {
        ...prev[type],
        [id]: parseFloat(val) || 0
      }
    }));
  };

  const resetDefaults = () => {
    setOverrides({ timeline: {}, benchmark: {} });
  };

  const handleSave = () => {
    onSave(overrides);
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
      display: 'flex', alignItems: 'center', justifyItems: 'center', justifyContent: 'center',
      zIndex: 1000, backdropFilter: 'blur(4px)',
      animation: 'fadeIn 0.2s ease',
    }}>
      <div style={{
        background: '#1a1a2e', border: '1px solid rgba(250,204,21,0.25)',
        borderRadius: '20px', padding: '2rem', width: '90%', maxWidth: '800px',
        maxHeight: '90vh', display: 'flex', flexDirection: 'column',
        boxShadow: '0 25px 60px rgba(0,0,0,0.6)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <h2 style={{ fontSize: '1.4rem', margin: 0, color: '#e2e8f0', display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Settings color="var(--accent-blue)" /> Timing Configuration
          </h2>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}><X size={24} /></button>
        </div>

        {loading ? (
          <div style={{ textAlign: 'center', padding: '3rem' }}><Loader size={32} className="lucide-spin" color="#60a5fa" style={{ animation: 'spin 1s linear infinite' }} /></div>
        ) : (
          <div style={{ flex: 1, overflowY: 'auto', marginBottom: '1.5rem', paddingRight: '10px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', color: '#e2e8f0' }}>
              <thead>
                <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                  <th style={{ padding: '10px 8px', fontWeight: 600 }}>Step</th>
                  <th style={{ padding: '10px 8px', fontWeight: 600 }}>Simulated Actual (s)</th>
                  <th style={{ padding: '10px 8px', fontWeight: 600 }}>Target Benchmark (s)</th>
                </tr>
              </thead>
              <tbody>
                {steps.map(s => {
                  const currentSim = overrides.timeline[s.id] !== undefined ? overrides.timeline[s.id] : s.default_simulated;
                  const currentBench = overrides.benchmark[s.id] !== undefined ? overrides.benchmark[s.id] : s.default_benchmark;
                  
                  return (
                    <tr key={s.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '12px 8px' }}>{s.name}</td>
                      <td style={{ padding: '12px 8px' }}>
                        <input
                          type="number"
                          value={currentSim}
                          onChange={(e) => handleOverrideChange('timeline', s.id, e.target.value)}
                          style={{
                            background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: '6px', color: '#e2e8f0', padding: '6px 10px', width: '80px',
                            fontFamily: 'inherit'
                          }}
                          min="0"
                        />
                      </td>
                      <td style={{ padding: '12px 8px' }}>
                        <input
                          type="number"
                          value={currentBench}
                          onChange={(e) => handleOverrideChange('benchmark', s.id, e.target.value)}
                          style={{
                            background: 'rgba(0,0,0,0.3)', border: '1px solid rgba(255,255,255,0.1)',
                            borderRadius: '6px', color: '#e2e8f0', padding: '6px 10px', width: '80px',
                            fontFamily: 'inherit'
                          }}
                          min="0"
                        />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
          <button className="modern-button outline" onClick={resetDefaults} style={{ borderColor: 'rgba(255,255,255,0.2)' }}>
            <RefreshCw size={18} /> Reset to Defaults
          </button>
          <button className="modern-button" onClick={handleSave} style={{ background: 'var(--accent-blue)', color: '#fff', border: 'none' }}>
            <Save size={18} /> Save & Re-analyze
          </button>
        </div>
      </div>
    </div>
  );
}
