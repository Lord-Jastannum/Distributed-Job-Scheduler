import { useState } from 'react'
import { api } from '../api'

export default function JobCreateForm({ queueId, onCreated }) {
  const [open, setOpen] = useState(false)
  const [jobType, setJobType] = useState('')
  const [payload, setPayload] = useState('{}')
  const [timing, setTiming] = useState('immediate') // immediate | delayed | cron
  const [delayMinutes, setDelayMinutes] = useState(5)
  const [cronExpr, setCronExpr] = useState('0 9 * * *')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    let parsedPayload
    try {
      parsedPayload = JSON.parse(payload)
    } catch {
      setError('Payload must be valid JSON')
      return
    }

    setSubmitting(true)
    try {
      if (timing === 'cron') {
        await api.createScheduledJob(queueId, {
          type: jobType,
          payload_template: parsedPayload,
          cron_expression: cronExpr,
        })
      } else {
        const body = { type: jobType, payload: parsedPayload }
        if (timing === 'delayed') {
          body.run_at = new Date(Date.now() + delayMinutes * 60000).toISOString()
        }
        await api.createJob(queueId, body)
      }
      setJobType('')
      setPayload('{}')
      setOpen(false)
      onCreated?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="bg-accent hover:bg-accent/90 text-white text-sm font-medium rounded-md px-3 py-1.5"
      >
        + New job
      </button>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="bg-panel border border-border rounded-lg p-4 space-y-3 mb-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-ink">New job</h3>
        <button type="button" onClick={() => setOpen(false)} className="text-muted hover:text-ink text-sm">✕</button>
      </div>

      <div>
        <label className="block text-xs text-muted mb-1">Job type</label>
        <input
          required
          value={jobType}
          onChange={(e) => setJobType(e.target.value)}
          placeholder="e.g. send_email"
          className="w-full bg-canvas border border-border rounded px-3 py-1.5 text-sm text-ink outline-none focus:border-accent"
        />
      </div>

      <div>
        <label className="block text-xs text-muted mb-1">Payload (JSON)</label>
        <textarea
          value={payload}
          onChange={(e) => setPayload(e.target.value)}
          rows={3}
          className="w-full bg-canvas border border-border rounded px-3 py-1.5 text-xs font-mono text-ink outline-none focus:border-accent"
        />
      </div>

      <div>
        <label className="block text-xs text-muted mb-1">Timing</label>
        <div className="flex gap-2">
          {['immediate', 'delayed', 'cron'].map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTiming(t)}
              className={`text-xs px-2.5 py-1 rounded border ${
                timing === t ? 'border-accent text-accent bg-accent/10' : 'border-border text-muted'
              }`}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      {timing === 'delayed' && (
        <div>
          <label className="block text-xs text-muted mb-1">Run in (minutes)</label>
          <input
            type="number"
            min={1}
            value={delayMinutes}
            onChange={(e) => setDelayMinutes(Number(e.target.value))}
            className="w-full bg-canvas border border-border rounded px-3 py-1.5 text-sm text-ink outline-none focus:border-accent"
          />
        </div>
      )}

      {timing === 'cron' && (
        <div>
          <label className="block text-xs text-muted mb-1">Cron expression</label>
          <input
            value={cronExpr}
            onChange={(e) => setCronExpr(e.target.value)}
            placeholder="0 9 * * *"
            className="w-full bg-canvas border border-border rounded px-3 py-1.5 text-sm font-mono text-ink outline-none focus:border-accent"
          />
          <p className="text-xs text-muted mt-1">Standard 5-field cron syntax (minute hour day month weekday)</p>
        </div>
      )}

      {error && <p className="text-failed text-xs">{error}</p>}

      <button
        type="submit"
        disabled={submitting}
        className="bg-accent hover:bg-accent/90 disabled:opacity-50 text-white text-sm font-medium rounded-md px-3 py-1.5"
      >
        {submitting ? 'Creating...' : 'Create job'}
      </button>
    </form>
  )
}
