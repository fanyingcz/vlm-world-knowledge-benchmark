<template>
  <div class="register-container">
    <el-card class="register-card">
      <template #header><h2>用户注册</h2></template>
      <el-form :model="registerForm" :rules="rules" ref="registerFormRef" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="registerForm.username" placeholder="至少3位" />
        </el-form-item>
        <el-form-item label="密码" prop="password">
          <el-input v-model="registerForm.password" type="password" placeholder="至少6位" />
        </el-form-item>
        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="registerForm.confirmPassword" type="password" placeholder="请再次输入密码" />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="registerForm.role" placeholder="请选择角色">
            <el-option label="游客" value="visitor" />
            <el-option label="正式用户" value="regular" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="handleRegister" :loading="loading">注册</el-button>
          <el-button @click="$router.push('/login')">返回登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import http from '@/api/http'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

const router = useRouter()
const registerFormRef = ref(null)
const loading = ref(false)

const registerForm = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  role: 'regular',
})

const validatePass2 = (rule, value, callback) => {
  if (value !== registerForm.password) {
    callback(new Error('两次输入密码不一致'))
  } else {
    callback()
  }
}

const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }, { min: 3, message: '至少3位', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }, { min: 6, message: '至少6位', trigger: 'blur' }],
  confirmPassword: [{ required: true, validator: validatePass2, trigger: 'blur' }],
}

const handleRegister = async () => {
  const valid = await registerFormRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await http.post('/auth/register', {
      username: registerForm.username,
      password: registerForm.password,
      role: registerForm.role,
    })
    ElMessage.success('注册成功，请登录')
    router.push('/login')
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '注册失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-container { display: flex; justify-content: center; align-items: center; height: 80vh; }
.register-card { width: 450px; }
</style>