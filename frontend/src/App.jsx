import { useState, useRef, useEffect } from 'react'
import './App.css'

const QUICK_PROMPTS = [
  {
    title: 'Treatment Response',
    description: 'What are the latest findings on treatment response rates in oncology trials?',
    icon: '🔬',
  },
  {
    title: 'Biomarker Analysis',
    description: 'How are biomarkers being used to predict treatment outcomes?',
    icon: '🧬',
  },
  {
    title: 'Patient Cohorts',
    description: 'What are the key demographic factors in cancer patient studies?',
    icon: '👥',
  },
  {
    title: 'Clinical Protocols',
    description: 'What are the standard protocols for breast cancer treatment?',
    icon: '📋',
  },
]

function getOrCreateSessionId() {
  let sid = localStorage.getItem('session_id')
  if (!sid) {
    sid = crypto.randomUUID()
    localStorage.setItem('session_id', sid)
  }
  return sid
}

function getChatHistory() {
  try {
    return JSON.parse(localStorage.getItem('chat_history') || '[]')
  } catch {
    return []
  }
}

function saveChatHistory(history) {
  localStorage.setItem('chat_history', JSON.stringify(history))
}

function formatSessionTitle(messages) {
  const userMsg = messages.find(m => m.role === 'user')
  if (!userMsg) return 'New Chat'
  const text = userMsg.text
  return text.length > 28 ? text.slice(0, 28) + '…' : text
}

export default function App() {
  const [sessions, setSessions] = useState(getChatHistory)
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [player, setPlayer] = useState(null)
  const [error, setError] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(window.innerWidth > 768)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const sessionIdRef = useRef(getOrCreateSessionId())

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (activeSessionId) {
      const s = sessions.find(s => s.id === activeSessionId)
      setMessages(s ? s.messages : [])
    } else {
      setMessages([])
    }
  }, [activeSessionId, sessions])

  useEffect(() => {
    // Restore last active session
    const lastSessionId = localStorage.getItem('active_session_id')
    if (lastSessionId && sessions.find(s => s.id === lastSessionId)) {
      setActiveSessionId(lastSessionId)
      sessionIdRef.current = lastSessionId
    }
  }, [])

  useEffect(() => {
    if (activeSessionId) localStorage.setItem('active_session_id', activeSessionId)
  }, [activeSessionId])

  const createNewChat = () => {
    sessionIdRef.current = crypto.randomUUID()
    setActiveSessionId(null)
    setMessages([])
    localStorage.removeItem('active_session_id')
    inputRef.current?.focus()
  }

  const switchSession = (id) => {
    setActiveSessionId(id)
    sessionIdRef.current = id
    inputRef.current?.focus()
  }

  const deleteSession = (id, e) => {
    e.stopPropagation()
    setSessions(prev => {
      const next = prev.filter(s => s.id !== id)
      saveChatHistory(next)
      return next
    })
    if (activeSessionId === id) {
      setActiveSessionId(null)
      setMessages([])
      sessionIdRef.current = crypto.randomUUID()
      localStorage.removeItem('active_session_id')
    }
  }

  const send = async (text) => {
    const q = (text || input).trim()
    if (!q || loading) return
    setInput('')
    setError(null)

    const userMsg = { role: 'user', text: q }
    const newMessages = [...messages, userMsg]
    setMessages(newMessages)
    setLoading(true)

    const streaming = import.meta.env.VITE_STREAMING_ENABLED === 'true'

    try {
      let answerText = ''
      let citations = []

      if (streaming) {
        const res = await fetch('/query/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: q, top_k: 5, session_id: sessionIdRef.current }),
        })
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)

        // Placeholder bot message
        setMessages([...newMessages, { role: 'assistant', text: '', citations: [] }])

        const reader = res.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''

        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buffer += decoder.decode(value, { stream: true })

          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6))
                if (data.type === 'token') {
                  answerText += data.text
                  setMessages(prev => {
                    const updated = [...prev]
                    updated[updated.length - 1] = { ...updated[updated.length - 1], text: answerText }
                    return updated
                  })
                } else if (data.type === 'done') {
                  answerText = data.answer
                  citations = data.citations || []
                  setMessages(prev => {
                    const updated = [...prev]
                    const last = updated[updated.length - 1]
                    updated[updated.length - 1] = { ...last, text: answerText, citations }
                    return updated
                  })
                }
              } catch (_) {}
            }
          }
        }
      } else {
        const res = await fetch('/query', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: q, top_k: 5, session_id: sessionIdRef.current }),
        })
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
        const data = await res.json()
        answerText = data.answer
        citations = data.citations || []
        setMessages([...newMessages, { role: 'assistant', text: answerText, citations }])
      }

      // Save session
      const allMessages = [...newMessages, { role: 'assistant', text: answerText, citations }]
      const sessionTitle = formatSessionTitle(newMessages)
      setSessions(prev => {
        let next
        const existing = prev.find(s => s.id === sessionIdRef.current)
        if (existing) {
          next = prev.map(s => s.id === sessionIdRef.current
            ? { ...s, title: sessionTitle, messages: allMessages, updatedAt: Date.now() }
            : s
          )
        } else {
          next = [
            { id: sessionIdRef.current, title: sessionTitle, messages: allMessages, updatedAt: Date.now() },
            ...prev,
          ]
        }
        saveChatHistory(next)
        return next
      })
      setActiveSessionId(sessionIdRef.current)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const handleKey = e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  const hasChat = messages.length > 0

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-header">
          <button className="new-chat-btn" onClick={createNewChat}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Chat
          </button>
        </div>
        <div className="sidebar-sessions">
          {sessions.map(s => (
            <div
              key={s.id}
              className={`session-item ${activeSessionId === s.id ? 'active' : ''}`}
              onClick={() => switchSession(s.id)}
            >
              <svg className="session-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
              </svg>
              <span className="session-title">{s.title}</span>
              <button className="session-delete" onClick={e => deleteSession(s.id, e)} title="Delete">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <div className="sidebar-empty">No chats yet</div>
          )}
        </div>
      </aside>
      {sidebarOpen && <div className="sidebar-backdrop" onClick={() => setSidebarOpen(false)} />}

      {/* Main content */}
      <main className="main-content">
        <header className="main-header">
          <button className="sidebar-toggle" onClick={() => setSidebarOpen(p => !p)}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <line x1="3" y1="6" x2="21" y2="6" /><line x1="3" y1="12" x2="15" y2="12" /><line x1="3" y1="18" x2="18" y2="18" />
            </svg>
          </button>
          <h1 className="logo">
            <span className="logo-mark">⬡</span> OncoSearch
          </h1>
        </header>

        {!hasChat ? (
          <div className="welcome">
            <div className="welcome-content">
              <div className="welcome-icon">⬡</div>
              <h2>How can we <span className="accent">assist</span> you today?</h2>
              <p>Search across oncology video and audio libraries. Ask questions about cancer research, treatments, and clinical protocols.</p>

              <div className="quick-prompts">
                {QUICK_PROMPTS.map((p, i) => (
                  <button key={i} className="quick-card" onClick={() => send(p.description)}>
                    <div className="quick-card-header">
                      <span className="quick-title">{p.title}</span>
                      <span className="quick-arrow">↗</span>
                    </div>
                    <p className="quick-desc">{p.description}</p>
                  </button>
                ))}
              </div>
            </div>

            <div className="input-wrapper">
              <div className="input-bar">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="Type your question here..."
                  disabled={loading}
                  autoFocus
                />
                <button className="send-btn" onClick={() => send()} disabled={loading || !input.trim()}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="chat-view">
            <div className="messages">
              {messages.map((m, i) => (
                <div key={i} className={`msg ${m.role === 'user' ? 'user' : 'assistant'}`}>
                  {m.role !== 'user' && <div className="avatar">⬡</div>}
                  <div className="bubble">
                    <div className="answer">{m.text}</div>
                    {m.citations?.length > 0 && (
                      <div className="citations">
                        <div className="citation-label">Sources</div>
                        {m.citations.map((c, ci) => (
                          <CitationCard key={ci} citation={c} onPlay={setPlayer} />
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {loading && (
                <div className="msg assistant">
                  <div className="avatar">⬡</div>
                  <div className="bubble">
                    <div className="typing"><span /><span /><span /></div>
                  </div>
                </div>
              )}
              {error && <div className="error-msg">Error: {error}</div>}
              <div ref={bottomRef} />
            </div>

            <div className="input-wrapper bottom">
              <div className="input-bar">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={handleKey}
                  placeholder="Type your question here..."
                  disabled={loading}
                />
                <button className="send-btn" onClick={() => send()} disabled={loading || !input.trim()}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="5" y1="12" x2="19" y2="12" /><polyline points="12 5 19 12 12 19" />
                  </svg>
                </button>
              </div>
            </div>
          </div>
        )}

        {player && (
          <VideoModal
            fileUrl={player.fileUrl}
            startTime={player.startTime}
            title={player.title}
            onClose={() => setPlayer(null)}
          />
        )}
      </main>
    </div>
  )
}

function CitationCard({ citation, onPlay }) {
  const ts = citation.start_time != null
    ? `${fmt(citation.start_time)}${citation.end_time != null ? ` – ${fmt(citation.end_time)}` : ''}`
    : null

  return (
    <div className="citation-card">
      <div className="citation-meta">
        <span className="source-badge">{citation.source_type}</span>
        {citation.speaker && <span className="speaker">{citation.speaker}</span>}
        {ts && <span className="timestamp">{ts}</span>}
      </div>
      <p className="citation-text">"{citation.supporting_text}"</p>
      {citation.file_url && (
        <button
          className="play-btn"
          onClick={() => onPlay({
            fileUrl: citation.file_url,
            startTime: citation.start_time ?? 0,
            title: citation.source_title,
          })}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3" /></svg>
          Play
        </button>
      )}
    </div>
  )
}

function VideoModal({ fileUrl, startTime, title, onClose }) {
  const videoRef = useRef(null)
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const el = videoRef.current
    if (!el) return
    let retries = 0
    const seek = () => {
      if (el.readyState >= 1) {
        el.currentTime = startTime
        el.play()
        setReady(true)
      } else if (retries < 50) {
        retries++
        setTimeout(seek, 100)
      }
    }
    seek()
  }, [startTime])

  const ext = fileUrl?.split('.').pop().toLowerCase()
  const isAudio = ['mp3', 'wav', 'ogg', 'm4a'].includes(ext)

  return (
    <div className="player-overlay" onClick={onClose}>
      <div className={`player-container ${isAudio ? 'audio' : ''}`} onClick={e => e.stopPropagation()}>
        <button className="player-close" onClick={onClose}>&times;</button>
        {title && <div className="player-title">{title}</div>}
        {isAudio ? (
          <audio ref={videoRef} controls autoPlay className="audio-player">
            <source src={fileUrl} />
          </audio>
        ) : (
          <video ref={videoRef} controls autoPlay className="video-player">
            <source src={fileUrl} />
          </video>
        )}
        {!ready && <div className="player-loading">Loading…</div>}
      </div>
    </div>
  )
}

function fmt(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
