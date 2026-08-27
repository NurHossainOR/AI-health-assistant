'use client'

import Link from 'next/link'
import { useState } from 'react'

function SpondonLogo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <path
        d="M2 12h5l2-7 4 14 3-10 2 3h4"
        stroke="#0E6F64"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function ArrowIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <path
        d="M5 12h14M13 6l6 6-6 6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export default function HomePage() {
  const [activeTab, setActiveTab] = useState('patient')

  return (
    <>
      <nav>
        <div className="nav-inner">
          <Link href="/" className="logo">
            <SpondonLogo />
            Spondon
          </Link>
          <div className="nav-links">
            <a href="#journey">How it works</a>
            <a href="#showcase">Product</a>
            <a href="#trust">Security</a>
            <Link href="/dashboard">Dashboard</Link>
          </div>
          <div className="nav-cta">
            <Link href="/login" className="btn btn-ghost">Sign in</Link>
            <Link href="/signup" className="btn btn-primary">Get started</Link>
          </div>
        </div>
      </nav>

      <header className="hero">
        <div className="wrap hero-grid">
          <div>
            <div className="eyebrow">Personal health intelligence</div>
            <h1>Every result,<br /><em>understood.</em></h1>
            <p className="sub">
              Upload any blood test, scan, or discharge summary. Spondon reads it, 
              tracks it against your history, and explains exactly what changed — 
              in your language, or your doctor&apos;s.
            </p>
            <div className="hero-ctas">
              <Link href="/signup" className="btn btn-primary">Upload your first report</Link>
              <a href="#journey" className="link-arrow">
                See how it works
                <ArrowIcon />
              </a>
            </div>
            <div className="trust-row">
              <span><span className="trust-dot" />Encrypted end to end</span>
              <span><span className="trust-dot" />Role-based access</span>
              <span><span className="trust-dot" />You control every share</span>
            </div>
          </div>

          <div className="hero-visual">
            <svg className="pulse-svg" viewBox="0 0 480 460" preserveAspectRatio="none">
              <path className="pulse-path" d="M0 360 L70 360 L95 300 L120 400 L145 260 L170 360 L480 360" />
            </svg>
            <div className="float-card card-report">
              <div className="report-head">
                <span className="report-title">Lipid Panel — Aug 2026</span>
                <span className="badge badge-watch">Watch</span>
              </div>
              <div className="report-row">
                <span className="rr-label">LDL Cholesterol</span>
                <span className="rr-val flag">165 mg/dL ↑</span>
              </div>
              <div className="report-row">
                <span className="rr-label">HDL Cholesterol</span>
                <span className="rr-val">58 mg/dL</span>
              </div>
              <div className="report-row">
                <span className="rr-label">Triglycerides</span>
                <span className="rr-val">120 mg/dL</span>
              </div>
            </div>
            <div className="float-card card-chip">
              <div className="chip-line">
                <div className="chip-avatar">V</div>
                <div className="chip-text">
                  <strong>Your LDL rose 12%</strong> since May. Still worth a conversation at your next visit.
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      <div className="divider">
        <svg viewBox="0 0 1200 52" preserveAspectRatio="none">
          <path d="M0 26 L400 26 L420 8 L440 44 L460 26 L1200 26" stroke="#DCE3DC" strokeWidth="1.5" fill="none" />
        </svg>
      </div>

      <section className="journey" id="journey">
        <div className="wrap">
          <div className="section-head">
            <div className="eyebrow">The path every report takes</div>
            <h2 style={{ color: '#fff' }}>From upload to understanding, in four steps.</h2>
            <p>This is the actual sequence Spondon runs on every document — not a marketing flourish, the real pipeline.</p>
          </div>
          <div className="j-grid">
            <div className="j-step">
              <div className="j-num">01 / Upload</div>
              <h3>Drop it in</h3>
              <p>Blood tests, prescriptions, MRI, CT, discharge summaries — PDF, photo, or DICOM. We sort the type for you.</p>
            </div>
            <div className="j-step">
              <div className="j-num">02 / Extract</div>
              <h3>We read it</h3>
              <p>OCR and medical-language models pull out every value, range, and medication — you confirm anything uncertain.</p>
            </div>
            <div className="j-step">
              <div className="j-num">03 / Understand</div>
              <h3>Two summaries</h3>
              <p>A clinical brief for your doctor, and a plain-language explanation for you — generated from the same data.</p>
            </div>
            <div className="j-step">
              <div className="j-num">04 / Track</div>
              <h3>Watch it over time</h3>
              <p>Every new report joins your timeline, compared automatically against what came before.</p>
            </div>
          </div>
        </div>
      </section>

      <section id="showcase">
        <div className="wrap">
          <div className="section-head">
            <div className="eyebrow">Inside the product</div>
            <h2>One record. Two audiences.</h2>
            <p>The same data, shaped for how you and your doctor each actually need to read it.</p>
          </div>

          <div className="tabs">
            <button
              className={`tab-btn ${activeTab === 'patient' ? 'active' : ''}`}
              onClick={() => setActiveTab('patient')}
            >
              Patient view
            </button>
            <button
              className={`tab-btn ${activeTab === 'doctor' ? 'active' : ''}`}
              onClick={() => setActiveTab('doctor')}
            >
              Doctor view
            </button>
            <button
              className={`tab-btn ${activeTab === 'trends' ? 'active' : ''}`}
              onClick={() => setActiveTab('trends')}
            >
              Trends
            </button>
            <button
              className={`tab-btn ${activeTab === 'chat' ? 'active' : ''}`}
              onClick={() => setActiveTab('chat')}
            >
              Ask Spondon
            </button>
          </div>

          <div className="browser-frame">
            <div className="browser-bar">
              <span className="dot" /><span className="dot" /><span className="dot" />
              <span className="browser-url">app.spondon.health/records</span>
            </div>

            {activeTab === 'patient' && (
              <div className="screen">
                <div className="screen-grid">
                  <div className="panel">
                    <h4>What your LDL result means</h4>
                    <p style={{ fontSize: '13.5px', color: 'var(--ink-soft)', lineHeight: 1.6, marginBottom: '16px' }}>
                      LDL carries cholesterol through your blood and, at higher levels, can build up in artery walls over time. Yours came in a bit above the healthy range.
                    </p>
                    <div className="finding">
                      <span className="lbl">This result</span>
                      <span className="delta up">165 mg/dL</span>
                    </div>
                    <div className="finding">
                      <span className="lbl">Healthy range</span>
                      <span className="delta ok">&lt; 130 mg/dL</span>
                    </div>
                    <div className="finding">
                      <span className="lbl">Since your last test</span>
                      <span className="delta up">↑ 12%</span>
                    </div>
                  </div>
                  <div className="panel">
                    <h4>Ask your doctor</h4>
                    <p style={{ fontSize: '13px', color: 'var(--ink-soft)', lineHeight: 1.7 }}>
                      • Should we recheck this in 3 months?<br />
                      • Would a diet change help first?<br />
                      • Is a statin worth discussing now?
                    </p>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'doctor' && (
              <div className="screen">
                <div className="panel" style={{ maxWidth: '560px' }}>
                  <h4>Clinical summary — Priya Sharma, 41F</h4>
                  <div className="finding">
                    <span className="lbl">LDL-C</span>
                    <span className="delta up">165 mg/dL, ↑12% vs. 3mo prior — above ref. range (130)</span>
                  </div>
                  <div className="finding">
                    <span className="lbl">HDL-C</span>
                    <span className="delta ok">58 mg/dL — within range</span>
                  </div>
                  <div className="finding">
                    <span className="lbl">Active meds</span>
                    <span className="delta ok">No lipid-lowering agent on file</span>
                  </div>
                  <div className="finding">
                    <span className="lbl">Suggested</span>
                    <span className="delta ok">Consider recheck in 3mo; diet/statin discussion</span>
                  </div>
                </div>
              </div>
            )}

            {activeTab === 'trends' && (
              <div className="screen">
                <div className="panel">
                  <h4>LDL Cholesterol — last 12 months</h4>
                  <svg className="mini-chart" viewBox="0 0 600 120" preserveAspectRatio="none">
                    <rect x="0" y="70" width="600" height="30" fill="#E7EEE7" />
                    <polyline points="0,85 100,80 200,78 300,60 400,45 500,30 600,20" fill="none" stroke="#0E6F64" strokeWidth="2.5" />
                    <circle cx="600" cy="20" r="5" fill="#E1583F" />
                  </svg>
                  <p style={{ fontSize: '12px', color: 'var(--ink-soft)', marginTop: '6px' }}>
                    Shaded band = healthy range · red point = today&apos;s flagged result
                  </p>
                </div>
              </div>
            )}

            {activeTab === 'chat' && (
              <div className="screen">
                <div className="panel" style={{ maxWidth: '520px' }}>
                  <div className="chat-bubble user">What were my last three LDL readings?</div>
                  <div className="chat-bubble">
                    Your last three LDL results were 165, 147, and 138 mg/dL, from Aug, May, and Feb 2026
                    <span className="cite">Lipid Panel, Aug 12</span>. 
                    That&apos;s a steady upward trend — worth flagging to your doctor.
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      <section id="trust">
        <div className="wrap">
          <div className="section-head">
            <div className="eyebrow">Built for health data, not around it</div>
            <h2>Your records stay yours.</h2>
            <p>Every design decision starts from the fact that this is the most sensitive data you have.</p>
          </div>
          <div className="trust-grid">
            <div className="trust-item">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                <rect x="4" y="10" width="16" height="10" rx="2" stroke="#0E6F64" strokeWidth="1.8" />
                <path d="M8 10V7a4 4 0 018 0v3" stroke="#0E6F64" strokeWidth="1.8" />
              </svg>
              <h3>Encrypted, always</h3>
              <p>TLS in transit, AES-256 at rest. Nothing about your health leaves your device unprotected.</p>
            </div>
            <div className="trust-item">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                <circle cx="12" cy="8" r="3.5" stroke="#0E6F64" strokeWidth="1.8" />
                <path d="M4 20c0-4 3.5-6 8-6s8 2 8 6" stroke="#0E6F64" strokeWidth="1.8" />
              </svg>
              <h3>You choose who sees what</h3>
              <p>Grant a doctor access to specific reports, or all of them — and revoke it instantly, any time.</p>
            </div>
            <div className="trust-item">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none">
                <path d="M12 3l7 4v5c0 5-3.5 7.5-7 9-3.5-1.5-7-4-7-9V7l7-4z" stroke="#0E6F64" strokeWidth="1.8" />
              </svg>
              <h3>Every access, logged</h3>
              <p>An immutable audit trail records who viewed what and when — visible to you, not just us.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="cta-band">
        <div className="wrap">
          <div className="eyebrow">Start with your next report</div>
          <h2>Stop reading lab results alone.</h2>
          <div className="hero-ctas">
            <Link href="/signup" className="btn btn-primary">Upload your first report</Link>
            <Link href="/login" className="btn btn-ghost">Talk to our team</Link>
          </div>
        </div>
      </section>

      <footer>
        <div className="wrap footer-inner">
          <div className="logo" style={{ fontSize: '16px' }}>
            <SpondonLogo size={18} />
            Spondon
          </div>
          <div className="footer-links">
            <a href="#">Privacy</a>
            <a href="#">Security</a>
            <a href="#">For clinicians</a>
            <a href="#">Contact</a>
          </div>
          <div className="footer-note">© 2026 Spondon Health — Informational only, not a substitute for medical advice.</div>
        </div>
      </footer>
    </>
  )
}
