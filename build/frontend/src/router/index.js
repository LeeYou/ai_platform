import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import NewBuild from '../views/NewBuild.vue'
import BuildHistory from '../views/BuildHistory.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/new', component: NewBuild },
  { path: '/history', component: BuildHistory },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
