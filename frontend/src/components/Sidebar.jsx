import { useEffect, useState } from 'react'
import { api } from '../api'

function InlineCreate({ placeholder, onCreate }) {
  const [active, setActive] = useState(false)
  const [value, setValue] = useState('')

  async function submit(e) {
    e.preventDefault()
    if (!value.trim()) return
    await onCreate(value.trim())
    setValue('')
    setActive(false)
  }

  if (!active) {
    return (
      <button
        onClick={() => setActive(true)}
        className="w-full text-left px-2 py-1 rounded text-xs text-muted hover:bg-panelhover hover:text-ink"
      >
        + {placeholder}
      </button>
    )
  }
  return (
    <form onSubmit={submit}>
      <input
        autoFocus
        className="w-full bg-canvas border border-border rounded px-2 py-1 text-xs text-ink outline-none focus:border-accent"
        placeholder={placeholder}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => !value && setActive(false)}
      />
    </form>
  )
}

export default function Sidebar({ selected, onSelectQueue }) {
  const [orgs, setOrgs] = useState([])
  const [projectsByOrg, setProjectsByOrg] = useState({})
  const [queuesByProject, setQueuesByProject] = useState({})
  const [expandedOrgs, setExpandedOrgs] = useState({})
  const [expandedProjects, setExpandedProjects] = useState({})
  const [newOrgName, setNewOrgName] = useState('')
  const [showNewOrg, setShowNewOrg] = useState(false)

  useEffect(() => { loadOrgs() }, [])

  async function loadOrgs() {
    const data = await api.listOrganizations()
    setOrgs(data)
  }

  async function toggleOrg(orgId) {
    setExpandedOrgs((s) => ({ ...s, [orgId]: !s[orgId] }))
    if (!projectsByOrg[orgId]) {
      const projects = await api.listProjects(orgId)
      setProjectsByOrg((s) => ({ ...s, [orgId]: projects }))
    }
  }

  async function toggleProject(projectId) {
    setExpandedProjects((s) => ({ ...s, [projectId]: !s[projectId] }))
    if (!queuesByProject[projectId]) {
      const queues = await api.listQueues(projectId)
      setQueuesByProject((s) => ({ ...s, [projectId]: queues }))
    }
  }

  async function handleCreateOrg(e) {
    e.preventDefault()
    if (!newOrgName.trim()) return
    await api.createOrganization(newOrgName.trim())
    setNewOrgName('')
    setShowNewOrg(false)
    loadOrgs()
  }

  return (
    <aside className="w-64 shrink-0 border-r border-border bg-panel h-screen overflow-y-auto flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center gap-2">
          <div className="h-2 w-2 rounded-full bg-running pulse" />
          <span className="font-mono text-xs text-muted uppercase tracking-widest">Job Scheduler</span>
        </div>
      </div>

      <nav className="flex-1 p-2 space-y-0.5">
        {orgs.map((org) => (
          <div key={org.id}>
            <button
              onClick={() => toggleOrg(org.id)}
              className="w-full text-left px-2 py-1.5 rounded text-sm text-ink hover:bg-panelhover flex items-center gap-1.5"
            >
              <span className="text-muted text-xs w-3">{expandedOrgs[org.id] ? '▾' : '▸'}</span>
              {org.name}
            </button>
            {expandedOrgs[org.id] && (
              <div className="ml-4 border-l border-border pl-2">
                {(projectsByOrg[org.id] || []).map((project) => (
                  <div key={project.id}>
                    <button
                      onClick={() => toggleProject(project.id)}
                      className="w-full text-left px-2 py-1.5 rounded text-sm text-muted hover:bg-panelhover flex items-center gap-1.5"
                    >
                      <span className="text-muted text-xs w-3">{expandedProjects[project.id] ? '▾' : '▸'}</span>
                      {project.name}
                    </button>
                    {expandedProjects[project.id] && (
                      <div className="ml-4 border-l border-border pl-2">
                        {(queuesByProject[project.id] || []).map((queue) => (
                          <button
                            key={queue.id}
                            onClick={() => onSelectQueue({ queue, project, org })}
                            className={`w-full text-left px-2 py-1.5 rounded text-xs font-mono flex items-center gap-1.5 ${
                              selected?.queue?.id === queue.id
                                ? 'bg-accent/15 text-accent'
                                : 'text-muted hover:bg-panelhover hover:text-ink'
                            }`}
                          >
                            <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${queue.status === 'active' ? 'bg-completed' : 'bg-queued'}`} />
                            <span className="truncate">{queue.name}</span>
                          </button>
                        ))}
                        {(queuesByProject[project.id] || []).length === 0 && (
                          <p className="text-xs text-muted px-2 py-1">No queues yet</p>
                        )}
                        <InlineCreate
                          placeholder="New queue"
                          onCreate={async (name) => {
                            await api.createQueue(project.id, { name, priority: 0, concurrency_limit: 5 })
                            const queues = await api.listQueues(project.id)
                            setQueuesByProject((s) => ({ ...s, [project.id]: queues }))
                          }}
                        />
                      </div>
                    )}
                  </div>
                ))}
                {(projectsByOrg[org.id] || []).length === 0 && (
                  <p className="text-xs text-muted px-2 py-1">No projects yet</p>
                )}
                <InlineCreate
                  placeholder="New project"
                  onCreate={async (name) => {
                    await api.createProject(org.id, name)
                    const projects = await api.listProjects(org.id)
                    setProjectsByOrg((s) => ({ ...s, [org.id]: projects }))
                  }}
                />
              </div>
            )}
          </div>
        ))}
      </nav>

      <div className="p-2 border-t border-border">
        {showNewOrg ? (
          <form onSubmit={handleCreateOrg} className="flex gap-1">
            <input
              autoFocus
              className="flex-1 bg-canvas border border-border rounded px-2 py-1 text-xs text-ink outline-none focus:border-accent"
              placeholder="Organization name"
              value={newOrgName}
              onChange={(e) => setNewOrgName(e.target.value)}
              onBlur={() => !newOrgName && setShowNewOrg(false)}
            />
          </form>
        ) : (
          <button
            onClick={() => setShowNewOrg(true)}
            className="w-full text-left px-2 py-1.5 rounded text-xs text-muted hover:bg-panelhover hover:text-ink"
          >
            + New organization
          </button>
        )}
      </div>
    </aside>
  )
}
