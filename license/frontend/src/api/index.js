import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

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
    // Ensure detail is always a string so callers can safely display it
    if (err.response?.data?.detail && typeof err.response.data.detail !== 'string') {
      err.response.data.detail = normalizeErrorDetail(err.response.data.detail)
    }
    return Promise.reject(err)
  }
)

// Customers
export function getCustomers(page = 1, size = 20) {
  return http.get('/customers', { params: { page, size } })
}
export function createCustomer(data) {
  return http.post('/customers', data)
}
export function updateCustomer(id, data) {
  return http.put(`/customers/${id}`, data)
}
export function deleteCustomer(id) {
  return http.delete(`/customers/${id}`)
}

// Licenses
export function getLicenses(params) {
  return http.get('/licenses', { params })
}
export function createLicense(data) {
  return http.post('/licenses', data)
}
export function getLicense(id) {
  return http.get(`/licenses/${id}`)
}
export function downloadLicense(id) {
  return http.get(`/licenses/${id}/download`, { responseType: 'blob' })
}
export function renewLicense(id, data) {
  return http.post(`/licenses/${id}/renew`, data)
}
export function revokeLicense(id) {
  return http.post(`/licenses/${id}/revoke`)
}
export function getExpiringLicenses(days = 30) {
  return http.get('/licenses/expiring', { params: { days } })
}

// Keys
export function getKeys() {
  return http.get('/keys')
}
export function createKey(data) {
  return http.post('/keys', data)
}
export function downloadPublicKey(id) {
  return http.get(`/keys/${id}/public`, { responseType: 'blob' })
}
