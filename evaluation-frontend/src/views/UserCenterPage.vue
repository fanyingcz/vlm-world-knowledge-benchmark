<template>
  <div class="user-center">
    <el-card class="main-card">
      <template #header>
        <h2>用户中心</h2>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="用户名">{{ user.username }}</el-descriptions-item>
        <el-descriptions-item label="角色">
          <el-tag :type="user.role === 'admin' ? 'danger' : user.role === 'regular' ? 'success' : 'info'">
            {{ user.role === 'admin' ? '管理员' : user.role === 'regular' ? '正式用户' : '游客' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="注册时间" v-if="user.created_at">{{ user.created_at }}</el-descriptions-item>
      </el-descriptions>
      <div style="margin-top: 20px">
        <el-button type="primary" @click="$router.push('/evaluation')">前往模型评测</el-button>
        <el-button @click="$router.push('/analysis')">结果分析</el-button>
        <el-button @click="$router.push('/knowledge')">知识点测试</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const user = computed(() => {
  try {
    return JSON.parse(localStorage.getItem('user')) || {}
  } catch {
    return {}
  }
})
</script>

<style scoped>
.user-center {
  max-width: 600px;
  margin: 0 auto;
}
.main-card {
  margin-top: 30px;
}
</style>