const STATUS_STYLES = {
  queued: { dot: 'bg-queued', text: 'text-queued' },
  scheduled: { dot: 'bg-scheduled', text: 'text-scheduled' },
  claimed: { dot: 'bg-running', text: 'text-running' },
  running: { dot: 'bg-running pulse', text: 'text-running' },
  completed: { dot: 'bg-completed', text: 'text-completed' },
  failed: { dot: 'bg-failed', text: 'text-failed' },
  dead_letter: { dot: 'bg-deadletter', text: 'text-deadletter' },
  active: { dot: 'bg-completed', text: 'text-completed' },
  paused: { dot: 'bg-queued', text: 'text-queued' },
  online: { dot: 'bg-completed pulse', text: 'text-completed' },
  offline: { dot: 'bg-muted', text: 'text-muted' },
  draining: { dot: 'bg-queued pulse', text: 'text-queued' },
}

export default function StatusBadge({ status }) {
  const style = STATUS_STYLES[status] || { dot: 'bg-muted', text: 'text-muted' }
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
      <span className={style.text}>{status}</span>
    </span>
  )
}
