import { createRouter, createWebHashHistory } from 'vue-router'
import { api, auth } from './api'
import MainLayout from './layouts/MainLayout.vue'

const routes = [
  { path: '/login', name: 'login', component: () => import('./views/Login.vue') },
  {
    path: '/',
    component: MainLayout,
    redirect: '/customers',
    children: [
      { path: 'customers', name: 'customers', component: () => import('./views/Customers.vue'), meta: { title: '客户管理' } },
      { path: 'scan', name: 'scan', component: () => import('./views/Scan.vue'), meta: { title: '风险扫描' } },
      { path: 'risks', name: 'risks', component: () => import('./views/RiskTable.vue'), meta: { title: '风险台账' } },
      { path: 'settings', name: 'settings', component: () => import('./views/Settings.vue'), meta: { title: '系统配置' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({ history: createWebHashHistory(), routes })

router.beforeEach(async (to) => {
  if (!auth.checked) {
    try {
      const r = await api.get('/api/me')
      auth.ok = true
      auth.defaultPassword = r.default_password
    } catch {
      auth.ok = false
    }
    auth.checked = true
  }
  if (to.name !== 'login' && !auth.ok) return { name: 'login' }
  if (to.name === 'login' && auth.ok) return { path: '/' }
})

export default router
