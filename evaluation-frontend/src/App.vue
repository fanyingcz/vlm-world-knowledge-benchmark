<template>
  <div id="app">
    <el-container>
      <el-header style="padding: 0;">
        <div class="custom-nav">
          <el-menu
            ref="menuRef"
            mode="horizontal"
            :default-active="activeMenu"
            class="left-menu"
            :key="visibleMenuCount"
            router
          >
            <el-menu-item
              index="/evaluation"
              v-if="state.isLoggedIn"
              :disabled="taskLock.running && taskLock.page === 'knowledge'"
            >
              模型评测
            </el-menu-item>
            <el-menu-item index="/analysis" v-if="state.isLoggedIn">结果分析</el-menu-item>
            <el-menu-item
              index="/knowledge"
              v-if="state.isLoggedIn"
              :disabled="taskLock.running && taskLock.page === 'evaluation'"
            >
              知识点测试
            </el-menu-item>
            <el-menu-item index="/result-history" v-if="state.isLoggedIn">结果可视化</el-menu-item>
            <el-menu-item index="/admin" v-if="isAdmin">用户管理</el-menu-item>
            <el-menu-item index="/dataset-management" v-if="isAdmin">数据集管理</el-menu-item>
          </el-menu>
          <div class="right-section">
            <template v-if="!state.isLoggedIn">
              <el-button type="text" @click="$router.push('/login')">登录</el-button>
              <el-button type="text" @click="$router.push('/register')" style="margin-left: 10px;">注册</el-button>
            </template>
            <template v-else>
              <el-dropdown trigger="click" @command="handleCommand">
                <span class="user-dropdown-link">
                  <el-avatar :size="32" style="margin-right: 8px;">
                    {{ state.user.username?.charAt(0)?.toUpperCase() || 'U' }}
                  </el-avatar>
                  <span>{{ state.user.username }}</span>
                  <el-icon class="el-icon--right"><arrow-down /></el-icon>
                </span>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="userCenter">用户中心</el-dropdown-item>
                    <el-dropdown-item command="logout" divided>退出登录</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </div>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { computed, reactive, provide, onMounted, onUnmounted, ref, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const activeMenu = computed(() => route.path)

const state = reactive({
  isLoggedIn: false,
  user: {}
})

const updateAuthState = () => {
  const token = localStorage.getItem('token')
  state.isLoggedIn = !!token
  if (token) {
    try {
      state.user = JSON.parse(localStorage.getItem('user')) || {}
    } catch {
      state.user = {}
    }
  } else {
    state.user = {}
  }
}

const logout = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  updateAuthState()
  ElMessage.success('已退出登录')
  router.push('/login')
}

const handleCommand = (command) => {
  if (command === 'userCenter') {
    router.push('/user-center')
  } else if (command === 'logout') {
    logout()
  }
}

provide('logout', logout)
provide('updateAuth', updateAuthState)

const handleStorage = (e) => {
  if (e.key === 'token') updateAuthState()
}

onMounted(() => {
  updateAuthState()
  window.addEventListener('storage', handleStorage)
})

onUnmounted(() => {
  window.removeEventListener('storage', handleStorage)
})

const isAdmin = computed(() => state.user.role === 'admin')

const visibleMenuCount = computed(() => {
  let count = 0
  if (state.isLoggedIn) count += 4
  if (isAdmin.value) count += 2   // 用户管理 + 数据集管理
  return count
})

const menuRef = ref(null)
watch(visibleMenuCount, async () => {
  await nextTick()
  setTimeout(() => {
    menuRef.value?.resize?.()
  }, 0)
})

// ---------- 全局任务锁 ----------
const taskLock = reactive({
  running: false,
  page: null
})

function acquireTaskLock(page) {
  if (taskLock.running && taskLock.page === page) {
    return true
  }
  if (taskLock.running) {
    return false
  }
  taskLock.running = true
  taskLock.page = page
  return true
}

function releaseTaskLock(page) {
  if (taskLock.page === page) {
    taskLock.running = false
    taskLock.page = null
  }
}

provide('taskLock', taskLock)
provide('acquireTaskLock', acquireTaskLock)
provide('releaseTaskLock', releaseTaskLock)
</script>

<style>
#app {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', sans-serif;
  height: 100vh;
}
.el-main {
  padding: 20px;
}

.custom-nav {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background-color: #fff;
  border-bottom: 1px solid #e6e6e6;
  padding: 0 20px;
  height: 60px;
  min-width: 900px;
}

.left-menu {
  border-bottom: none !important;
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
}

.right-section {
  display: flex;
  align-items: center;
  white-space: nowrap;
  flex-shrink: 0;
}

.user-dropdown-link {
  display: flex;
  align-items: center;
  cursor: pointer;
  color: #303133;
  white-space: nowrap;
}
.user-dropdown-link:focus-visible {
  outline: none;
}
</style>