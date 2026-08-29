import { createRouter, createWebHistory } from 'vue-router'
import EvaluationPage from '@/views/EvaluationPage.vue'
import AnalysisPage from '@/views/AnalysisPage.vue'
import KnowledgeTestPage from '@/views/KnowledgeTestPage.vue'
import LoginPage from '@/views/LoginPage.vue'
import RegisterPage from '@/views/RegisterPage.vue'
import AdminPage from '@/views/AdminPage.vue'
import UserCenterPage from '@/views/UserCenterPage.vue'
import ResultHistoryPage from '@/views/ResultHistory.vue'
import DatasetManagement from '@/views/DatasetManagement.vue'   // 新增

const routes = [
  { path: '/', redirect: '/evaluation' },
  { path: '/login', name: 'Login', component: LoginPage, meta: { guest: true } },
  { path: '/register', name: 'Register', component: RegisterPage, meta: { guest: true } },
  { path: '/evaluation', name: 'Evaluation', component: EvaluationPage },
  { path: '/analysis', name: 'Analysis', component: AnalysisPage },
  { path: '/knowledge', name: 'Knowledge', component: KnowledgeTestPage },
  { path: '/admin', name: 'Admin', component: AdminPage, meta: { requiresAdmin: true } },
  { path: '/user-center', name: 'UserCenter', component: UserCenterPage },
  { path: '/result-history', name: 'ResultHistory', component: ResultHistoryPage },
  { path: '/dataset-management', name: 'DatasetManagement', component: DatasetManagement, meta: { requiresAdmin: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const token = localStorage.getItem('token')
  const user = JSON.parse(localStorage.getItem('user') || '{}')

  if (to.meta.guest) {
    if (token) {
      next('/evaluation')
    } else {
      next()
    }
  } else {
    if (!token) {
      next('/login')
    } else if (to.meta.requiresAdmin && user.role !== 'admin') {
      next('/evaluation')
    } else {
      next()
    }
  }
})

export default router