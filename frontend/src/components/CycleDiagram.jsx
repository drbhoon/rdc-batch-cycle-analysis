import React, { useMemo } from 'react';

/**
 * CycleDiagram — Enhanced with status color-coding, target times, delta column,
 * and clickable bars for fault diagnosis.
 *
 * Props:
 *   data        – response from /api/analyze/annotated
 *   onStepClick – callback(step_id, delta_sec) when user clicks a slow/critical bar
 */
export default function CycleDiagram({ data, onStepClick }) {
  if (!data || !data.events || data.events.length === 0) return null;

  const { events, total_cycle_time_sec, analysis_mode, batch_id } = data;

  const totalSec = total_cycle_time_sec || Math.max(...events.map(e => e.end_sec));
  const tickStep = totalSec <= 100 ? 10 : totalSec <= 250 ? 25 : 50;
  const ticks = useMemo(() => {
    const arr = [];
    for (let t = 0; t <= totalSec + tickStep; t += tickStep) arr.push(t);
    return arr;
  }, [totalSec, tickStep]);

  const secToPercent = (s) => `${((s / totalSec) * 100).toFixed(3)}%`;

  // Color map by status — overrides the default event color
  const statusColor = {
    ok:       '#4ade80',   // green
    slow:     '#facc15',   // amber
    critical: '#ef4444',   // red
  };

  const getBarColor = (ev) => {
    if (ev.status) return statusColor[ev.status] || ev.color;
    return ev.color;
  };

  const handleBarClick = (ev) => {
    if (ev.status && ev.status !== 'ok' && onStepClick) {
      onStepClick(ev.id, ev.delta_sec ?? 0);
    }
  };

  return (
    <div style={{
      background: '#1a1a2e',
      border: '1px solid rgba(255,255,255,0.08)',
      borderRadius: '16px',
      overflow: 'hidden',
      fontFamily: "'Inter', sans-serif",
    }}>
      {/* Title Bar */}
      <div style={{
        background: '#facc15', color: '#111', textAlign: 'center',
        fontWeight: 800, fontSize: '1rem', padding: '10px',
        letterSpacing: '0.08em', textTransform: 'uppercase',
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '12px',
      }}>
        Cycle Diagram — Skip to Mixer
        {analysis_mode === 'demo' && (
          <span style={{ fontSize: '0.75rem', fontWeight: 400, color: '#555' }}>
            (Demo Mode — ROIs not yet calibrated)
          </span>
        )}
      </div>

      {/* Legend */}
      <div style={{ background: '#16213e', padding: '8px 16px', display: 'flex', gap: '1.5rem', fontSize: '0.75rem', color: '#94a3b8', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        {[['ok','#4ade80','On Target'],['slow','#facc15','Slow (click to diagnose)'],['critical','#ef4444','Critical (click to diagnose)']].map(([key, col, label]) => (
          <span key={key} style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
            <span style={{ width: 12, height: 12, borderRadius: 3, background: col, display: 'inline-block' }} />
            {label}
          </span>
        ))}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '310px 1fr' }}>
        {/* LEFT TABLE */}
        <div style={{ borderRight: '1px solid rgba(255,255,255,0.1)' }}>
          {/* Header */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 68px 68px 68px', background: '#2d2d44', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
            <div style={thStyle}>Sequence of Work</div>
            <div style={{ ...thStyle, background: '#facc15', color: '#111' }}>Actual (s)</div>
            <div style={{ ...thStyle, background: '#f9a825', color: '#111' }}>Target (s)</div>
            <div style={{ ...thStyle, background: '#1e293b', color: '#94a3b8' }}>Δ (s)</div>
          </div>
          {/* Rows */}
          {events.map((ev, i) => {
            const delta = ev.delta_sec ?? null;
            const deltaColor = delta === null ? '#94a3b8' : delta > 0 ? '#ef4444' : '#4ade80';
            const isClickable = ev.status && ev.status !== 'ok';
            return (
              <div
                key={ev.id}
                onClick={() => handleBarClick(ev)}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 68px 68px 68px',
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent',
                  height: ROW_HEIGHT,
                  cursor: isClickable ? 'pointer' : 'default',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { if (isClickable) e.currentTarget.style.background = 'rgba(239,68,68,0.08)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = i % 2 === 0 ? 'rgba(255,255,255,0.02)' : 'transparent'; }}
              >
                <div style={{ ...cellStyle, gap: '6px' }}>
                  {ev.status && ev.status !== 'ok' && (
                    <span style={{ fontSize: '0.6rem', color: statusColor[ev.status] }}>●</span>
                  )}
                  {ev.name}
                </div>
                <div style={{ ...cellStyle, textAlign: 'center', color: getBarColor(ev), fontWeight: 600 }}>
                  {ev.duration_sec}
                </div>
                <div style={{ ...cellStyle, textAlign: 'center', color: '#94a3b8' }}>
                  {ev.target_sec ?? '—'}
                </div>
                <div style={{ ...cellStyle, textAlign: 'center', color: deltaColor, fontWeight: 600 }}>
                  {delta !== null ? (delta > 0 ? `+${delta}` : delta) : '—'}
                </div>
              </div>
            );
          })}
        </div>

        {/* RIGHT GANTT CHART */}
        <div>
          {/* X-Axis Ticks */}
          <div style={{ position: 'relative', height: '32px', borderBottom: '1px solid rgba(255,255,255,0.1)', background: '#16213e' }}>
            {ticks.map(t => (
              <span key={t} style={{ position: 'absolute', left: secToPercent(t), transform: 'translateX(-50%)', fontSize: '0.72rem', color: '#94a3b8', top: '8px', userSelect: 'none' }}>
                {t}
              </span>
            ))}
            {ticks.map(t => (
              <div key={`grid-${t}`} style={{ position: 'absolute', left: secToPercent(t), top: 0, bottom: 0, borderLeft: '1px solid rgba(255,255,255,0.05)' }} />
            ))}
          </div>

          {/* Bars */}
          {events.map((ev, i) => {
            const barColor = getBarColor(ev);
            const isClickable = ev.status && ev.status !== 'ok';
            return (
              <div
                key={ev.id}
                onClick={() => handleBarClick(ev)}
                style={{
                  position: 'relative',
                  height: ROW_HEIGHT,
                  borderBottom: '1px solid rgba(255,255,255,0.04)',
                  background: i % 2 === 0 ? 'rgba(255,255,255,0.015)' : 'transparent',
                  cursor: isClickable ? 'pointer' : 'default',
                }}
              >
                {ticks.map(t => (
                  <div key={t} style={{ position: 'absolute', left: secToPercent(t), top: 0, bottom: 0, borderLeft: '1px solid rgba(255,255,255,0.04)' }} />
                ))}
                {/* Target ghost bar */}
                {ev.target_sec != null && (
                  <div style={{
                    position: 'absolute',
                    left: secToPercent(ev.start_sec),
                    width: secToPercent(ev.target_sec),
                    top: '15%',
                    height: '70%',
                    background: 'rgba(255,255,255,0.07)',
                    borderRadius: '3px',
                    border: '1px dashed rgba(255,255,255,0.15)',
                  }} />
                )}
                {/* Actual bar */}
                <div
                  title={`${ev.name}: actual ${ev.duration_sec}s / target ${ev.target_sec ?? '—'}s${ev.delta_sec != null ? ` (Δ ${ev.delta_sec > 0 ? '+' : ''}${ev.delta_sec}s)` : ''}${isClickable ? ' — Click to diagnose' : ''}`}
                  style={{
                    position: 'absolute',
                    left: secToPercent(ev.start_sec),
                    width: secToPercent(ev.duration_sec),
                    top: '20%',
                    height: '60%',
                    background: barColor,
                    borderRadius: '3px',
                    opacity: 0.88,
                    transition: 'opacity 0.2s, box-shadow 0.2s',
                    boxShadow: `0 0 ${isClickable ? 10 : 6}px ${barColor}66`,
                  }}
                  onMouseEnter={e => { e.currentTarget.style.opacity = '1'; }}
                  onMouseLeave={e => { e.currentTarget.style.opacity = '0.88'; }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer */}
      <div style={{ padding: '12px 20px', borderTop: '1px solid rgba(255,255,255,0.08)', display: 'flex', gap: '2rem', fontSize: '0.85rem', color: '#94a3b8', background: '#16213e', flexWrap: 'wrap' }}>
        <span>📹 <strong style={{ color: '#e2e8f0' }}>{batch_id}</strong></span>
        <span>⏱ Total: <strong style={{ color: '#facc15' }}>{totalSec.toFixed(1)}s</strong></span>
        <span>📊 Steps: <strong style={{ color: '#4ade80' }}>{events.length}</strong></span>
        <span>🔴 Critical: <strong style={{ color: '#ef4444' }}>{events.filter(e => e.status === 'critical').length}</strong></span>
        <span>🟡 Slow: <strong style={{ color: '#facc15' }}>{events.filter(e => e.status === 'slow').length}</strong></span>
        <span style={{ marginLeft: 'auto', fontSize: '0.78rem', opacity: 0.6 }}>
          {analysis_mode === 'demo' ? '⚡ Demo Mode' : '✅ Live CV Analysis'}
        </span>
      </div>
    </div>
  );
}

const ROW_HEIGHT = '34px';
const thStyle = {
  padding: '6px 8px', fontSize: '0.7rem', fontWeight: 700, color: '#e2e8f0',
  borderRight: '1px solid rgba(0,0,0,0.1)', display: 'flex', alignItems: 'center',
  justifyContent: 'center', textAlign: 'center', lineHeight: 1.2,
};
const cellStyle = {
  padding: '0 8px', fontSize: '0.78rem', color: '#e2e8f0', display: 'flex',
  alignItems: 'center', borderRight: '1px solid rgba(255,255,255,0.05)',
  overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
};
