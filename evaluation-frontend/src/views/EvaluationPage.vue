<template>
  <div>
    <el-card class="config-card">
      <el-form :model="form" label-width="120px" label-position="left">
        <!-- 数据源选择 -->
        <el-form-item label="数据源">
          <el-radio-group v-model="form.dataSource" :disabled="isRunning" @change="onDataSourceChange">
            <el-radio label="json">JSON 文件</el-radio>
            <el-radio label="database">数据库</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="选择模型">
          <el-select
            v-model="form.model"
            placeholder="请选择模型"
            :disabled="isRunning"
          >
            <el-option
              v-for="(name, key) in models"
              :key="key"
              :label="name"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="选择学科">
          <el-select
            v-model="form.subject"
            placeholder="请选择学科"
            :disabled="isRunning"
          >
            <el-option
              v-for="(info, key) in subjects"
              :key="key"
              :label="info.name"
              :value="key"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="测试模式">
          <el-select
            v-model="form.mode"
            placeholder="请选择测试模式"
            :disabled="isRunning"
          >
            <el-option label="直接提问" value="1" />
            <el-option label="先问自身的 pre_question" value="2" />
            <el-option label="自定义提示词" value="3" />
            <el-option label="随机抽取其他科目 pre_question" value="4" />
          </el-select>
        </el-form-item>
        <el-form-item label="自定义提示词" v-if="form.mode === '3'">
          <el-input
            type="textarea"
            v-model="form.customPrompt"
            placeholder="输入自定义系统提示词（留空则使用默认）"
            :rows="3"
            :disabled="isRunning"
          />
        </el-form-item>
        <el-form-item label="测试数量">
          <el-radio-group v-model="form.quantityType" :disabled="isRunning">
            <el-radio label="all">全部题目</el-radio>
            <el-radio label="limit">指定数量</el-radio>
          </el-radio-group>
          <el-input-number
            v-if="form.quantityType === 'limit'"
            v-model="form.maxQuestions"
            :min="1"
            :max="999"
            :disabled="isRunning"
            style="margin-left: 20px"
          />
        </el-form-item>

        <!-- 按钮组 -->
        <el-form-item>
          <el-button
            type="primary"
            @click="startEvaluation"
            :loading="isRunning && taskStatus === 'running'"
            :disabled="isRunning && taskStatus === 'running'"
          >
            {{ btnStartText }}
          </el-button>
          <el-button
            @click="pauseTask"
            v-if="taskStatus === 'running' && isRunning"
            :disabled="pendingPause"
          >
            暂停
          </el-button>
          <el-button
          type="success"
          @click="resumeTask"
          :loading="resumePending"
          v-if="taskStatus === 'paused'"
          >
            继续
          </el-button>
          <el-button
            type="danger"
            @click="stopTask"
            v-if="taskStatus === 'running' || taskStatus === 'paused'"
          >
            强制结束
          </el-button>
          <el-button
            @click="clearLogs"
            :disabled="isRunning || taskStatus === 'paused'"
          >
            清空日志
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 实时日志区域 -->
    <el-card class="log-card" style="margin-top: 20px">
      <template #header>
        <div style="display: flex; align-items: center">
          <span>评测日志</span>
          <el-tag v-if="taskStatus === 'running'" type="warning" style="margin-left: 10px">
            运行中
          </el-tag>
          <el-tag v-else-if="taskStatus === 'paused'" type="info" style="margin-left: 10px">
            已暂停
          </el-tag>
          <el-tag v-else-if="taskStatus === 'completed'" type="success" style="margin-left: 10px">
            已完成
          </el-tag>
          <el-tag v-else-if="taskStatus === 'stopped'" type="danger" style="margin-left: 10px">
            已停止
          </el-tag>
          <el-tag v-else-if="taskStatus === 'error'" type="danger" style="margin-left: 10px">
            异常终止
          </el-tag>
        </div>
      </template>
      <div class="log-container" ref="logContainer">
        <div v-for="(log, index) in logs" :key="index" class="log-line">
          {{ formatTime(log.time) }} - {{ log.msg }}
        </div>
        <div v-if="logs.length === 0" style="color: #999">暂无日志，点击“开始评测”</div>
      </div>
    </el-card>

    <!-- 评测结果摘要 -->
    <el-card v-if="summary" class="summary-card" style="margin-top: 20px">
      <template #header>
        <div style="display: flex; justify-content: space-between; align-items: center">
          <span>评测结果</span>
          <el-button
            v-if="!resultFile && taskStatus === 'completed'"
            type="primary"
            size="small"
            @click="openSaveDialog"
          >
            保存结果
          </el-button>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="4">
          <el-statistic title="总题数" :value="summary.total" />
        </el-col>
        <el-col :span="4">
          <el-statistic title="正确数" :value="summary.correct" />
        </el-col>
        <el-col :span="4">
          <el-statistic title="错误数" :value="summary.incorrect" />
        </el-col>
        <el-col :span="5">
          <el-statistic title="正确率" :value="summary.accuracy + '%'" />
        </el-col>
        <el-col :span="7">
          <el-statistic>
            <template #title>
              <span>加权准确率 
                <el-tooltip content="权重：简答题4分，选择题2分，判断题1分" placement="top">
                  <span style="border-bottom: 1px dashed #999; cursor: help;">ⓘ</span>
                </el-tooltip>
              </span>
            </template>
            <template #default>
              {{ summary.weighted_accuracy ?? '—' }}%
            </template>
          </el-statistic>
        </el-col>
      </el-row>
      <div style="margin-top: 15px" v-if="resultFile">
        <el-link type="primary" :href="'/api/download/' + resultFile" target="_blank">
          下载详细结果 JSON 文件 ({{ resultFile }})
        </el-link>
      </div>
    </el-card>

    <!-- 文件名输入对话框 -->
    <el-dialog
      v-model="saveDialogVisible"
      title="保存评测结果"
      width="400px"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      :show-close="false"
      @closed="clearAutoSaveTimer"
    >
      <el-form :model="saveForm" label-width="80px">
        <el-form-item label="文件名">
          <el-input v-model="saveForm.filename" placeholder="请输入文件名（不含扩展名）">
            <template #append>.json</template>
          </el-input>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="skipSave">暂不保存</el-button>
        <el-button type="primary" @click="confirmSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'

// ---------- 注入全局锁 ----------
const acquireTaskLock = inject('acquireTaskLock')
const releaseTaskLock = inject('releaseTaskLock')

// ---------- 持久化 key ----------
const TASK_ID_KEY = 'evaluation_current_task_id'
const CONFIG_KEY = 'evaluation_current_config'

const getStoredTaskId = () => localStorage.getItem(TASK_ID_KEY)
const setStoredTaskId = (id) => localStorage.setItem(TASK_ID_KEY, id)
const removeStoredTaskId = () => localStorage.removeItem(TASK_ID_KEY)

const getStoredConfig = () => {
  const raw = localStorage.getItem(CONFIG_KEY)
  if (!raw) return null
  try { return JSON.parse(raw) } catch { return null }
}
const saveConfig = () => {
  localStorage.setItem(CONFIG_KEY, JSON.stringify({
    dataSource: form.dataSource,
    model: form.model,
    subject: form.subject,
    mode: form.mode,
    customPrompt: form.customPrompt,
    quantityType: form.quantityType,
    maxQuestions: form.maxQuestions
  }))
}
const removeConfig = () => localStorage.removeItem(CONFIG_KEY)

// ---------- 响应式数据 ----------
const models = ref({})
const subjects = ref({})
const form = reactive({
  dataSource: 'json',
  model: '',
  subject: '',
  mode: '1',
  customPrompt: '',
  quantityType: 'all',
  maxQuestions: 10
})

const isRunning = ref(false)
const taskId = ref(null)
const taskStatus = ref(null)
const logs = ref([])
const lastLogIndex = ref(-1)
const summary = ref(null)
const resultFile = ref('')
const pollingTimer = ref(null)
const pendingPause = ref(false)

const logContainer = ref(null)

const saveDialogVisible = ref(false)
const saving = ref(false)
const saveForm = reactive({
  filename: ''
})

// ---------- 自动保存相关 ----------
const autoSaveTimer = ref(null)

const subjectEnglishMap = {
  '物理': 'physics',
  '生物': 'biology',
  '化学': 'chemical',
  '安全常识': 'safety'
}
const modelEnglishMap = {
  '1': 'Qwen',
  '2': 'Gemini',
  '3': 'Doubao'
}
const modeStringMap = {
  '1': 'mode1',
  '2': 'mode2',
  '3': 'mode3',
  '4': 'mode4'
}

const getDefaultFilename = () => {
  const subjectName = subjects.value[form.subject]?.name || 'unknown'
  const subjectEng = subjectEnglishMap[subjectName] || 'unknown'
  const modelEng = modelEnglishMap[form.model] || 'unknown'
  const modeStr = modeStringMap[form.mode] || 'mode1'
  return `${subjectEng}_test_${modeStr}_${modelEng}`
}

const generateTimestampFilename = () => {
  const timestamp = new Date().toISOString().slice(0,19).replace(/:/g, '-').replace('T', '_')
  const randomSuffix = Math.random().toString(36).substring(2, 6)
  return `evaluation_auto_${timestamp}_${randomSuffix}`
}

const clearAutoSaveTimer = () => {
  if (autoSaveTimer.value) {
    clearTimeout(autoSaveTimer.value)
    autoSaveTimer.value = null
  }
}

const performAutoSave = async () => {
  if (saving.value || resultFile.value || taskStatus.value !== 'completed') return
  saving.value = true
  let filename = getDefaultFilename()
  try {
    const res = await axios.post('/api/save_result', {
      task_id: taskId.value,
      filename: filename
    })
    if (res.data.success) {
      resultFile.value = res.data.filename
      if (res.data.summary) summary.value = res.data.summary
      saveDialogVisible.value = false
      ElMessage.success(`评测结果已自动保存为：${res.data.filename}`)
    }
  } catch (err) {
    if (err.response?.status === 409) {
      try {
        filename = generateTimestampFilename()
        const retryRes = await axios.post('/api/save_result', {
          task_id: taskId.value,
          filename: filename
        })
        if (retryRes.data.success) {
          resultFile.value = retryRes.data.filename
          if (retryRes.data.summary) summary.value = retryRes.data.summary
          saveDialogVisible.value = false
          ElMessage.success(`评测结果已自动保存为：${retryRes.data.filename}`)
          return
        }
      } catch (retryErr) {
        ElMessage.error('自动保存失败，请手动保存')
      }
    } else {
      const errorMsg = err.response?.data?.error || '未知错误'
      ElMessage.error(`自动保存失败：${errorMsg}`)
    }
  } finally {
    saving.value = false
    clearAutoSaveTimer()
  }
}

const startAutoSaveTimer = () => {
  clearAutoSaveTimer()
  autoSaveTimer.value = setTimeout(() => { performAutoSave() }, 60000)
}

// ---------- 工具函数 ----------
const formatTime = (timestamp) => {
  const date = new Date(timestamp * 1000)
  return date.toLocaleTimeString()
}

const onDataSourceChange = () => {
  if (isRunning.value) clearLogs()
}

// ---------- 按钮文本 ----------
const btnStartText = computed(() => {
  if (isRunning.value && taskStatus.value === 'running') return '评测中...'
  if (isRunning.value && taskStatus.value === 'paused') return '已暂停'
  return '开始评测'
})

// ---------- 初始化数据 ----------
const fetchModels = async () => {
  try {
    const res = await axios.get('/api/models')
    models.value = res.data
    if (Object.keys(models.value).length > 0 && !form.model) {
      form.model = Object.keys(models.value)[0]
    }
  } catch (err) {
    ElMessage.error('获取模型列表失败，请确保后端服务已启动')
  }
}

const fetchSubjects = async () => {
  try {
    const res = await axios.get('/api/subjects')
    subjects.value = res.data
    if (Object.keys(subjects.value).length > 0 && !form.subject) {
      form.subject = Object.keys(subjects.value)[0]
    }
  } catch (err) {
    ElMessage.error('获取学科列表失败')
  }
}

// ---------- 控制方法 ----------
const pauseTask = async () => {
  try {
    await axios.post(`/api/task/${taskId.value}/pause`)
    pendingPause.value = true
    ElMessage.info('暂停指令已发送，将在当前题目完成后暂停')
  } catch (e) {
    ElMessage.error('暂停失败: ' + (e.response?.data?.error || e.message))
  }
}

const resumePending = ref(false)

// 【核心修改1】继续任务：不再手动修改状态，全部交给轮询同步
const resumeTask = async () => {
  if (resumePending.value) return
  if (!taskId.value) {
    ElMessage.error('任务ID丢失，无法继续')
    return
  }
  resumePending.value = true
  try {
    const res = await axios.post(`/api/task/${taskId.value}/resume`)
    // 确保轮询在运行（可能之前因暂停或其他原因停止了）
    if (!pollingTimer.value) {
      pollingTimer.value = setInterval(pollTaskStatus, 1000)
    }
    ElMessage.success(res.data.message || '任务已继续')
  } catch (e) {
    const errMsg = e.response?.data?.error || e.message
    ElMessage.error({ message: '继续失败: ' + errMsg, duration: 5000 })
    // 若返回特定错误，手动触发一次轮询获取最新状态
    if (errMsg.includes('控制已丢失') || e.response?.status === 400) {
      await pollTaskStatus()
    }
  } finally {
    resumePending.value = false
  }
}

const stopTask = async () => {
  try {
    await ElMessageBox.confirm('确定要强制结束当前任务吗？已完成的题目不会被保存。', '警告', { type: 'warning' })
    await axios.post(`/api/task/${taskId.value}/stop`)
    ElMessage.warning('停止指令已发送')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('强制结束失败: ' + (e.response?.data?.error || e.message))
  }
}

// ---------- 评测流程 ----------
const startEvaluation = async () => {
  if (!form.model || !form.subject || !form.mode) {
    ElMessage.warning('请完整填写配置')
    return
  }

  if (taskStatus.value === 'paused') {
    ElMessage.info('任务已暂停，请点击“继续”按钮恢复')
    return
  }

  if (!acquireTaskLock('evaluation')) {
    ElMessage.warning('有另一个评测任务正在进行中，请等待完成或取消后再试')
    return
  }

  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
  removeStoredTaskId()
  removeConfig()

  const payload = {
    data_source: form.dataSource,
    model: form.model,
    subject: form.subject,
    mode: form.mode,
    max_questions: form.quantityType === 'all' ? null : form.maxQuestions,
    custom_prompt: form.mode === '3' ? form.customPrompt : null
  }

  try {
    const res = await axios.post('/api/evaluate', payload)
    taskId.value = res.data.task_id
    setStoredTaskId(res.data.task_id)
    saveConfig()

    isRunning.value = true
    taskStatus.value = 'running'
    logs.value = []
    lastLogIndex.value = -1
    summary.value = null
    resultFile.value = ''
    pendingPause.value = false
    ElMessage.success('评测任务已启动')

    pollingTimer.value = setInterval(pollTaskStatus, 1000)
  } catch (err) {
    releaseTaskLock('evaluation')
    ElMessage.error('启动评测失败：' + (err.response?.data?.error || err.message))
  }
}

// 【核心修改2】轮询：严格根据后端状态更新 isRunning 和 pendingPause
const pollTaskStatus = async () => {
  if (!taskId.value) return
  try {
    const res = await axios.get(`/api/task/${taskId.value}/status`, {
      params: { last_index: lastLogIndex.value }
    })
    const data = res.data
    if (data.logs && data.logs.length > 0) {
      logs.value.push(...data.logs)
      lastLogIndex.value = data.total_logs - 1
      await nextTick()
      if (logContainer.value) {
        logContainer.value.scrollTop = logContainer.value.scrollHeight
      }
    }

    // ---------- 状态同步核心 ----------
    taskStatus.value = data.status

    if (data.status === 'running') {
      isRunning.value = true
      pendingPause.value = false   // 运行中，暂停标识清除
    } else if (data.status === 'paused') {
      isRunning.value = true       // 暂停也是任务进行中，所以 isRunning 仍为 true
      pendingPause.value = true    // 明确标记已暂停
    } else if (data.status === 'stopped') {
      isRunning.value = false
      if (pollingTimer.value) {
        clearInterval(pollingTimer.value)
        pollingTimer.value = null
      }
      releaseTaskLock('evaluation')
      removeStoredTaskId()
      removeConfig()
      ElMessage.warning('任务已强制结束')
      taskId.value = null
      pendingPause.value = false
    } else if (data.status === 'completed') {
      isRunning.value = false
      if (data.summary) summary.value = data.summary
      if (pollingTimer.value) {
        clearInterval(pollingTimer.value)
        pollingTimer.value = null
      }
      releaseTaskLock('evaluation')
      removeStoredTaskId()
      if (data.result_file) {
        resultFile.value = data.result_file
        ElMessage.success('评测完成！')
      } else {
        ElMessage.success('评测完成，请保存结果文件')
        saveForm.filename = getDefaultFilename()
        saveDialogVisible.value = true
        startAutoSaveTimer()
      }
      pendingPause.value = false
    } else if (data.status === 'error') {
      isRunning.value = false
      if (pollingTimer.value) {
        clearInterval(pollingTimer.value)
        pollingTimer.value = null
      }
      releaseTaskLock('evaluation')
      removeStoredTaskId()
      removeConfig()
      ElMessage.error('任务异常终止，请检查后端日志')
      pendingPause.value = false
    }
  } catch (err) {
    console.error('轮询失败，将在下一次重试', err)
  }
}

// 【核心修改3】恢复任务：同样统一状态管理
const restoreTask = async (storedTaskId) => {
  try {
    const res = await axios.get(`/api/task/${storedTaskId}/status`, {
      params: { last_index: -1 }
    })
    const data = res.data
    taskId.value = storedTaskId
    logs.value = data.logs || []
    lastLogIndex.value = data.total_logs ? data.total_logs - 1 : -1
    taskStatus.value = data.status

    const storedConfig = getStoredConfig()
    if (storedConfig) {
      if (storedConfig.dataSource) form.dataSource = storedConfig.dataSource
      if (storedConfig.model && Object.prototype.hasOwnProperty.call(models.value, storedConfig.model)) {
        form.model = storedConfig.model
      }
      if (storedConfig.subject && Object.prototype.hasOwnProperty.call(subjects.value, storedConfig.subject)) {
        form.subject = storedConfig.subject
      }
      if (storedConfig.mode) form.mode = storedConfig.mode
      if (storedConfig.customPrompt !== undefined) form.customPrompt = storedConfig.customPrompt
      if (storedConfig.quantityType) form.quantityType = storedConfig.quantityType
      if (storedConfig.maxQuestions !== undefined) form.maxQuestions = storedConfig.maxQuestions
    }

    // ---------- 根据恢复的状态设置辅助变量 ----------
    if (data.status === 'running') {
      isRunning.value = true
      pendingPause.value = false
      if (!acquireTaskLock('evaluation')) {
        ElMessage.warning('有其他任务正在运行，已终止恢复')
        removeStoredTaskId()
        removeConfig()
        isRunning.value = false
        return
      }
      pollingTimer.value = setInterval(pollTaskStatus, 1000)
    } else if (data.status === 'paused') {
      isRunning.value = true
      pendingPause.value = true   // 与暂停状态相符
      if (!acquireTaskLock('evaluation')) {
        removeStoredTaskId()
        removeConfig()
        isRunning.value = false
        return
      }
      pollingTimer.value = setInterval(pollTaskStatus, 1000)
    } else if (data.status === 'completed') {
      isRunning.value = false
      pendingPause.value = false
      if (data.summary) summary.value = data.summary
      if (data.result_file) resultFile.value = data.result_file
    } else if (data.status === 'error') {
      isRunning.value = false
      taskStatus.value = null
      summary.value = null
      logs.value = []
      lastLogIndex.value = -1
      removeStoredTaskId()
      removeConfig()
      releaseTaskLock('evaluation')
      pendingPause.value = false
      ElMessage.error('任务状态异常，已终止')
    } else {
      // stopped 等其他终态
      removeStoredTaskId()
      removeConfig()
      releaseTaskLock('evaluation')
      pendingPause.value = false
    }

    await nextTick()
    if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
  } catch (err) {
    removeStoredTaskId()
    removeConfig()
    releaseTaskLock('evaluation')
    console.warn('恢复任务失败，已清除旧任务ID', err)
  }
}

const clearLogs = () => {
  if (isRunning.value || taskStatus.value === 'paused') {
    return
  }
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
  logs.value = []
  lastLogIndex.value = -1
  summary.value = null
  taskStatus.value = null
  taskId.value = null
  isRunning.value = false
  pendingPause.value = false
  removeStoredTaskId()
  removeConfig()
  releaseTaskLock('evaluation')
}

const openSaveDialog = () => {
  if (taskStatus.value !== 'completed') {
    ElMessage.warning('评测尚未完成')
    return
  }
  if (resultFile.value) {
    ElMessage.info('结果已保存，可直接下载')
    return
  }
  saveForm.filename = getDefaultFilename()
  saveDialogVisible.value = true
  startAutoSaveTimer()
}

const confirmSave = async () => {
  clearAutoSaveTimer()
  const filename = saveForm.filename.trim()
  if (!filename) {
    ElMessage.warning('请输入文件名')
    return
  }
  saving.value = true
  try {
    const res = await axios.post('/api/save_result', {
      task_id: taskId.value,
      filename: filename
    })
    if (res.data.success) {
      resultFile.value = res.data.filename
      if (res.data.summary) summary.value = res.data.summary
      saveDialogVisible.value = false
      ElMessage.success('结果文件保存成功！')
    }
  } catch (err) {
    const errorMsg = err.response?.data?.error || '保存失败'
    if (err.response?.status === 409) {
      ElMessageBox.confirm('文件已存在，是否覆盖？', '提示', {
        confirmButtonText: '覆盖',
        cancelButtonText: '取消',
        type: 'warning'
      }).then(() => {
        ElMessage.info('请修改文件名后再保存')
      }).catch(() => {})
    } else {
      ElMessage.error(errorMsg)
    }
  } finally {
    saving.value = false
  }
}

const skipSave = () => {
  clearAutoSaveTimer()
  saveDialogVisible.value = false
  ElMessage.info('结果未保存，可稍后通过“保存结果”按钮操作')
}

// ---------- 生命周期 ----------
onMounted(async () => {
  await fetchModels()
  await fetchSubjects()

  const storedTaskId = getStoredTaskId()
  if (storedTaskId) {
    await restoreTask(storedTaskId)
  }
})

onBeforeUnmount(() => {
  if (pollingTimer.value) {
    clearInterval(pollingTimer.value)
    pollingTimer.value = null
  }
  clearAutoSaveTimer()
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