import { useEffect, useState } from 'react'
import { api } from '../api'

export default function DlqPanel({ queueId }) {
  const [entries, setEntries] = useState([])
  const [busyId, setBusyId] = useState(null)

  useEffect(() => { load() }, [queueId])

  async function load() {
    const data = await api.listDeadLetterQueue(queueId)
    setEntries(data)
  }

  async function handleReplay(id) {
    setBusyId(id)
    try {
      await api.replayDeadLetter(id)
      await load()
    } finally {
      setBusyId(null)
    }
  }

  async function handleDismiss(id) {
    setBusyId(id)
    try {
      await api.dismissDeadLetter(id)
      await load()
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-medium text-ink">Dead Letter Queue</h3>
        <button onClick={load} className="text-xs text-muted hover:text-ink">↻ Refresh</button>
      </div>

      <div className="space-y-2">
        {entries.map((entry) => (
          <div key={entry.id} className="border border-deadletter/30 bg-deadletter/5 rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-xs text-muted">Job {entry.job_id.slice(0, 8)}</span>
              <span className="font-mono text-xs text-muted">{entry.attempt_count} attempts made</span>
            </div>
            <p className="text-xs text-failed font-mono mb-3 break-words">{entry.final_error}</p>
            <div className="flex gap-2">
              <button
                onClick={() => handleReplay(entry.id)}
                disabled={busyId === entry.id}
                className="text-xs bg-accent hover:bg-accent/90 disabled:opacity-50 text-white rounded px-2.5 py-1"
              >
                Replay
              </button>
              <button
                onClick={() => handleDismiss(entry.id)}
                disabled={busyId === entry.id}
                className="text-xs border border-border hover:bg-panelhover disabled:opacity-50 text-muted rounded px-2.5 py-1"
              >
                Dismiss
              </button>
            </div>
          </div>
        ))}
        {entries.length === 0 && (
          <p className="text-sm text-muted py-6 text-center border border-dashed border-border rounded-lg">
            No jobs in the dead letter queue — everything's healthy
          </p>
        )}
      </div>
    </div>
  )
}
