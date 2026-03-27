import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1' })

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
