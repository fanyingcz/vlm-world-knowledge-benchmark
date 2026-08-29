<template>
  <div>
    <h3>数据集管理</h3>

    <!-- 搜索 & 操作 -->
    <el-row :gutter="20" style="margin-bottom: 16px;">
      <el-col :span="6">
        <el-select v-model="selectedSubject" clearable placeholder="选择学科" style="width: 100%">
          <el-option v-for="subj in subjectList" :key="subj" :label="subj" :value="subj" />
        </el-select>
      </el-col>
      <el-col :span="4">
        <el-button type="primary" @click="fetchData(1)">查询</el-button>
        <el-button @click="showCreateDialog = true">新增场景</el-button>
      </el-col>
    </el-row>

    <!-- 场景列表 -->
    <el-table :data="scenarios" border stripe style="width: 100%">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="category" label="学科" width="120" />
      <el-table-column label="前置问题" show-overflow-tooltip>
        <template #default="{ row }">{{ row.pre_question || '-' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220">
        <template #default="{ row }">
          <el-button size="small" @click="viewDetail(row)">查看/编辑</el-button>
          <el-button size="small" type="danger" @click="deleteScene(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <el-pagination
      v-model:current-page="currentPage"
      :page-size="pageSize"
      :total="total"
      layout="prev, pager, next, total"
      @current-change="handlePageChange"
      style="margin-top: 16px; justify-content: center;"
    />

    <!-- 场景详情/编辑对话框 -->
    <el-dialog v-model="detailVisible" title="场景详情与编辑" width="80%" :close-on-click-modal="false">
      <div v-if="currentScene">
        <el-form :model="editSceneForm" label-width="100px">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-form-item label="学科">
                <el-input v-model="editSceneForm.category" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="前置问题">
            <el-input v-model="editSceneForm.pre_question" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="前置答案">
            <el-input v-model="editSceneForm.pre_answer" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item label="COT">
            <el-input v-model="editSceneForm.cot" type="textarea" :rows="2" />
          </el-form-item>
          <el-form-item>
            <el-button type="primary" @click="updateScene">保存基本信息</el-button>
          </el-form-item>
        </el-form>

        <el-divider />

        <!-- 图片管理 -->
        <h4>关联图片</h4>
        <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px;">
          <div v-for="file in currentScene.files" :key="file.id" class="file-chip">
            <span>{{ file.file_name }}</span>
            <el-button type="danger" size="small" circle @click="deleteFile(file)">✕</el-button>
          </div>
        </div>
        <div style="display: flex; gap: 10px;">
          <el-input v-model="newFileName" placeholder="输入图片文件名" style="width: 250px" />
          <el-button type="primary" @click="addFile">添加图片</el-button>
        </div>

        <el-divider />

        <!-- 题目管理 -->
        <h4>题目列表</h4>
        <el-table :data="currentScene.questions" border stripe>
          <el-table-column type="index" label="序号" width="50" />
          <el-table-column prop="question" label="问题" show-overflow-tooltip />
          <el-table-column prop="question_type" label="题型" width="100" />
          <el-table-column prop="answer" label="答案" show-overflow-tooltip />
          <el-table-column prop="core" label="核心知识点" show-overflow-tooltip />
          <el-table-column label="操作" width="160">
            <template #default="{ row }">
              <el-button size="small" @click="editQuestion(row)">编辑</el-button>
              <el-button size="small" type="danger" @click="deleteQuestion(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 添加题目表单 -->
        <el-form :model="newQuestion" label-width="100px" style="margin-top: 16px;">
          <el-form-item label="问题">
            <el-input v-model="newQuestion.question" type="textarea" :rows="2" />
          </el-form-item>
          <el-row :gutter="20">
            <el-col :span="6">
              <el-form-item label="题型">
                <el-select v-model="newQuestion.question_type" style="width: 100%">
                  <el-option value="选择题" />
                  <el-option value="判断题" />
                  <el-option value="简答题" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="10">
              <el-form-item label="答案">
                <el-input v-model="newQuestion.answer" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="核心知识点">
                <el-input v-model="newQuestion.core" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item>
            <el-button type="success" @click="addQuestion">添加题目</el-button>
          </el-form-item>
        </el-form>
      </div>
    </el-dialog>

    <!-- 新增场景对话框 -->
    <el-dialog v-model="showCreateDialog" title="新增场景" width="500px" :close-on-click-modal="false">
      <el-form :model="createForm" label-width="100px">
        <el-form-item label="学科">
          <el-input v-model="createForm.category" />
        </el-form-item>
        <el-form-item label="前置问题">
          <el-input v-model="createForm.pre_question" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="前置答案">
          <el-input v-model="createForm.pre_answer" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="COT">
          <el-input v-model="createForm.cot" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="createScene">创建</el-button>
      </template>
    </el-dialog>

    <!-- 编辑题目对话框 -->
    <el-dialog v-model="questionEditVisible" title="编辑题目" width="500px">
      <el-form v-if="editingQuestion" :model="editingQuestion" label-width="100px">
        <el-form-item label="问题">
          <el-input v-model="editingQuestion.question" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="editingQuestion.question_type" style="width: 100%">
            <el-option value="选择题" />
            <el-option value="判断题" />
            <el-option value="简答题" />
          </el-select>
        </el-form-item>
        <el-form-item label="答案">
          <el-input v-model="editingQuestion.answer" />
        </el-form-item>
        <el-form-item label="核心知识点">
          <el-input v-model="editingQuestion.core" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="questionEditVisible = false">取消</el-button>
        <el-button type="primary" @click="saveQuestionEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '../api/http'

const subjectList = ref([])
const selectedSubject = ref('')
const scenarios = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

// 获取学科列表
const fetchSubjects = async () => {
  try {
    const res = await http.get('/subjects-list')
    subjectList.value = res.data
  } catch (e) {
    console.error(e)
  }
}

// 获取场景列表
const fetchData = async (page = currentPage.value) => {
  try {
    const params = { page, limit: pageSize.value }
    if (selectedSubject.value) params.subject = selectedSubject.value
    const res = await http.get('/datasets', { params })
    scenarios.value = res.data.records
    total.value = res.data.total
    currentPage.value = res.data.page
  } catch (e) {
    ElMessage.error('加载失败')
  }
}

const handlePageChange = (page) => {
  fetchData(page)
}

onMounted(() => {
  fetchSubjects()
  fetchData()
})

// 场景详情相关
const detailVisible = ref(false)
const currentScene = ref(null)
const editSceneForm = reactive({
  category: '',
  pre_question: '',
  pre_answer: '',
  cot: '',
})

const viewDetail = async (row) => {
  try {
    const res = await http.get(`/datasets/${row.id}`)
    currentScene.value = res.data
    editSceneForm.category = res.data.category
    editSceneForm.pre_question = res.data.pre_question
    editSceneForm.pre_answer = res.data.pre_answer
    editSceneForm.cot = res.data.cot
    detailVisible.value = true
  } catch (e) {
    ElMessage.error('获取详情失败')
  }
}

const updateScene = async () => {
  try {
    await http.put(`/datasets/${currentScene.value.id}`, { ...editSceneForm })
    ElMessage.success('基本信息已更新')
    const res = await http.get(`/datasets/${currentScene.value.id}`)
    currentScene.value = res.data
  } catch (e) {
    ElMessage.error('更新失败')
  }
}

// 图片操作
const newFileName = ref('')
const addFile = async () => {
  if (!newFileName.value.trim()) return ElMessage.warning('请输入文件名')
  try {
    await http.post(`/datasets/${currentScene.value.id}/files`, { file_name: newFileName.value.trim() })
    ElMessage.success('添加成功')
    newFileName.value = ''
    const res = await http.get(`/datasets/${currentScene.value.id}`)
    currentScene.value = res.data
  } catch (e) {
    ElMessage.error('添加失败')
  }
}

const deleteFile = async (file) => {
  try {
    await ElMessageBox.confirm(`确定删除图片 "${file.file_name}" 吗？`, '提示', { type: 'warning' })
    await http.delete(`/datasets/files/${file.id}`)
    ElMessage.success('删除成功')
    currentScene.value.files = currentScene.value.files.filter(f => f.id !== file.id)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

// 题目操作
const newQuestion = reactive({
  question: '',
  question_type: '选择题',
  answer: '',
  core: ''
})

const addQuestion = async () => {
  if (!newQuestion.question || !newQuestion.answer) return ElMessage.warning('问题与答案必填')
  try {
    await http.post(`/datasets/${currentScene.value.id}/questions`, { ...newQuestion })
    ElMessage.success('题目添加成功')
    Object.assign(newQuestion, { question: '', answer: '', core: '', question_type: '选择题' })
    const res = await http.get(`/datasets/${currentScene.value.id}`)
    currentScene.value = res.data
  } catch (e) {
    ElMessage.error('添加失败')
  }
}

const questionEditVisible = ref(false)
const editingQuestion = ref(null)

const editQuestion = (row) => {
  editingQuestion.value = { ...row }
  questionEditVisible.value = true
}

const saveQuestionEdit = async () => {
  try {
    const { id, ...data } = editingQuestion.value
    await http.put(`/datasets/questions/${id}`, data)
    ElMessage.success('保存成功')
    questionEditVisible.value = false
    const res = await http.get(`/datasets/${currentScene.value.id}`)
    currentScene.value = res.data
  } catch (e) {
    ElMessage.error('保存失败')
  }
}

const deleteQuestion = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除该问题吗？`, '警告', { type: 'warning' })
    await http.delete(`/datasets/questions/${row.id}`)
    ElMessage.success('已删除')
    const res = await http.get(`/datasets/${currentScene.value.id}`)
    currentScene.value = res.data
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}

// 新增场景
const showCreateDialog = ref(false)
const createForm = reactive({
  category: '',
  pre_question: '',
  pre_answer: '',
  cot: ''
})

const createScene = async () => {
  if (!createForm.category) return ElMessage.warning('学科不能为空')
  try {
    const res = await http.post('/datasets', { ...createForm })
    ElMessage.success(`场景创建成功，ID: ${res.data.id}`)
    showCreateDialog.value = false
    fetchData()
  } catch (e) {
    ElMessage.error('创建失败')
  }
}

const deleteScene = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除场景 ${row.id}？所有关联图片和问题将被删除。`, '删除确认', { type: 'warning' })
    await http.delete(`/datasets/${row.id}`)
    ElMessage.success('删除成功')
    fetchData()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败')
  }
}
</script>
<style scoped>
.file-chip {
  display: inline-flex;
  align-items: center;
  background: #f0f2f5;
  padding: 4px 8px;
  border-radius: 4px;
  margin-bottom: 6px;
}
.file-chip span {
  margin-right: 8px;
}
</style>