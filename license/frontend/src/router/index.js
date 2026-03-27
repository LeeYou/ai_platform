import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Customers from '../views/Customers.vue'
import Licenses from '../views/Licenses.vue'
import GenerateLicense from '../views/GenerateLicense.vue'
import KeyManagement from '../views/KeyManagement.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/customers', component: Customers },
  { path: '/licenses', component: Licenses },
  { path: '/generate', component: GenerateLicense },
  { path: '/keys', component: KeyManagement },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
