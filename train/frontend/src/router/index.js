import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from '../views/Dashboard.vue'
import Datasets from '../views/Datasets.vue'
import Capabilities from '../views/Capabilities.vue'
import Jobs from '../views/Jobs.vue'
import Models from '../views/Models.vue'
import AnnotationProjects from '../views/AnnotationProjects.vue'
import AnnotationWorkspace from '../views/AnnotationWorkspace.vue'

const routes = [
  { path: '/', component: Dashboard },
  { path: '/annotations', component: AnnotationProjects },
  { path: '/annotations/:id', component: AnnotationWorkspace },
  { path: '/datasets', component: Datasets },
  { path: '/capabilities', component: Capabilities },
  { path: '/jobs', component: Jobs },
  { path: '/models', component: Models },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
