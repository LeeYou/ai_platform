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

export const listModels = () => http.get('/models')
export const singleInfer = (formData) => http.post('/infer/single', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
export const batchInfer = (data) => http.post('/infer/batch', data)
export const getBatchJob = (id) => http.get(`/infer/batch/${id}`)
export const getBatchReport = (id) => http.get(`/infer/batch/${id}/report`)
export const compareVersions = (data) => http.post('/infer/compare', data)
