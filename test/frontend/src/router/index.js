import { createRouter, createWebHashHistory } from 'vue-router'
import Models from '../views/Models.vue'
import SingleTest from '../views/SingleTest.vue'
import BatchTest from '../views/BatchTest.vue'
import Compare from '../views/Compare.vue'

const routes = [
  { path: '/', component: Models },
  { path: '/single', component: SingleTest },
  { path: '/batch', component: BatchTest },
  { path: '/compare', component: Compare },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
