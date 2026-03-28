import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1' })

/**
 * Normalize error.response.data.detail to a human-readable string.
 * FastAPI validation errors (422) return detail as an array of objects;
 * concatenating them directly produces "[object Object]".
 */
function normalizeErrorDetail(detail) {
  if (!detail) return ''
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(d => {
      const field = d.loc ? d.loc[d.loc.length - 1] : ''
      const msg = d.msg || ''
      return field ? `${field}: ${msg}` : msg
    }).join('; ')
  }
  if (typeof detail === 'object') {
    return detail.message || JSON.stringify(detail)
  }
  return String(detail)
}

http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.data?.detail && typeof err.response.data.detail !== 'string') {
      err.response.data.detail = normalizeErrorDetail(err.response.data.detail)
    }
    return Promise.reject(err)
  }
)

export const listModels = () => http.get('/models')
export const singleInfer = (formData) => http.post('/infer/single', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
export const batchInfer = (data) => http.post('/infer/batch', data)
export const getBatchJob = (id) => http.get(`/infer/batch/${id}`)
export const getBatchReport = (id) => http.get(`/infer/batch/${id}/report`)
export const compareVersions = (data) => http.post('/infer/compare', data)
