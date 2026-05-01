import React from 'react';
import { AlertTriangle, Wrench, TrendingDown } from 'lucide-react';

/**
 * BottleneckPanel
 * Shows ranked list of top bottlenecks with impact and a Diagnose button.
 *
 * Props:
 *   bottlenecks  – array from /api/analyze/annotated .bottlenecks
 *   onDiagnose   – callback(step_id, delta_sec)
 */
export default function BottleneckPanel({ bottlenecks, onDiagnose }) {
  if (!bottlenecks || bottlenecks.length === 0) {
    return (
      <div style={containerStyle}>
        <h3 style={headerStyle}><TrendingDown size={18} color="#4ade80" /> Bottleneck Analysis</h3>
        <div style={{ color: '#4ade80', textAlign: 'center', padding: '2rem', fontSize: '0.9rem' }}>
          ✅ No significant bottlenecks detected. All steps are within target.
        </div>
      </div>
    );
  }

  const top = bottlenecks.slice(0, 6);
  const maxDelta = Math.max(...top.map(b => b.delta_sec));

  const statusColor = { slow: '#facc15', critical: '#ef4444' };

  return (
    <div style={containerStyle}>
      <h3 style={headerStyle}>
        <AlertTriangle size={18} color="#facc15" />
        Top Bottlenecks
        <span style={{ fontSize: '0.75rem', color: '#64748b', fontWeight: 400, marginLeft: '8px' }}>
          (click Diagnose to start fault analysis)
        </span>
      </h3>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {top.map((b, rank) => {
          const barPct = maxDelta > 0 ? (b.delta_sec / maxDelta) * 100 : 0;
          const col = statusColor[b.status] || '#facc15';
          return (
            <div key={b.id} style={{
              background: 'rgba(255,255,255,0.03)',
              border: `1px solid ${col}33`,
              borderRadius: '10px',
              padding: '12px 14px',
              display: 'grid',
              gridTemplateColumns: '24px 1fr auto',
              gap: '10px',
              alignItems: 'center',
            }}>
              {/* Rank badge */}
              <div style={{
                width: 24, height: 24, borderRadius: '50%',
                background: rank === 0 ? '#ef4444' : rank === 1 ? '#f97316' : '#facc15',
                color: '#111', fontWeight: 800, fontSize: '0.7rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {rank + 1}
              </div>

              {/* Info */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.88rem', color: '#e2e8f0' }}>{b.name}</span>
                  {b.on_critical_path && (
                    <span style={{ fontSize: '0.65rem', background: '#7c3aed22', color: '#a78bfa', border: '1px solid #a78bfa44', borderRadius: '4px', padding: '1px 5px' }}>
                      Critical Path
                    </span>
                  )}
                  <span style={{ fontSize: '0.65rem', color: '#64748b' }}>{b.component}</span>
                </div>
                {/* Impact bar */}
                <div style={{ background: 'rgba(255,255,255,0.07)', borderRadius: '4px', height: '6px', overflow: 'hidden' }}>
                  <div style={{ width: `${barPct}%`, height: '100%', background: col, borderRadius: '4px', transition: 'width 0.6s ease' }} />
                </div>
                <div style={{ marginTop: '4px', fontSize: '0.75rem', color: '#94a3b8', display: 'flex', gap: '1rem' }}>
                  <span>Actual: <strong style={{ color: col }}>{b.actual_sec}s</strong></span>
                  <span>Target: <strong style={{ color: '#94a3b8' }}>{b.target_sec}s</strong></span>
                  <span>Lost: <strong style={{ color: col }}>+{b.delta_sec}s</strong></span>
                </div>
              </div>

              {/* Diagnose button */}
              <button
                onClick={() => onDiagnose && onDiagnose(b.id, b.delta_sec)}
                style={{
                  background: `${col}22`, border: `1px solid ${col}55`,
                  color: col, borderRadius: '7px', padding: '6px 12px',
                  fontSize: '0.78rem', fontWeight: 600, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: '5px',
                  whiteSpace: 'nowrap', transition: 'background 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = `${col}44`}
                onMouseLeave={e => e.currentTarget.style.background = `${col}22`}
              >
                <Wrench size={13} /> Diagnose
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}

const containerStyle = {
  background: 'rgba(255,255,255,0.03)',
  border: '1px solid rgba(255,255,255,0.08)',
  borderRadius: '16px',
  padding: '1.5rem',
};

const headerStyle = {
  display: 'flex', alignItems: 'center', gap: '8px',
  fontSize: '1.1rem', fontWeight: 700, color: '#e2e8f0',
  marginBottom: '1.2rem', margin: '0 0 1.2rem 0',
};
