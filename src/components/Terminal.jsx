import { useEffect, useRef } from 'react'
import { WifiHigh } from '@phosphor-icons/react'

export default function Terminal({ lines = [], connected = true }) {
  const outputRef = useRef(null)

  useEffect(() => {
    if (outputRef.current) {
      outputRef.current.scrollTop = outputRef.current.scrollHeight
    }
  }, [lines])

  return (
    <section className="terminal theme-console">
      <div className="terminal-bar">
        <span>Terminal // grab_maps_api_v4</span>
        <span>
          <WifiHigh weight="fill" className="stream-icon" />
          {connected ? 'Stream OK' : 'Stream Idle'}
        </span>
      </div>
      <div className="terminal-output" aria-live="polite" ref={outputRef}>
        {lines.length === 0 && (
          <div className="terminal-line">{'> Awaiting audit...'}</div>
        )}
        {lines.map((line) => (
          <div className={`terminal-line ${line.tone || ''}`} key={line.seq}>
            {line.text}
          </div>
        ))}
        <div className="cursor">_</div>
      </div>
    </section>
  )
}
