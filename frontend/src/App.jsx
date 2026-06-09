import { useState, useRef, useEffect } from 'react'
import './App.css'

export default function App() {
  const [messages, setMessages] = useState([
    { role: 'bot', text: 'Ask me anything about your video library.' },
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [player, setPlayer] = useState(null)
  const [error, setError] = useState(null)
  const bottomRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const q = input.trim()
    if (!q || loading) return
    setInput('')
    setError(null)
    setMessages(prev => [...prev, { role: 'user', text: q }])
    setLoading(true)
    try {
      const res = await fetch('/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, top_k: 5 }),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      const data = await res.json()
      setMessages(prev => [...prev, {
        role: 'bot',
        text: data.answer,
        citations: data.citations || [],
      }])
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

  return (
    <div className="app">
      <header>
        <h1>Video Search</h1>
      </header>

      <div className="messages">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === 'bot' && <div className="avatar">AI</div>}
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
          <div className="msg bot">
            <div className="avatar">AI</div>
            <div className="bubble">
              <div className="typing"><span /><span /><span /></div>
            </div>
          </div>
        )}
        {error && <div className="error-msg">Error: {error}</div>}
        <div ref={bottomRef} />
      </div>

      {player && (
        <VideoModal
          fileUrl={player.fileUrl}
          startTime={player.startTime}
          title={player.title}
          onClose={() => setPlayer(null)}
        />
      )}

      <div className="input-bar">
        <input
          ref={inputRef}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask a question about the videos..."
          disabled={loading}
          autoFocus
        />
        <button onClick={send} disabled={loading || !input.trim()}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="22" y1="2" x2="11" y2="13" /><polygon points="22 2 15 22 11 13 2 9 22 2" />
          </svg>
        </button>
      </div>
    </div>
  )
}

function CitationCard({ citation, onPlay }) {
  const ts = citation.start_time != null
    ? `${fmt(citation.start_time)}${citation.end_time != null ? ` – ${fmt(citation.end_time)}` : ''}`
    : null

  const ext = citation.file_url?.split('.').pop().toLowerCase()
  const isAudio = ['mp3', 'wav', 'ogg', 'm4a'].includes(ext)
  const label = isAudio ? 'Listen' : 'Watch'

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
          className="watch-btn"
          onClick={() => onPlay({
            fileUrl: citation.file_url,
            startTime: citation.start_time ?? 0,
            title: citation.source_title,
          })}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3" /></svg>
          {label}
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
        {!ready && <div className="player-loading">Loading video…</div>}
      </div>
    </div>
  )
}

function fmt(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}
