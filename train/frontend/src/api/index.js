import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1' })

/**
 * Extract a human-readable error message from any error shape.
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

// Datasets
export const listDatasets = () => http.get('/datasets/')
export const getDataset = (name) => http.get(`/datasets/${name}`)

// Capabilities
export const listCapabilities = () => http.get('/capabilities/')
export const getCapability = (id) => http.get(`/capabilities/${id}`)
export const createCapability = (data) => http.post('/capabilities/', data)
export const updateCapability = (id, data) => http.put(`/capabilities/${id}`, data)
export const deleteCapability = (id) => http.delete(`/capabilities/${id}`)

// Jobs
export const listJobs = (params) => http.get('/jobs/', { params })
export const createJob = (data) => http.post('/jobs/', data)
export const getJob = (id) => http.get(`/jobs/${id}`)
export const stopJob = (id) => http.post(`/jobs/${id}/stop`)
export const pauseJob = (id) => http.post(`/jobs/${id}/pause`)
export const resumeJob = (id) => http.post(`/jobs/${id}/resume`)
export const getJobLogs = (id) => http.get(`/jobs/${id}/logs`)

// Models
export const listModels = (params) => http.get('/models/', { params })
export const getModel = (id) => http.get(`/models/${id}`)
export const setCurrentModel = (id) => http.post(`/models/${id}/set-current`)
