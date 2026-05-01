import React, { useState, useEffect } from 'react';
import {
  Camera, StopCircle, Settings, Play, Database, Activity,
  AlertCircle, BarChart2, Loader, Zap, ChevronDown,
  X, MessageSquare, CheckCircle
} from 'lucide-react';
import './index.css';
import CycleDiagram from './components/CycleDiagram';
import BottleneckPanel from './components/BottleneckPanel';
import SettingsModal from './components/SettingsModal';

const BATCH_VOLUMES = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0];

function App() {
  const [isRecording, setIsRecording] = useState(false);
  const [statusMsg, setStatusMsg] = useState('System Ready');
  const [backendUrl] = useState('http://localhost:8000');
  const [cycleData, setCycleData] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [batchVolume, setBatchVolume] = useState(0.5);

  const [showSettings, setShowSettings] = useState(false);
  const [overrides, setOverrides] = useState({ timeline: {}, benchmark: {} });

  // Fault diagnosis modal state
  const [diagnosisModal, setDiagnosisModal] = useState(null);
  // diagnosisModal shape: { sessionId, stepName, question, context, resolved, resolution, loading }

  useEffect(() => {
    checkStatus();
    const interval = setInterval(checkStatus, 5000);
    return () => clearInterval(interval);
  }, []);

  const checkStatus = async () => {
    try {
      const res = await fetch(`${backendUrl}/api/status`);
      const data = await res.json();
      setIsRecording(data.is_recording);
      if (data.is_recording) setStatusMsg(`Recording to ${data.output_filename}`);
    } catch (err) {
      setStatusMsg('Cannot connect to Capture Engine');
    }
  };

  const startRecording = async () => {
    setStatusMsg('Initializing Capture...');
    setCycleData(null);
    try {
      const res = await fetch(`${backendUrl}/api/record/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_window: 'Full Screen', output_filename: 'batch_cycle_recording.mp4' })
      });
      const data = await res.json();
      if (res.ok) {
        setIsRecording(true);
        setStatusMsg('Recording Active (Full Screen)');
      } else {
        setStatusMsg(`Error: ${data.detail}`);
      }
    } catch (err) {
      setStatusMsg('Failed to contact Capture Engine.');
    }
  };

  const stopRecording = async () => {
    setStatusMsg('Stopping Capture...');
    try {
      const res = await fetch(`${backendUrl}/api/record/stop`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        setIsRecording(false);
        setStatusMsg(`Capture Saved: ${data.file} — Click "Analyze" to generate the cycle diagram.`);
      } else {
        setStatusMsg(`Error: ${data.detail}`);
      }
    } catch (err) {
      setStatusMsg('Failed to stop Capture Engine.');
    }
  };

  // ── Upgraded: calls /api/analyze/annotated ──────────────────────────────────
  const analyzeVideo = async (filename, customOverrides) => {
    const ovs = customOverrides || overrides;
    setIsAnalyzing(true);
    setStatusMsg(`Analyzing ${filename} @ ${batchVolume} m³...`);
    setCycleData(null);
    try {
      const payload = { 
        video_filename: filename, 
        batch_volume_m3: batchVolume 
      };
      if (Object.keys(ovs.timeline).length > 0) payload.timeline_overrides = ovs.timeline;
      if (Object.keys(ovs.benchmark).length > 0) payload.benchmark_overrides = ovs.benchmark;

      const res = await fetch(`${backendUrl}/api/analyze/annotated`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok) {
        setCycleData(data);
        const critical = (data.bottlenecks || []).filter(b => b.status === 'critical').length;
        setStatusMsg(`Analysis complete — ${data.events.length} events, ${critical} critical bottleneck(s) found.`);
      } else {
        setStatusMsg(`Error: ${data.detail}`);
      }
    } catch (err) {
      setStatusMsg('Failed to run analysis.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  // ── Fault Diagnosis ─────────────────────────────────────────────────────────
  const openDiagnosis = async (stepId, deltaSec) => {
    const stepName = cycleData?.events?.find(e => e.id === stepId)?.name || stepId;
    setDiagnosisModal({ stepName, loading: true, question: null, sessionId: null, resolved: false });
    try {
      const res = await fetch(`${backendUrl}/api/diagnose`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId, delta_sec: deltaSec })
      });
      const data = await res.json();
      setDiagnosisModal({
        stepName,
        loading: false,
        sessionId: data.session_id,
        question: data.question,
        context: data.context,
        resolved: false,
        resolution: null,
      });
    } catch (err) {
      setDiagnosisModal(prev => ({ ...prev, loading: false, question: 'Failed to start diagnosis. Is the backend running?' }));
    }
  };

  const respondToDiagnosis = async (answer) => {
    if (!diagnosisModal?.sessionId) return;
    setDiagnosisModal(prev => ({ ...prev, loading: true }));
    try {
      const res = await fetch(`${backendUrl}/api/diagnose/respond`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: diagnosisModal.sessionId, answer })
      });
      const data = await res.json();
      if (data.resolution) {
        setDiagnosisModal(prev => ({ ...prev, loading: false, resolved: true, resolution: data.resolution, question: null }));
      } else {
        setDiagnosisModal(prev => ({ ...prev, loading: false, question: data.question, context: data.context }));
      }
    } catch (err) {
      setDiagnosisModal(prev => ({ ...prev, loading: false, question: 'Response failed. Please try again.' }));
    }
  };

  const handleSettingsSave = (newOverrides) => {
    setOverrides(newOverrides);
    setShowSettings(false);
    const videoToAnalyze = cycleData?.batch_id || 'batch_cycle_recording.mp4';
    analyzeVideo(videoToAnalyze, newOverrides);
  };

  const tp = cycleData?.throughput;

  return (
    <div className="app-container" style={{ padding: '2rem', maxWidth: '1400px', margin: '0 auto' }}>

      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }} className="animate-fade-in">
        <div>
          <h1 style={{ fontSize: '2.2rem', margin: 0, display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Activity color="var(--accent-blue)" size={34} />
            Batch Optimization <span style={{ color: 'var(--text-secondary)' }}>Module</span>
          </h1>
          <p style={{ color: 'var(--text-secondary)', marginTop: '6px' }}>Real-time batch cycle analytics and computer vision pipeline</p>
        </div>
        <div className={`status-badge ${isRecording ? 'recording' : 'idle'}`}>
          {isRecording ? 'Live Capture' : 'Engine Idle'}
        </div>
      </header>

      {/* ── Control Row ── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '2rem', marginBottom: '2rem' }}>

        <section className="glass-panel animate-fade-in" style={{ padding: '2rem', display: 'flex', flexDirection: 'column', animationDelay: '0.1s' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h2 style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '1.4rem', margin: 0 }}>
              <Camera color="var(--accent-green)" />
              Capture Engine
            </h2>
            <button className="modern-button outline" style={{ padding: '6px 12px', fontSize: '0.85rem' }} onClick={() => setShowSettings(true)}>
              <Settings size={14} /> Timing Settings
            </button>
          </div>

          <div style={{ background: 'rgba(0,0,0,0.3)', borderRadius: '12px', padding: '2rem', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', minHeight: '160px', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '1.5rem' }}>
            {isRecording ? (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
                <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: 'rgba(239,68,68,0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid rgba(239,68,68,0.3)' }}>
                  <div style={{ width: '18px', height: '18px', borderRadius: '4px', background: 'var(--accent-red)', animation: 'pulse 1.5s infinite' }} />
                </div>
                <p style={{ fontSize: '1.1rem', color: '#fca5a5' }}>Recording Full Screen...</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.6rem', color: 'var(--text-secondary)' }}>
                <Database size={42} opacity={0.5} />
                <p>Ready to capture batch sequence data.</p>
                <p style={{ fontSize: '0.85rem', opacity: 0.7, textAlign: 'center', maxWidth: '360px' }}>
                  Start the sequence recording or analyze the BCA video directly.
                </p>
              </div>
            )}
          </div>

          {/* Batch Volume Selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '0.75rem', padding: '10px 14px', background: 'rgba(255,255,255,0.04)', borderRadius: '10px', border: '1px solid rgba(255,255,255,0.08)' }}>
            <Zap size={15} color="#facc15" />
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>Batch Volume:</span>
            <div style={{ position: 'relative', flex: 1 }}>
              <select
                value={batchVolume}
                onChange={e => setBatchVolume(parseFloat(e.target.value))}
                style={{
                  width: '100%', appearance: 'none', background: 'rgba(0,0,0,0.35)',
                  border: '1px solid rgba(250,204,21,0.3)', borderRadius: '7px',
                  color: '#facc15', fontWeight: 700, fontSize: '0.9rem',
                  padding: '6px 32px 6px 10px', cursor: 'pointer',
                }}
              >
                {BATCH_VOLUMES.map(v => (
                  <option key={v} value={v} style={{ background: '#1a1a2e', color: '#facc15' }}>
                    {v} m³
                  </option>
                ))}
              </select>
              <ChevronDown size={13} color="#facc15" style={{ position: 'absolute', right: 9, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              {!isRecording ? (
                <button className="modern-button" onClick={startRecording} style={{ flex: 1 }}>
                  <Play size={18} /> Start Sequence Recording
                </button>
              ) : (
                <button className="modern-button danger" onClick={stopRecording} style={{ flex: 1 }}>
                  <StopCircle size={18} /> End Cycle &amp; Process Data
                </button>
              )}
            </div>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                className="modern-button"
                style={{ flex: 1, background: 'rgba(96,165,250,0.15)', borderColor: 'rgba(96,165,250,0.3)' }}
                onClick={() => analyzeVideo('batch_cycle_recording.mp4')}
                disabled={isAnalyzing}
              >
                {isAnalyzing ? <Loader size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <BarChart2 size={18} />}
                Analyze Last Recording
              </button>

              <button
                className="modern-button"
                style={{ flex: 1, background: 'rgba(74,222,128,0.12)', borderColor: 'rgba(74,222,128,0.3)' }}
                onClick={() => analyzeVideo('BCA Video.MP4')}
                disabled={isAnalyzing}
              >
                {isAnalyzing ? <Loader size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <BarChart2 size={18} />}
                Analyze BCA Video
              </button>
            </div>

            <button
              className="modern-button outline"
              onClick={async () => {
                setStatusMsg('Launching AnyDesk...');
                try {
                  const res = await fetch(`${backendUrl}/api/launch/anydesk`, { method: 'POST' });
                  const data = await res.json();
                  setStatusMsg(res.ok ? 'AnyDesk Launched' : `Error: ${data.detail}`);
                } catch (err) {
                  setStatusMsg('Failed to launch AnyDesk.');
                }
              }}
              style={{ backgroundColor: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.1)' }}
            >
              <Activity size={18} /> Launch AnyDesk App
            </button>
          </div>
        </section>

        {/* Status Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <aside className="glass-panel animate-fade-in" style={{ padding: '1.5rem', animationDelay: '0.2s' }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
              <Settings size={16} /> System Status
            </h3>
            <div style={{ background: 'rgba(0,0,0,0.3)', padding: '1rem', borderRadius: '8px', borderLeft: '3px solid var(--accent-blue)', fontFamily: 'monospace', fontSize: '0.85rem', color: '#60a5fa', wordBreak: 'break-word' }}>
              &gt; {statusMsg}
            </div>
            <div style={{ marginTop: '1.2rem', display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
              {[
                ['Batch Volume', `${batchVolume} m³`],
                ['Capture Mode', 'Full Screen'],
                ['Analysis Mode', cycleData ? (cycleData.analysis_mode === 'demo' ? '⚡ Demo' : '✅ Live CV') : '—'],
                ['Events Detected', cycleData ? `${cycleData.events.length}` : '—'],
                ['Critical Bottlenecks', cycleData ? `${(cycleData.bottlenecks || []).filter(b => b.status === 'critical').length}` : '—'],
              ].map(([label, val]) => (
                <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
                  <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
                  <span>{val}</span>
                </div>
              ))}
            </div>
          </aside>

          <aside className="glass-panel animate-fade-in" style={{ padding: '1.5rem', animationDelay: '0.3s' }}>
            <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '1rem', color: 'var(--text-secondary)' }}>
              <AlertCircle size={16} /> Instructions
            </h3>
            <ol style={{ paddingLeft: '1.1rem', color: 'var(--text-secondary)', fontSize: '0.85rem', display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              <li>Select a <strong>Batch Volume</strong> from the dropdown.</li>
              <li>Click <strong>Analyze BCA Video</strong> to visualize the provided recording.</li>
              <li>Review the Cycle Diagram and Bottleneck Panel below.</li>
              <li>Click <strong>Diagnose</strong> on any bottleneck to start fault analysis.</li>
            </ol>
          </aside>
        </div>
      </div>

      {/* ── Throughput KPI Strip ── */}
      {tp && (
        <section className="animate-fade-in" style={{ marginBottom: '1.5rem', animationDelay: '0.1s' }}>
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem',
          }}>
            {[
              { label: 'Current Output', value: `${tp.current_m3_hr} m³/hr`, color: '#60a5fa', icon: '📊' },
              { label: 'Ideal Output', value: `${tp.ideal_m3_hr} m³/hr`, color: '#4ade80', icon: '🎯' },
              { label: 'Efficiency', value: `${tp.efficiency_pct}%`, color: tp.efficiency_pct >= 85 ? '#4ade80' : tp.efficiency_pct >= 65 ? '#facc15' : '#ef4444', icon: '⚡' },
              { label: 'Projected (fix top 3)', value: `${tp.projected_m3_hr} m³/hr`, color: '#a78bfa', icon: '🚀' },
            ].map(({ label, value, color, icon }) => (
              <div key={label} style={{
                background: 'rgba(255,255,255,0.03)',
                border: `1px solid ${color}33`,
                borderRadius: '12px', padding: '1rem 1.2rem',
                display: 'flex', flexDirection: 'column', gap: '4px',
              }}>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>{icon} {label}</span>
                <span style={{ fontSize: '1.4rem', fontWeight: 800, color }}>{value}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Bottleneck Panel ── */}
      {cycleData?.bottlenecks && (
        <section className="animate-fade-in" style={{ marginBottom: '1.5rem', animationDelay: '0.15s' }}>
          <BottleneckPanel
            bottlenecks={cycleData.bottlenecks}
            onDiagnose={openDiagnosis}
          />
        </section>
      )}

      {/* ── Cycle Diagram ── */}
      {cycleData && (
        <section className="animate-fade-in" style={{ animationDelay: '0.2s' }}>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '1rem', fontSize: '1.4rem' }}>
            <BarChart2 color="var(--accent-blue)" />
            Cycle Diagram
            <span style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', fontWeight: 400 }}>
              — {cycleData.batch_id}
            </span>
          </h2>
          <CycleDiagram data={cycleData} onStepClick={openDiagnosis} />
        </section>
      )}

      {/* ── Fault Diagnosis Modal ── */}
      {diagnosisModal && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000, backdropFilter: 'blur(4px)',
          animation: 'fadeIn 0.2s ease',
        }}>
          <div style={{
            background: '#1a1a2e', border: '1px solid rgba(250,204,21,0.25)',
            borderRadius: '20px', padding: '2rem', maxWidth: '520px', width: '90%',
            boxShadow: '0 25px 60px rgba(0,0,0,0.6)',
            animation: 'slideUp 0.25s ease',
          }}>
            {/* Modal Header */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <MessageSquare size={20} color="#facc15" />
                <div>
                  <div style={{ fontWeight: 700, fontSize: '1rem', color: '#e2e8f0' }}>Fault Diagnosis</div>
                  <div style={{ fontSize: '0.78rem', color: '#facc15' }}>{diagnosisModal.stepName}</div>
                </div>
              </div>
              <button
                onClick={() => setDiagnosisModal(null)}
                style={{ background: 'rgba(255,255,255,0.06)', border: 'none', borderRadius: '8px', padding: '6px', cursor: 'pointer', color: '#94a3b8', display: 'flex' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            {diagnosisModal.loading ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#94a3b8' }}>
                <Loader size={28} style={{ animation: 'spin 1s linear infinite', marginBottom: '1rem', color: '#facc15' }} />
                <p>Analyzing fault tree...</p>
              </div>
            ) : diagnosisModal.resolved ? (
              <div>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                  <CheckCircle size={22} color="#4ade80" style={{ flexShrink: 0, marginTop: '2px' }} />
                  <div>
                    <div style={{ fontWeight: 600, color: '#4ade80', marginBottom: '6px' }}>Resolution Found</div>
                    <div style={{ color: '#e2e8f0', fontSize: '0.9rem', lineHeight: 1.6 }}>{diagnosisModal.resolution}</div>
                  </div>
                </div>
                <button
                  className="modern-button"
                  style={{ width: '100%', background: 'rgba(74,222,128,0.15)', borderColor: 'rgba(74,222,128,0.4)' }}
                  onClick={() => setDiagnosisModal(null)}
                >
                  Close
                </button>
              </div>
            ) : (
              <div>
                {diagnosisModal.context && (
                  <div style={{ background: 'rgba(250,204,21,0.06)', border: '1px solid rgba(250,204,21,0.15)', borderRadius: '8px', padding: '10px 13px', marginBottom: '1rem', fontSize: '0.8rem', color: '#94a3b8' }}>
                    {diagnosisModal.context}
                  </div>
                )}
                <div style={{ fontSize: '1rem', color: '#e2e8f0', lineHeight: 1.65, marginBottom: '1.8rem' }}>
                  {diagnosisModal.question}
                </div>
                <div style={{ display: 'flex', gap: '0.75rem' }}>
                  <button
                    className="modern-button"
                    style={{ flex: 1, background: 'rgba(74,222,128,0.15)', borderColor: 'rgba(74,222,128,0.4)', color: '#4ade80' }}
                    onClick={() => respondToDiagnosis('yes')}
                  >
                    ✓ Yes
                  </button>
                  <button
                    className="modern-button"
                    style={{ flex: 1, background: 'rgba(239,68,68,0.12)', borderColor: 'rgba(239,68,68,0.3)', color: '#ef4444' }}
                    onClick={() => respondToDiagnosis('no')}
                  >
                    ✗ No
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Settings Modal ── */}
      {showSettings && (
        <SettingsModal
          backendUrl={backendUrl}
          onClose={() => setShowSettings(false)}
          onSave={handleSettingsSave}
        />
      )}

    </div>
  );
}

export default App;
