import { useEffect, useState } from 'react'
import { api } from '../api'
import StatusBadge from './StatusBadge'

export default function WorkersPanel({ projectId }) {
  const [workers, setWorkers] = useState([])
  const [expanded, setExpanded] = useState(null)
  const [heartbeats, setHeartbeats] = useState([])

  useEffect(() => { load() }, [projectId])

  async function load() {
    const data = await api.listWorkers(projectId)
    setWorkers(data)
  }

  async function toggleExpand(worker) {
    if (expanded === worker.id) {
      setExpanded(null)
      return
    }
    setExpanded(worker.id)
    const hb = await api.listWorkerHeartbeats(worker.id)
    setHeartbeats(hb)
  }

  function timeAgo(dateStr) {
    if (!dateStr) return 'never'
    const seconds = Math.floor((Date.now() - new Date(dateStr)) / 1000)
    if (seconds < 60) return `${seconds}s ago`
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
    return `${Math.floor(seconds / 3600)}h ago`
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-ink">Workers</h3>
        <button onClick={load} className="text-xs text-muted hover:text-ink">↻ Refresh</button>
      </div>

      <div className="space-y-2">
        {workers.map((worker) => (
          <div key={worker.id} className="border border-border rounded-lg overflow-hidden">
            <button
              onClick={() => toggleExpand(worker)}
              className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-panelhover text-left"
            >
              <div className="flex items-center gap-3">
                <StatusBadge status={worker.status} />
                <span className="font-mono text-xs text-ink">{worker.hostname}</span>
                <span className="font-mono text-xs text-muted">{worker.id.slice(0, 8)}</span>
              </div>
              <span className="text-xs text-muted">last seen {timeAgo(worker.last_seen_at)}</span>
            </button>
            {expanded === worker.id && (
              <div className="border-t border-border bg-canvas px-3 py-2 space-y-1">
                <p className="text-xs text-muted uppercase tracking-wide mb-1">Recent heartbeats</p>
                {heartbeats.map((hb) => (
                  <div key={hb.id} className="flex justify-between text-xs font-mono text-muted">
                    <span>{new Date(hb.sent_at).toLocaleTimeString()}</span>
                    <span>{hb.active_jobs} active job(s)</span>
                  </div>
                ))}
                {heartbeats.length === 0 && <p className="text-xs text-muted">No heartbeats recorded</p>}
              </div>
            )}
          </div>
        ))}
        {workers.length === 0 && (
          <p className="text-sm text-muted py-6 text-center border border-dashed border-border rounded-lg">
            No workers have registered for this project yet
          </p>
        )}
      </div>
    </div>
  )
}
