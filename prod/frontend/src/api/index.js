import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

export function getAdminToken() {
  return (
    window.localStorage.getItem('ai_admin_token') ||
    window.sessionStorage.getItem('ai_admin_token') ||
    import.meta.env.VITE_AI_ADMIN_TOKEN ||
    ''
  ).trim()
}

function withAdminHeaders(config = {}, token = getAdminToken()) {
  const value = (token || '').trim()
  if (!value) return config
  return {
    ...config,
    headers: {
      ...(config.headers || {}),
      Authorization: `Bearer ${value}`,
    },
  }
}

/**
 * Extract a human-readable error message from any error shape.
 * Handles: AxiosError, FastAPI validation arrays, plain objects, strings.
 */
export function extractErrorMessage(e) {
  const detail = e?.response?.data?.detail
  if (detail) {
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail.map(d => {
        if (typeof d === 'string') return d
        const field = d.loc ? d.loc[d.loc.length - 1] : ''
        const msg = d.msg || ''
        return field ? `${field}: ${msg}` : msg
      }).join('; ')
    }
    if (typeof detail === 'object') {
      return detail.message || detail.msg || JSON.stringify(detail)
    }
    return String(detail)
  }
  if (e?.response?.data && typeof e.response.data === 'string') {
    return e.response.data.slice(0, 200)
  }
  if (e?.message && typeof e.message === 'string') return e.message
  if (typeof e === 'string') return e
  return '未知错误'
}

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.data?.detail && typeof err.response.data.detail !== 'string') {
      err.response.data.detail = extractErrorMessage(err)
    }
    return Promise.reject(err)
  }
)

// Health & Status
export function getHealth() {
  return http.get('/health')
}

export function getCapabilities() {
  return http.get('/capabilities')
}

export function getCapabilityDiagnostics() {
  return http.get('/capabilities/diagnostics')
}

export function getLicense() {
  return http.get('/license/status')
}

// Inference
export function infer(capability, formData) {
  return http.post(`/infer/${capability}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

// Admin
export function adminReload(token = getAdminToken()) {
  return http.post('/admin/reload', null, withAdminHeaders({}, token))
}

export function listABTests(token = getAdminToken()) {
  return http.get('/admin/ab_tests', withAdminHeaders({}, token))
}

export function reloadABTests(token = getAdminToken()) {
  return http.post('/admin/ab_tests/reload', null, withAdminHeaders({}, token))
}

// Pipelines
export function getPipelines() {
  return http.get('/pipelines')
}

export function getPipeline(id) {
  return http.get(`/pipelines/${id}`)
}

export function createPipeline(data) {
  return http.post('/pipelines', data)
}

export function updatePipeline(id, data) {
  return http.put(`/pipelines/${id}`, data)
}

export function deletePipeline(id) {
  return http.delete(`/pipelines/${id}`)
}

export function validatePipeline(id) {
  return http.post(`/pipelines/${id}/validate`)
}

export function runPipeline(id, formData) {
  return http.post(`/pipeline/${id}/run`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}
