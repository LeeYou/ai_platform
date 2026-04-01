import { createRouter, createWebHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import ApiTest from '../views/ApiTest.vue'
import Pipelines from '../views/Pipelines.vue'
import PipelineEdit from '../views/PipelineEdit.vue'
import PipelineTest from '../views/PipelineTest.vue'
import Status from '../views/Status.vue'
import Admin from '../views/Admin.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/api-test', component: ApiTest },
  { path: '/pipelines', component: Pipelines },
  { path: '/pipelines/new', component: PipelineEdit },
  { path: '/pipelines/:id/edit', component: PipelineEdit },
  { path: '/pipeline-test', component: PipelineTest },
  { path: '/status', component: Status },
  { path: '/admin', component: Admin },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
