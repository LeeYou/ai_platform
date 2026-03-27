import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1' })

export const listModels = () => http.get('/models')
export const singleInfer = (formData) => http.post('/infer/single', formData, {
  headers: { 'Content-Type': 'multipart/form-data' }
})
export const batchInfer = (data) => http.post('/infer/batch', data)
export const getBatchJob = (id) => http.get(`/infer/batch/${id}`)
export const getBatchReport = (id) => http.get(`/infer/batch/${id}/report`)
export const compareVersions = (data) => http.post('/infer/compare', data)
