import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

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

// Capabilities
export function getCapabilities() {
  return http.get('/capabilities')
}

// Key Pairs (proxied from license service)
export function getKeyPairs() {
  return http.get('/key-pairs')
}

// Builds
export function getBuilds() {
  return http.get('/builds')
}

export function triggerBuild(data) {
  return http.post('/builds', data)
}

export function getBuild(jobId) {
  return http.get(`/builds/${jobId}`)
}

export function getBuildLogs(jobId) {
  return http.get(`/builds/${jobId}/logs`, { responseType: 'text' })
}

export function getArtifacts(jobId) {
  return http.get(`/builds/${jobId}/artifacts`)
}

export function downloadArtifact(jobId, filename) {
  return http.get(`/builds/${jobId}/artifacts/${filename}`, { responseType: 'blob' })
}

/**
 * Open a WebSocket connection to stream build logs.
 * Returns the WebSocket instance.
 */
export function connectBuildWs(jobId) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return new WebSocket(`${proto}//${host}/ws/build/${jobId}`)
}
