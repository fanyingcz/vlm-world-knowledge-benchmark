<template>
  <div>
    <el-card class="config-card">
      <el-form :model="knowledgeForm" label-width="120px" label-position="left">
        <!-- 新增：数据源选择 -->
        <el-form-item label="数据源">
          <el-radio-group v-model="knowledgeForm.dataSource" @change="onDataSourceChange">
            <el-radio label="json">JSON 文件</el-radio>
            <el-radio label="database">数据库</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="选择学科">
          <el-select v-model="knowledgeForm.subject" placeholder="请选择学科">
            <el-option
              v-for="(info, key) in subjects"
              :key="key"
              :label="info.name"
              :value="key"
            />
          </el-select>
          <el-button
            style="margin-left: 10px"
            @click="loadKnowledgePoints"
            :disabled="!knowledgeForm.subject"
            :loading="loadingKP"
          >
            加载知识点
          </el-button>
        </el-form-item>
        <el-form-item label="选择知识点" v-if="knowledgePoints.length > 0">
          <el-select
            v-model="knowledgeForm.knowledgeIndex"
            placeholder="请选择知识点单元"
            @change="handleKnowledgeChange"
          >
            <el-option
              v-for="(kp, idx) in knowledgePoints"
              :key="idx"
              :label="kp.name"
              :value="idx"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="测试类型" v-if="selectedKnowledge">
          <el-radio-group v-model="knowledgeForm.testType" @change="handleTestTypeChange">
            <el-radio label="single">单一测试</el-radio>
            <el-radio label="question">问题测试</el-radio>
            <el-radio label="knowledge">知识点测试</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- 单一测试额外选项 -->
        <template v-if="knowledgeForm.testType === 'single' && selectedKnowledge">
          <el-form-item label="选择图片">
            <el-select v-model="knowledgeForm.singleImage" placeholder="请选择图片">
              <el-option
                v-for="(img, idx) in selectedKnowledge.files"
                :key="idx"
                :label="img"
                :value="img"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="选择问题">
            <el-select v-model="knowledgeForm.singleQuestionIndex" placeholder="请选择问题">
              <el-option
                v-for="(q, idx) in selectedKnowledge.questions"
                :key="idx"
                :label="`${idx+1}. [${selectedKnowledge.question_type[idx]}] ${q}`"
                :value="idx"
              />
            </el-select>
          </el-form-item>
        </template>

        <!-- 问题测试额外选项 -->
        <template v-if="knowledgeForm.testType === 'question' && selectedKnowledge">
          <el-form-item label="选择问题">
            <el-select v-model="knowledgeForm.questionIndex" placeholder="请选择问题">
              <el-option
                v-for="(q, idx) in selectedKnowledge.questions"
                :key="idx"
                :label="`${idx+1}. [${selectedKnowledge.question_type[idx]}] ${q}`"
                :value="idx"
              />
            </el-select>
          </el-form-item>
        </template>

        <!-- 共同：测试模型、模式 -->
        <template v-if="selectedKnowledge && knowledgeForm.testType">
          <el-form-item label="选择模型">
            <el-select v-model="knowledgeForm.model" placeholder="请选择模型">
              <el-option
                v-for="(name, key) in models"
                :key="key"
                :label="name"
                :value="key"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="测试模式">
            <el-select v-model="knowledgeForm.mode" placeholder="请选择测试模式">
              <el-option label="直接提问" value="1" />
              <el-option label="先问自身的 pre_question" value="2" />
              <el-option label="自定义提示词" value="3" />
              <el-option label="随机抽取其他科目 pre_question" value="4" />
            </el-select>
          </el-form-item>
          <el-form-item label="自定义提示词" v-if="knowledgeForm.mode === '3'">
            <el-input
              type="textarea"
              v-model="knowledgeForm.customPrompt"
              placeholder="自定义系统提示词"
              :rows="3"
            />
          </el-form-item>
          <el-form-item>
            <el-button
              type="primary"
              @click="startKnowledgeTest"
              :loading="kIsRunning || singleTestLoading"
              :disabled="kIsRunning || singleTestLoading"
            >
              {{ kIsRunning || singleTestLoading ? '测试中...' : '开始测试' }}
            </el-button>
            <el-button @click="clearKnowledgeLogs" :disabled="kIsRunning || singleTestLoading">
              清空日志
            </el-button>
          </el-form-item>
        </template>
      </el-form>
    </el-card>

    <!-- 单一测试结果卡片 -->
    <el-card v-if="singleTestResult" class="log-card" style="margin-top: 20px">
      <template #header>
        <span>单一测试结果</span>
        <el-tag
          :type="singleTestResult.is_correct ? 'success' : 'danger'"
          style="margin-left: 10px"
        >
          {{ singleTestResult.is_correct ? '正确' : '错误' }}
        </el-tag>
      </template>
      <div>
        <p><strong>模型回答：</strong>{{ singleTestResult.model_answer }}</p>
        <p><strong>标准答案：</strong>{{ singleTestResult.correct_answer }}</p>
        <p v-if="singleTestResult.evaluation"><strong>评估详情：</strong>{{ singleTestResult.evaluation }}</p>
      </div>
    </el-card>

    <!-- 日志与结果（问题测试、知识点测试） -->
    <el-card v-if="kTaskId" class="log-card" style="margin-top: 20px">
      <template #header>
        <div style="display: flex; align-items: center">
          <span>测试日志</span>
          <el-tag v-if="kTaskStatus === 'running'" type="warning" style="margin-left: 10px">运行中</el-tag>
          <el-tag v-else-if="kTaskStatus === 'completed'" type="success" style="margin-left: 10px">已完成</el-tag>
        </div>
      </template>
      <div class="log-container" ref="kLogContainer">
        <div v-for="(log, index) in kLogs" :key="index" class="log-line">
          {{ formatTime(log.time) }} - {{ log.msg }}
        </div>
        <div v-if="kLogs.length === 0" style="color: #999">暂无日志</div>
      </div>
    </el-card>

    <el-card v-if="kSummary" class="summary-card" style="margin-top: 20px">
      <template #header>
        <span>测试结果</span>
      </template>
      <el-row :gutter="20">
        <el-col :span="4"><el-statistic title="总题数" :value="kSummary.total" /></el-col>
        <el-col :span="4"><el-statistic title="正确数" :value="kSummary.correct" /></el-col>
        <el-col :span="4"><el-statistic title="错误数" :value="kSummary.incorrect" /></el-col>
        <el-col :span="5"><el-statistic title="正确率" :value="kSummary.accuracy + '%'" /></el-col>
        <el-col :span="7">
          <el-statistic>
            <template #title>
              <span>加权准确率
                <el-tooltip content="权重：简答题4分，选择题2分，判断题1分" placement="top">
                  <span style="border-bottom: 1px dashed #999; cursor: help;">ⓘ</span>
                </el-tooltip>
              </span>
            </template>
            <template #default>{{ kSummary.weighted_accuracy ?? '—' }}%</template>
          </el-statistic>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, nextTick, inject } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

// ---------- 注入全局锁 ----------
const acquireTaskLock = inject('acquireTaskLock')
const releaseTaskLock = inject('releaseTaskLock')

// ---------- 通用数据 ----------
const models = ref({})
const subjects = ref({})

// ---------- 表单数据 ----------
const knowledgeForm = reactive({
  dataSource: 'json',       // 新增字段
  subject: '',
  knowledgeIndex: null,
  testType: '',
  singleImage: '',
  singleQuestionIndex: null,
  questionIndex: null,
  model: '',
  mode: '1',
  customPrompt: ''
})
const knowledgePoints = ref([])
const loadingKP = ref(false)
const selectedKnowledge = ref(null)

// ---------- 异步任务数据 ----------
const kTaskId = ref(null)
const kTaskStatus = ref(null)
const kIsRunning = ref(false)
const kLogs = ref([])
const kLastLogIndex = ref(-1)
const kSummary = ref(null)
const kPollingTimer = ref(null)
const kLogContainer = ref(null)

// 单一测试
const singleTestResult = ref(null)
const singleTestLoading = ref(false)

// ---------- 持久化 taskId ----------
const KTASK_ID_KEY = 'knowledge_current_task_id'
const getStoredKnowledgeTaskId = () => localStorage.getItem(KTASK_ID_KEY)
const setStoredKnowledgeTaskId = (id) => localStorage.setItem(KTASK_ID_KEY, id)
const removeStoredKnowledgeTaskId = () => localStorage.removeItem(KTASK_ID_KEY)

// ---------- 工具函数 ----------
const formatTime = (timestamp) => {
  const date = new Date(timestamp * 1000)
  return date.toLocaleTimeString()
}

// ---------- 初始化 ----------
const fetchModels = async () => {
  try {
    const res = await axios.get('/api/models')
    models.value = res.data
    if (Object.keys(models.value).length > 0) {
      knowledgeForm.model = Object.keys(models.value)[0]
    }
  } catch (err) {
    ElMessage.error('获取模型列表失败，请确保后端服务已启动')
  }
}

const fetchSubjects = async () => {
  try {
    const res = await axios.get('/api/subjects')
    subjects.value = res.data
    if (Object.keys(subjects.value).length > 0) {
      knowledgeForm.subject = Object.keys(subjects.value)[0]
    }
  } catch (err) {
    ElMessage.error('获取学科列表失败')
  }
}

// 数据源切换处理
const onDataSourceChange = () => {
  // 切换数据源时清空当前选择与结果
  knowledgeForm.knowledgeIndex = null
  selectedKnowledge.value = null
  knowledgeForm.testType = ''
  singleTestResult.value = null
  kTaskId.value = null
  kSummary.value = null
  if (kIsRunning.value) clearKnowledgeLogs()
  // 如果已选学科，重新加载知识点
  if (knowledgeForm.subject) loadKnowledgePoints()
}

// ---------- 知识点加载 ----------
const loadKnowledgePoints = async () => {
  if (!knowledgeForm.subject) return
  loadingKP.value = true
  try {
    if (kIsRunning.value) clearKnowledgeLogs()
    const params = { subject: knowledgeForm.subject }
    if (knowledgeForm.dataSource === 'database') {
      params.source = 'database'
    }
    const res = await axios.get('/api/knowledge_points', { params })
    knowledgePoints.value = res.data.knowledge_points || []
    knowledgeForm.knowledgeIndex = null
    selectedKnowledge.value = null
    singleTestResult.value = null
    kTaskId.value = null
    kSummary.value = null
  } catch (err) {
    ElMessage.error('加载知识点失败：' + (err.response?.data?.error || err.message))
  } finally {
    loadingKP.value = false
  }
}

const handleKnowledgeChange = (idx) => {
  if (kIsRunning.value) clearKnowledgeLogs()
  if (idx !== null && idx !== undefined) {
    selectedKnowledge.value = knowledgePoints.value[idx]
    knowledgeForm.testType = ''
    knowledgeForm.singleImage = ''
    knowledgeForm.singleQuestionIndex = null
    knowledgeForm.questionIndex = null
  } else {
    selectedKnowledge.value = null
  }
  singleTestResult.value = null
  kTaskId.value = null
  kSummary.value = null
}

const handleTestTypeChange = () => {
  if (kIsRunning.value) clearKnowledgeLogs()
  else {
    singleTestResult.value = null
    kTaskId.value = null
    kSummary.value = null
    kIsRunning.value = false
    kTaskStatus.value = null
  }
}

// ---------- 测试发起 ----------
const buildTestPayload = () => {
  const payload = {
    data_source: knowledgeForm.dataSource,  // 携带数据源
    subject: knowledgeForm.subject,
    unit_index: knowledgeForm.knowledgeIndex,
    model: knowledgeForm.model,
    mode: knowledgeForm.mode,
    custom_prompt: knowledgeForm.mode === '3' ? knowledgeForm.customPrompt : ''
  }
  if (knowledgeForm.testType === 'single') {
    payload.image = knowledgeForm.singleImage
    payload.question = selectedKnowledge.value.questions[knowledgeForm.singleQuestionIndex]
    payload.question_type = selectedKnowledge.value.question_type[knowledgeForm.singleQuestionIndex]
    payload.correct_answer = selectedKnowledge.value.answers[knowledgeForm.singleQuestionIndex]
    payload.core = selectedKnowledge.value.cores ? selectedKnowledge.value.cores[knowledgeForm.singleQuestionIndex] : ''
  } else if (knowledgeForm.testType === 'question') {
    payload.question_index = knowledgeForm.questionIndex
  }
  return payload
}

const startKnowledgeTest = async () => {
  if (!knowledgeForm.subject || knowledgeForm.knowledgeIndex === null || !knowledgeForm.testType) {
    ElMessage.warning('请完整填写配置')
    return
  }
  const payload = buildTestPayload()

  if (knowledgeForm.testType === 'single') {
    if (!acquireTaskLock('knowledge')) {
      ElMessage.warning('有另一个评测任务正在进行中，请等待完成或取消后再试')
      return
    }
    singleTestLoading.value = true
    try {
      const res = await axios.post('/api/test_single', payload)
      if (res.data.success) {
        singleTestResult.value = res.data.result
      } else {
        ElMessage.error(res.data.error || '测试失败')
      }
    } catch (err) {
      ElMessage.error('单一测试失败：' + (err.response?.data?.error || err.message))
    } finally {
      singleTestLoading.value = false
      releaseTaskLock('knowledge')
    }
  } else {
    if (!acquireTaskLock('knowledge')) {
      ElMessage.warning('有另一个评测任务正在进行中，请等待完成或取消后再试')
      return
    }

    const url = knowledgeForm.testType === 'question' ? '/api/test_question' : '/api/test_knowledge'
    try {
      const res = await axios.post(url, payload)
      kTaskId.value = res.data.task_id
      setStoredKnowledgeTaskId(res.data.task_id)
      kIsRunning.value = true
      kTaskStatus.value = 'running'
      kLogs.value = []
      kLastLogIndex.value = -1
      kSummary.value = null
      singleTestResult.value = null
      ElMessage.success('测试任务已启动')
      kPollingTimer.value = setInterval(pollKnowledgeTask, 1000)
    } catch (err) {
      ElMessage.error('启动测试失败：' + (err.response?.data?.error || err.message))
      releaseTaskLock('knowledge')
    }
  }
}

// ---------- 轮询 ----------
const pollKnowledgeTask = async () => {
  if (!kTaskId.value) return
  try {
    const res = await axios.get(`/api/task/${kTaskId.value}/status`, {
      params: { last_index: kLastLogIndex.value }
    })
    const data = res.data
    if (data.logs && data.logs.length > 0) {
      kLogs.value.push(...data.logs)
      kLastLogIndex.value = data.total_logs - 1
      await nextTick()
      if (kLogContainer.value) kLogContainer.value.scrollTop = kLogContainer.value.scrollHeight
    }
    kTaskStatus.value = data.status
    if (data.status === 'completed') {
      kIsRunning.value = false
      kSummary.value = data.summary
      if (kPollingTimer.value) {
        clearInterval(kPollingTimer.value)
        kPollingTimer.value = null
      }
      ElMessage.success('测试完成')
      releaseTaskLock('knowledge')
      removeStoredKnowledgeTaskId()
    }
  } catch (err) {
    console.error('知识点轮询失败', err)
  }
}

const clearKnowledgeLogs = () => {
  if (kPollingTimer.value) {
    clearInterval(kPollingTimer.value)
    kPollingTimer.value = null
  }
  kLogs.value = []
  kLastLogIndex.value = -1
  kSummary.value = null
  kTaskId.value = null
  kIsRunning.value = false
  kTaskStatus.value = null
  singleTestResult.value = null
  releaseTaskLock('knowledge')
  removeStoredKnowledgeTaskId()
}

// ---------- 任务恢复 ----------
const restoreKnowledgeTask = async (storedTaskId) => {
  try {
    const res = await axios.get(`/api/task/${storedTaskId}/status`, {
      params: { last_index: -1 }
    })
    const data = res.data
    kTaskId.value = storedTaskId
    kLogs.value = data.logs || []
    kLastLogIndex.value = data.total_logs ? data.total_logs - 1 : -1
    kTaskStatus.value = data.status

    if (data.status === 'running') {
      kIsRunning.value = true
      if (!acquireTaskLock('knowledge')) {
        ElMessage.warning('有其他任务正在运行，已终止恢复')
        removeStoredKnowledgeTaskId()
        return
      }
      kPollingTimer.value = setInterval(pollKnowledgeTask, 1000)
    } else if (data.status === 'completed') {
      kIsRunning.value = false
      if (data.summary) kSummary.value = data.summary
    } else {
      removeStoredKnowledgeTaskId()
      releaseTaskLock('knowledge')
    }

    await nextTick()
    if (kLogContainer.value) kLogContainer.value.scrollTop = kLogContainer.value.scrollHeight
  } catch (err) {
    removeStoredKnowledgeTaskId()
    releaseTaskLock('knowledge')
    console.warn('恢复知识点测试任务失败', err)
  }
}

// ---------- 生命周期 ----------
onMounted(async () => {
  await fetchModels()
  await fetchSubjects()

  const storedTaskId = getStoredKnowledgeTaskId()
  if (storedTaskId) await restoreKnowledgeTask(storedTaskId)
})

onBeforeUnmount(() => {
  if (kPollingTimer.value) {
    clearInterval(kPollingTimer.value)
    kPollingTimer.value = null
  }
})
</script>

<style scoped>
.config-card {
  max-width: 800px;
}
.log-container {
  background: #f5f7fa;
  border-radius: 4px;
  padding: 12px;
  height: 300px;
  overflow-y: auto;
  font-family: 'Courier New', monospace;
  font-size: 14px;
}
.log-line {
  padding: 2px 0;
  border-bottom: 1px solid #e4e7ed;
  color: #303133;
}
.summary-card .el-statistic {
  text-align: center;
}
</style>