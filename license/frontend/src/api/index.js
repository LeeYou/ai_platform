import axios from 'axios'

const http = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
})

export function getAdminToken() {
  return (
    window.localStorage.getItem('ai_admin_token') ||
    window.sessionStorage.getItem('ai_admin_token') ||
    import.meta.env.VITE_AI_ADMIN_TOKEN ||
    ''
  ).trim()
}

function attachAdminHeaders(config = {}) {
  const token = getAdminToken()
  if (!token) return config
  return {
    ...config,
    headers: {
      ...(config.headers || {}),
      Authorization: `Bearer ${token}`,
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

http.interceptors.request.use((config) => attachAdminHeaders(config))

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

// Dashboard
export function getDashboardStats() {
  return http.get('/dashboard')
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

// Capabilities
export function getCapabilities() {
  return http.get('/capabilities')
}

// Production Admin Tokens
export function getProdTokens() {
  return http.get('/prod-tokens')
}
export function createProdToken(data) {
  return http.post('/prod-tokens', data)
}
export function updateProdToken(id, data) {
  return http.put(`/prod-tokens/${id}`, data)
}
export function deleteProdToken(id) {
  return http.delete(`/prod-tokens/${id}`)
}
export function verifyProdToken(plaintext_token) {
  return http.post('/prod-tokens/verify', { plaintext_token })
}
