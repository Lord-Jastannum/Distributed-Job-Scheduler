const API_BASE = '/api/v1'

function getToken() {
  return localStorage.getItem('token')
}

export function setToken(token) {
  if (token) localStorage.setItem('token', token)
  else localStorage.removeItem('token')
}

async function request(path, { method = 'GET', body, formBody, headers = {} } = {}) {
  const token = getToken()
  const finalHeaders = { ...headers }
  let finalBody = body

  if (formBody) {
    finalHeaders['Content-Type'] = 'application/x-www-form-urlencoded'
    finalBody = new URLSearchParams(formBody).toString()
  } else if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json'
    finalBody = JSON.stringify(body)
  }

  if (token) finalHeaders['Authorization'] = `Bearer ${token}`

  const res = await fetch(`${API_BASE}${path}`, { method, headers: finalHeaders, body: finalBody })

  if (res.status === 204) return null

  const text = await res.text()
  const data = text ? JSON.parse(text) : null

  if (!res.ok) {
    const message = data?.error?.message || data?.detail || `Request failed (${res.status})`
    const err = new Error(message)
    err.status = res.status
    err.details = data?.error?.details
    throw err
  }
  return data
}

export const api = {
  register: (email, password, name) => request('/auth/register', { method: 'POST', body: { email, password, name } }),
  login: (email, password) => request('/auth/login', { method: 'POST', formBody: { username: email, password } }),

  listOrganizations: () => request('/organizations'),
  createOrganization: (name) => request('/organizations', { method: 'POST', body: { name } }),

  listProjects: (orgId) => request(`/organizations/${orgId}/projects`),
  createProject: (orgId, name) => request(`/organizations/${orgId}/projects`, { method: 'POST', body: { name } }),

  listQueues: (projectId) => request(`/projects/${projectId}/queues`),
  createQueue: (projectId, payload) => request(`/projects/${projectId}/queues`, { method: 'POST', body: payload }),
  pauseQueue: (queueId) => request(`/queues/${queueId}/pause`, { method: 'POST' }),
  resumeQueue: (queueId) => request(`/queues/${queueId}/resume`, { method: 'POST' }),

  listJobs: (queueId, { status, type, page = 1, pageSize = 20 } = {}) => {
    const params = new URLSearchParams({ page, page_size: pageSize })
    if (status) params.set('status', status)
    if (type) params.set('type', type)
    return request(`/queues/${queueId}/jobs?${params}`)
  },
  createJob: (queueId, payload) => request(`/queues/${queueId}/jobs`, { method: 'POST', body: payload }),
  createBatchJobs: (queueId, jobs) => request(`/queues/${queueId}/jobs/batch`, { method: 'POST', body: { jobs } }),
  getJob: (jobId) => request(`/jobs/${jobId}`),
  getJobExecutions: (jobId) => request(`/jobs/${jobId}/executions`),

  listScheduledJobs: (queueId) => request(`/queues/${queueId}/scheduled-jobs`),
  createScheduledJob: (queueId, payload) => request(`/queues/${queueId}/scheduled-jobs`, { method: 'POST', body: payload }),
  deactivateScheduledJob: (id) => request(`/scheduled-jobs/${id}/deactivate`, { method: 'POST' }),

  listWorkers: (projectId) => request(`/projects/${projectId}/workers`),
  listWorkerHeartbeats: (workerId) => request(`/workers/${workerId}/heartbeats`),

  listDeadLetterQueue: (queueId, includeResolved = false) =>
    request(`/queues/${queueId}/dead-letter-queue?include_resolved=${includeResolved}`),
  replayDeadLetter: (id) => request(`/dead-letter-queue/${id}/replay`, { method: 'POST' }),
  dismissDeadLetter: (id) => request(`/dead-letter-queue/${id}/dismiss`, { method: 'POST' }),
}
