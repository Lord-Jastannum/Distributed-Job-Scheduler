import { useState } from 'react'
import Sidebar from '../components/Sidebar'
import JobTable from '../components/JobTable'
import JobCreateForm from '../components/JobCreateForm'
import WorkersPanel from '../components/WorkersPanel'
import DlqPanel from '../components/DlqPanel'
import { api } from '../api'
import { useAuth } from '../context/AuthContext'

const TABS = ['Jobs', 'Workers', 'Dead Letter Queue']

export default function Dashboard() {
  const [selection, setSelection] = useState(null)
  const [tab, setTab] = useState('Jobs')
  const [refreshKey, setRefreshKey] = useState(0)
  const { logout } = useAuth()

  async function handleToggleQueue() {
    const queue = selection.queue
    if (queue.status === 'active') await api.pauseQueue(queue.id)
    else await api.resumeQueue(queue.id)
    setSelection({ ...selection, queue: { ...queue, status: queue.status === 'active' ? 'paused' : 'active' } })
  }

  return (
    <div className="flex h-screen">
      <Sidebar selected={selection} onSelectQueue={(sel) => { setSelection(sel); setTab('Jobs') }} />

      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="border-b border-border px-6 py-3 flex items-center justify-between shrink-0">
          <div className="font-mono text-xs text-muted">
            {selection ? `${selection.org.name} / ${selection.project.name} / ${selection.queue.name}` : 'Select a queue to get started'}
          </div>
          <button onClick={logout} className="text-xs text-muted hover:text-ink">Sign out</button>
        </header>

        {!selection ? (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-muted text-sm">Pick or create an organization → project → queue on the left</p>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <h1 className="text-lg font-semibold text-ink">{selection.queue.name}</h1>
                <span className={`text-xs font-mono px-2 py-0.5 rounded ${selection.queue.status === 'active' ? 'bg-completed/15 text-completed' : 'bg-queued/15 text-queued'}`}>
                  {selection.queue.status}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-xs text-muted font-mono">concurrency: {selection.queue.concurrency_limit}</span>
                <button onClick={handleToggleQueue} className="text-xs border border-border hover:bg-panelhover text-ink rounded px-2.5 py-1">
                  {selection.queue.status === 'active' ? 'Pause queue' : 'Resume queue'}
                </button>
              </div>
            </div>

            <div className="flex gap-1 border-b border-border mb-5">
              {TABS.map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`text-sm px-3 py-2 border-b-2 -mb-px ${
                    tab === t ? 'border-accent text-ink' : 'border-transparent text-muted hover:text-ink'
                  }`}
                >
                  {t}
                </button>
              ))}
            </div>

            {tab === 'Jobs' && (
              <>
                <div className="mb-4">
                  <JobCreateForm queueId={selection.queue.id} onCreated={() => setRefreshKey((k) => k + 1)} />
                </div>
                <JobTable queueId={selection.queue.id} refreshKey={refreshKey} />
              </>
            )}
            {tab === 'Workers' && <WorkersPanel projectId={selection.project.id} />}
            {tab === 'Dead Letter Queue' && <DlqPanel queueId={selection.queue.id} />}
          </div>
        )}
      </main>
    </div>
  )
}
