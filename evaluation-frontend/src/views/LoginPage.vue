<template>
  <div class="login-container">
    <el-card class="login-card">
      <template #header><h2>用户登录</h2></template>
      <el-form :model="loginForm" :rules="rules" ref="loginFormRef" label-width="80px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="loginForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleLogin" :loading="loading">登录</el-button>
          <el-button @click="$router.push('/register')">注册新账号</el-button>
          <el-button @click="guestLogin" :loading="guestLoading">游客登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, inject } from 'vue'
import { useRouter } from 'vue-router'
import http from '@/api/http'
import { ElMessage } from 'element-plus'

const router = useRouter()
const updateAuth = inject('updateAuth')
const loginFormRef = ref(null)
const loading = ref(false)
const guestLoading = ref(false)

const loginForm = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const handleLogin = async () => {
  const valid = await loginFormRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    const res = await http.post('/auth/login', loginForm)
    localStorage.setItem('token', res.data.token)
    localStorage.setItem('user', JSON.stringify(res.data.user))
    updateAuth()                     // 立即更新导航栏状态
    ElMessage.success('登录成功')
    router.push('/evaluation')
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '登录失败')
  } finally {
    loading.value = false
  }
}

const guestLogin = async () => {
  guestLoading.value = true
  try {
    const res = await http.post('/auth/guest-login')
    localStorage.setItem('token', res.data.token)
    localStorage.setItem('user', JSON.stringify(res.data.user))
    updateAuth()
    ElMessage.success('游客登录成功')
    router.push('/evaluation')
  } catch (err) {
    ElMessage.error('游客登录失败')
  } finally {
    guestLoading.value = false
  }
}
</script>

<style scoped>
.login-container { display: flex; justify-content: center; align-items: center; height: 80vh; }
.login-card { width: 400px; }
</style>