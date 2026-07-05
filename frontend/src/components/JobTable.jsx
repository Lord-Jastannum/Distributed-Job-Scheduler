import { useEffect, useState, useCallback, useRef } from 'react'
import { api } from '../api'
import StatusBadge from './StatusBadge'

const STATUS_OPTIONS = ['queued', 'scheduled', 'claimed', 'running', 'completed', 'failed', 'dead_letter']

function useLiveJobs(queueId, enabled) {
  const [liveJobs, setLiveJobs] = useState(null)
  const [connected, setConnected] = useState(false)
  const wsRef = useRef(null)

  useEffect(() => {
    if (!enabled) return
    const token = localStorage.getItem('token')
    if (!token) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/api/v1/ws/queues/${queueId}/jobs?token=${token}`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data.type === 'jobs_snapshot') setLiveJobs(data.jobs)
    }

    return () => ws.close()
  }, [queueId, enabled])

  return { liveJobs, connected }
}

export default function JobTable({ queueId, refreshKey }) {
  const [jobs, setJobs] = useState([])
  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [selectedJob, setSelectedJob] = useState(null)
  const [executions, setExecutions] = useState([])

  const noFiltersActive = !statusFilter && !typeFilter && page === 1
  const { liveJobs, connected } = useLiveJobs(queueId, noFiltersActive)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const data = await api.listJobs(queueId, { status: statusFilter || undefined, type: typeFilter || undefined, page })
      setJobs(data)
    } finally {
      setLoading(false)
    }
  }, [queueId, statusFilter, typeFilter, page])

  useEffect(() => {
    if (noFiltersActive) return // WebSocket drives the table in this mode
    load()
  }, [load, refreshKey, noFiltersActive])

  const displayedJobs = noFiltersActive && liveJobs !== null ? liveJobs : jobs

  async function openJob(job) {
    const full = await api.getJob(job.id)
    setSelectedJob(full)
    const execs = await api.getJobExecutions(job.id)
    setExecutions(execs)
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <select
          value={statusFilter}
          onChange={(e) => { setStatusFilter(e.target.value); setPage(1) }}
          className="bg-panel border border-border rounded px-2 py-1.5 text-xs text-ink outline-none focus:border-accent"
        >
          <option value="">All statuses</option>
          {STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input
          placeholder="Filter by type..."
          value={typeFilter}
          onChange={(e) => { setTypeFilter(e.target.value); setPage(1) }}
          className="bg-panel border border-border rounded px-2 py-1.5 text-xs text-ink outline-none focus:border-accent flex-1 max-w-xs"
        />
        <button onClick={load} className="text-xs text-muted hover:text-ink px-2 py-1.5">
          {loading ? 'Refreshing...' : '↻ Refresh'}
        </button>
        {noFiltersActive && (
          <span className="text-xs font-mono flex items-center gap-1.5 ml-auto">
            <span className={`h-1.5 w-1.5 rounded-full ${connected ? 'bg-completed pulse' : 'bg-muted'}`} />
            <span className={connected ? 'text-completed' : 'text-muted'}>{connected ? 'live' : 'connecting...'}</span>
          </span>
        )}
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-panel border-b border-border text-left text-xs text-muted uppercase tracking-wide">
              <th className="px-3 py-2 font-medium">Type</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Priority</th>
              <th className="px-3 py-2 font-medium">Attempts</th>
              <th className="px-3 py-2 font-medium">Run at</th>
              <th className="px-3 py-2 font-medium">Job ID</th>
            </tr>
          </thead>
          <tbody>
            {displayedJobs.map((job) => (
              <tr
                key={job.id}
                onClick={() => openJob(job)}
                className="border-b border-border last:border-0 hover:bg-panelhover cursor-pointer"
              >
                <td className="px-3 py-2 text-ink">{job.type}</td>
                <td className="px-3 py-2"><StatusBadge status={job.status} /></td>
                <td className="px-3 py-2 text-muted font-mono text-xs">{job.priority}</td>
                <td className="px-3 py-2 text-muted font-mono text-xs">{job.attempt_count}</td>
                <td className="px-3 py-2 text-muted font-mono text-xs">{new Date(job.run_at).toLocaleString()}</td>
                <td className="px-3 py-2 text-muted font-mono text-xs">{job.id.slice(0, 8)}</td>
              </tr>
            ))}
            {displayedJobs.length === 0 && !loading && (
              <tr><td colSpan={6} className="px-3 py-8 text-center text-muted text-sm">No jobs match these filters</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-2">
        <button
          disabled={page === 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="text-xs text-muted hover:text-ink disabled:opacity-30 px-2 py-1"
        >
          ← Prev
        </button>
        <span className="text-xs text-muted">Page {page}</span>
        <button
          disabled={displayedJobs.length < 20}
          onClick={() => setPage((p) => p + 1)}
          className="text-xs text-muted hover:text-ink disabled:opacity-30 px-2 py-1"
        >
          Next →
        </button>
      </div>

      {selectedJob && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4" onClick={() => setSelectedJob(null)}>
          <div className="bg-panel border border-border rounded-lg max-w-lg w-full max-h-[80vh] overflow-y-auto p-5" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-mono text-sm text-ink">{selectedJob.type}</h3>
              <button onClick={() => setSelectedJob(null)} className="text-muted hover:text-ink">✕</button>
            </div>
            <div className="space-y-2 text-xs mb-4">
              <div className="flex justify-between"><span className="text-muted">Status</span><StatusBadge status={selectedJob.status} /></div>
              <div className="flex justify-between"><span className="text-muted">Job ID</span><span className="font-mono text-ink">{selectedJob.id}</span></div>
              <div className="flex justify-between"><span className="text-muted">Attempts</span><span className="font-mono text-ink">{selectedJob.attempt_count}</span></div>
              <div className="flex justify-between"><span className="text-muted">Batch ID</span><span className="font-mono text-ink">{selectedJob.batch_id || '—'}</span></div>
            </div>
            <p className="text-xs text-muted uppercase tracking-wide mb-2">Payload</p>
            <pre className="bg-canvas border border-border rounded p-3 text-xs font-mono text-ink overflow-x-auto mb-4">
              {JSON.stringify(selectedJob.payload, null, 2)}
            </pre>
            <p className="text-xs text-muted uppercase tracking-wide mb-2">Execution history</p>
            <div className="space-y-1.5">
              {executions.map((ex) => (
                <div key={ex.id} className="flex items-center justify-between text-xs bg-canvas border border-border rounded px-3 py-2">
                  <span className="text-muted">Attempt {ex.attempt_number}</span>
                  <StatusBadge status={ex.status} />
                  <span className="text-muted font-mono">{ex.duration_ms ? `${ex.duration_ms}ms` : '—'}</span>
                </div>
              ))}
              {executions.length === 0 && <p className="text-xs text-muted">No execution attempts yet</p>}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
