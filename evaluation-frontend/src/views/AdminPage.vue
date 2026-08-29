<template>
  <div>
    <el-card>
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <h2 style="margin:0;">用户管理</h2>
          <div>
            <el-input
              v-model="searchKeyword"
              placeholder="搜索用户名"
              clearable
              style="width: 200px; margin-right: 10px;"
              @clear="fetchUsers"
              @keyup.enter="fetchUsers"
            />
            <el-button type="primary" @click="fetchUsers">搜索</el-button>
            <el-button type="success" @click="openCreateDialog">添加用户</el-button>
          </div>
        </div>
      </template>

      <el-table :data="users" border stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="role" label="角色" />
        <el-table-column prop="created_at" label="创建时间" />
        <el-table-column label="操作" width="260">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="openEditDialog(row)"
              :disabled="row.id === currentUserId"
            >
              编辑
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="deleteUser(row.id)"
              :disabled="row.id === currentUserId"
              style="margin-left: 5px"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 添加/编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="dialogTitle"
      width="400px"
      @close="resetForm"
    >
      <el-form :model="form" label-width="80px">
        <el-form-item label="用户名">
          <el-input v-model="form.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item v-if="!isEdit" label="密码">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="form.role" style="width: 100%;">
            <el-option label="游客" value="visitor" />
            <el-option label="正式用户" value="regular" />
            <el-option label="管理员" value="admin" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitForm">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import http from '@/api/http';
import { ElMessage, ElMessageBox } from 'element-plus';

const users = ref([]);
const currentUserId = ref(null);
const searchKeyword = ref('');
const dialogVisible = ref(false);
const dialogTitle = ref('');
const isEdit = ref(false);

const form = reactive({
  id: null,
  username: '',
  password: '',
  role: 'regular',
});

// 获取用户列表（支持搜索）
const fetchUsers = async () => {
  try {
    const params = {};
    if (searchKeyword.value.trim()) {
      params.search = searchKeyword.value.trim();
    }
    const res = await http.get('/auth/users', { params });
    users.value = res.data.users;
    // 获取自己的ID
    const user = JSON.parse(localStorage.getItem('user') || '{}');
    currentUserId.value = user.id;
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '获取用户列表失败');
  }
};

// 打开创建对话框
const openCreateDialog = () => {
  isEdit.value = false;
  dialogTitle.value = '添加用户';
  form.id = null;
  form.username = '';
  form.password = '';
  form.role = 'regular';
  dialogVisible.value = true;
};

// 打开编辑对话框
const openEditDialog = (row) => {
  isEdit.value = true;
  dialogTitle.value = '编辑用户';
  form.id = row.id;
  form.username = row.username;
  form.password = '';      // 编辑不需要密码
  form.role = row.role;
  dialogVisible.value = true;
};

// 重置表单
const resetForm = () => {
  form.id = null;
  form.username = '';
  form.password = '';
  form.role = 'regular';
};

// 提交表单（创建 / 更新）
const submitForm = async () => {
  if (!form.username.trim()) {
    ElMessage.warning('用户名不能为空');
    return;
  }
  try {
    if (isEdit.value) {
      // 更新用户
      await http.put(`/auth/users/${form.id}`, {
        username: form.username.trim(),
        role: form.role,
      });
      ElMessage.success('用户信息已更新');
    } else {
      // 创建用户
      if (!form.password) {
        ElMessage.warning('密码不能为空');
        return;
      }
      await http.post('/auth/users', {
        username: form.username.trim(),
        password: form.password,
        role: form.role,
      });
      ElMessage.success('用户创建成功');
    }
    dialogVisible.value = false;
    fetchUsers();
  } catch (err) {
    ElMessage.error(err.response?.data?.error || '操作失败');
  }
};

// 删除用户
const deleteUser = async (userId) => {
  try {
    await ElMessageBox.confirm('确定要删除该用户吗？', '警告', { type: 'warning' });
    await http.delete(`/auth/users/${userId}`);
    ElMessage.success('用户已删除');
    fetchUsers();
  } catch (err) {
    if (err !== 'cancel') ElMessage.error(err.response?.data?.error || '删除失败');
  }
};

onMounted(() => {
  fetchUsers();
});
</script>