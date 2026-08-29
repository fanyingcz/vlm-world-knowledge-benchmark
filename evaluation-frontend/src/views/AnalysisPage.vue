<template>
  <div class="analysis-page">
    <el-card>
      <el-form label-width="120px">
        <el-form-item label="分析模式">
          <el-radio-group v-model="analysisMode">
            <el-radio value="cross-model">多模型同一学科</el-radio>
            <el-radio value="cross-subject">单一模型多学科</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="上传结果文件">
          <el-upload
            ref="uploadRef"
            v-model:file-list="fileList"
            :auto-upload="false"
            :limit="20"
            accept=".json"
            multiple
            drag
          >
            <el-icon><UploadFilled /></el-icon>
            <div>将 JSON 文件拖到此处或点击上传</div>
            <template #tip>
              <div class="el-upload__tip">仅支持 .json 文件，可上传多个</div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="startAnalysis" :loading="analyzing">开始分析</el-button>
          <el-button @click="clearFiles">清空文件</el-button>
          <el-button v-if="result" @click="saveResult">保存结果</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 多模型同一学科分析结果（左右布局） -->
    <template v-if="result && analysisMode === 'cross-model'">
      <el-row :gutter="20" class="result-row">
        <!-- 左侧：表格区域 -->
        <el-col :xs="24" :md="14">
          <el-card class="result-card">
            <template #header><span>分析结果（多模型同一学科）</span></template>

            <div class="sub-title">各模型各模式表现</div>
            <el-table :data="result.summaries" border stripe style="width:100%">
              <el-table-column prop="model" label="模型" width="120" />
              <el-table-column prop="test_mode" label="测试模式" width="100" />
              <el-table-column prop="accuracy_percent" label="正确率(%)" />
              <el-table-column prop="weighted_acc" label="加权正确率" />
            </el-table>

            <div class="sub-title">模式总体准确率</div>
            <el-table :data="result.mode_overall_accuracy" border stripe style="width:100%">
              <el-table-column prop="mode" label="测试模式" />
              <el-table-column prop="total" label="总题数" />
              <el-table-column prop="correct" label="正确数" />
              <el-table-column prop="accuracy" label="正确率(%)" />
            </el-table>

            <div class="sub-title">模型总体准确率</div>
            <el-table :data="result.model_overall_accuracy" border stripe style="width:100%">
              <el-table-column prop="model" label="模型" />
              <el-table-column prop="total" label="总题数" />
              <el-table-column prop="correct" label="正确数" />
              <el-table-column prop="accuracy" label="正确率(%)" />
            </el-table>

            <div class="sub-title">各问题详细统计（按正确率升序）</div>
            <el-table :data="result.questions" border stripe max-height="400" style="width:100%">
              <el-table-column prop="question_id" label="问题ID" width="140" fixed />
              <el-table-column prop="question_type" label="题型" width="100" />
              <el-table-column prop="accuracy" label="总正确率(%)" width="110" sortable />
              <el-table-column
                v-for="col in result.all_columns"
                :key="col"
                :label="col"
                width="90"
              >
                <template #default="{ row }">
                  <el-tag v-if="row.details[col] === true" type="success" size="small">✓</el-tag>
                  <el-tag v-else-if="row.details[col] === false" type="danger" size="small">✗</el-tag>
                  <span v-else style="color: #ccc">-</span>
                </template>
              </el-table-column>
            </el-table>
          </el-card>
        </el-col>

        <!-- 右侧：图表区域 -->
        <el-col :xs="24" :md="10">
          <el-card class="chart-card">
            <template #header><span>📊 模型准确率对比</span></template>
            <div ref="modelAccuracyChartRef" class="chart-container"></div>
          </el-card>
          <el-card class="chart-card" style="margin-top: 20px;">
            <template #header><span>📊 测试模式准确率对比</span></template>
            <div ref="modeAccuracyChartRef" class="chart-container"></div>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- 单一模型多学科分析结果（左右布局） -->
    <template v-if="result && analysisMode === 'cross-subject'">
      <el-row :gutter="20" class="result-row">
        <!-- 左侧：表格区域 -->
        <el-col :xs="24" :md="14">
          <el-card class="result-card">
            <template #header><span>分析结果（单一模型多学科）</span></template>

            <el-descriptions :column="3" border>
              <el-descriptions-item label="模型">{{ result.model }}</el-descriptions-item>
              <el-descriptions-item label="总题数">{{ result.total }}</el-descriptions-item>
              <el-descriptions-item label="总体正确率">{{ result.overall_accuracy }}%</el-descriptions-item>
              <el-descriptions-item label="总体加权正确率">{{ (result.overall_weighted_acc * 100).toFixed(2) }}%</el-descriptions-item>
            </el-descriptions>

            <div class="sub-title">模型在各测试模式下的表现</div>
            <el-table :data="result.mode_performance" border stripe style="width:100%">
              <el-table-column prop="test_mode" label="测试模式" width="100" />
              <el-table-column prop="total_questions" label="总题数" width="100" />
              <el-table-column prop="correct_count" label="正确数" width="100" />
              <el-table-column prop="accuracy_percent" label="正确率(%)" width="120" />
              <el-table-column prop="weighted_acc" label="加权正确率" width="120">
                <template #default="{ row }">
                  {{ (row.weighted_acc * 100).toFixed(2) }}%
                </template>
              </el-table-column>
            </el-table>

            <div class="sub-title">模型在各学科上的表现</div>
            <el-table :data="result.subject_performance" border stripe style="width:100%">
              <el-table-column prop="subject" label="学科" width="150" />
              <el-table-column prop="total_questions" label="总题数" width="100" />
              <el-table-column prop="correct_count" label="正确数" width="100" />
              <el-table-column prop="accuracy_percent" label="正确率(%)" width="120" />
              <el-table-column prop="weighted_acc" label="加权正确率" width="120">
                <template #default="{ row }">
                  {{ (row.weighted_acc * 100).toFixed(2) }}%
                </template>
              </el-table-column>
            </el-table>

            <div class="sub-title">各题型准确率</div>
            <el-table :data="result.type_accuracy" border stripe style="width:100%">
              <el-table-column prop="type" label="题型" />
              <el-table-column prop="total" label="题目数" />
              <el-table-column prop="correct" label="正确数" />
              <el-table-column prop="accuracy" label="正确率(%)" />
            </el-table>
          </el-card>
        </el-col>

        <!-- 右侧：图表区域 -->
        <el-col :xs="24" :md="10">
          <el-card class="chart-card">
            <template #header><span>📊 各测试模式正确率对比</span></template>
            <div ref="subjectModeChartRef" class="chart-container"></div>
          </el-card>
          <el-card class="chart-card" style="margin-top: 20px;">
            <template #header><span>📊 各学科正确率对比</span></template>
            <div ref="subjectSubjectChartRef" class="chart-container"></div>
          </el-card>
          <el-card class="chart-card" style="margin-top: 20px;">
            <template #header><span>📊 各题型正确率对比</span></template>
            <div ref="subjectTypeChartRef" class="chart-container"></div>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import axios from 'axios'
import * as echarts from 'echarts'

// 分析模式与文件
const analysisMode = ref('cross-model')
const fileList = ref([])
const analyzing = ref(false)
const result = ref(null)

// 图表容器引用
const modelAccuracyChartRef = ref(null)
const modeAccuracyChartRef = ref(null)
const subjectModeChartRef = ref(null)
const subjectSubjectChartRef = ref(null)
const subjectTypeChartRef = ref(null)

// 存储 ECharts 实例
let modelAccuracyChart = null
let modeAccuracyChart = null
let subjectModeChart = null
let subjectSubjectChart = null
let subjectTypeChart = null

// 销毁所有图表实例
const disposeCharts = () => {
  if (modelAccuracyChart) { modelAccuracyChart.dispose(); modelAccuracyChart = null }
  if (modeAccuracyChart) { modeAccuracyChart.dispose(); modeAccuracyChart = null }
  if (subjectModeChart) { subjectModeChart.dispose(); subjectModeChart = null }
  if (subjectSubjectChart) { subjectSubjectChart.dispose(); subjectSubjectChart = null }
  if (subjectTypeChart) { subjectTypeChart.dispose(); subjectTypeChart = null }
}

// 绘制多模型分析图表
const drawCrossModelCharts = () => {
  if (!result.value) return

  // 模型准确率柱状图
  if (modelAccuracyChartRef.value) {
    if (modelAccuracyChart) modelAccuracyChart.dispose()
    modelAccuracyChart = echarts.init(modelAccuracyChartRef.value)
    const modelData = result.value.model_overall_accuracy || []
    const categories = modelData.map(item => item.model)
    const accuracyData = modelData.map(item => item.accuracy)
    modelAccuracyChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: categories, axisLabel: { rotate: 15 } },
      yAxis: { type: 'value', name: '正确率 (%)', max: 100 },
      series: [{
        name: '正确率 (%)',
        type: 'bar',
        data: accuracyData,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#5470c6' },
        label: { show: true, position: 'top', formatter: '{c}%' }
      }]
    })
  }

  // 模式准确率柱状图
  if (modeAccuracyChartRef.value) {
    if (modeAccuracyChart) modeAccuracyChart.dispose()
    modeAccuracyChart = echarts.init(modeAccuracyChartRef.value)
    const modeData = result.value.mode_overall_accuracy || []
    const categories = modeData.map(item => `模式 ${item.mode}`)
    const accuracyData = modeData.map(item => item.accuracy)
    modeAccuracyChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', name: '正确率 (%)', max: 100 },
      series: [{
        name: '正确率 (%)',
        type: 'bar',
        data: accuracyData,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#91cc75' },
        label: { show: true, position: 'top', formatter: '{c}%' }
      }]
    })
  }
}

// 绘制单一模型多学科分析图表
const drawCrossSubjectCharts = () => {
  if (!result.value) return

  // 各模式正确率柱状图
  if (subjectModeChartRef.value) {
    if (subjectModeChart) subjectModeChart.dispose()
    subjectModeChart = echarts.init(subjectModeChartRef.value)
    const modeData = result.value.mode_performance || []
    const categories = modeData.map(item => `模式 ${item.test_mode}`)
    const accuracyData = modeData.map(item => item.accuracy_percent)
    subjectModeChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', name: '正确率 (%)', max: 100 },
      series: [{
        name: '正确率 (%)',
        type: 'bar',
        data: accuracyData,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#fac858' },
        label: { show: true, position: 'top', formatter: '{c}%' }
      }]
    })
  }

  // 各学科正确率柱状图
  if (subjectSubjectChartRef.value) {
    if (subjectSubjectChart) subjectSubjectChart.dispose()
    subjectSubjectChart = echarts.init(subjectSubjectChartRef.value)
    const subjectData = result.value.subject_performance || []
    const categories = subjectData.map(item => item.subject)
    const accuracyData = subjectData.map(item => item.accuracy_percent)
    subjectSubjectChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: categories, axisLabel: { rotate: 15 } },
      yAxis: { type: 'value', name: '正确率 (%)', max: 100 },
      series: [{
        name: '正确率 (%)',
        type: 'bar',
        data: accuracyData,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#ee6666' },
        label: { show: true, position: 'top', formatter: '{c}%' }
      }]
    })
  }

  // 各题型正确率柱状图
  if (subjectTypeChartRef.value) {
    if (subjectTypeChart) subjectTypeChart.dispose()
    subjectTypeChart = echarts.init(subjectTypeChartRef.value)
    const typeData = result.value.type_accuracy || []
    const categories = typeData.map(item => item.type)
    const accuracyData = typeData.map(item => item.accuracy)
    subjectTypeChart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
      xAxis: { type: 'category', data: categories },
      yAxis: { type: 'value', name: '正确率 (%)', max: 100 },
      series: [{
        name: '正确率 (%)',
        type: 'bar',
        data: accuracyData,
        itemStyle: { borderRadius: [4, 4, 0, 0], color: '#73c0de' },
        label: { show: true, position: 'top', formatter: '{c}%' }
      }]
    })
  }
}

// 监听 result 变化，绘制图表
watch(result, async (newVal) => {
  if (!newVal) return
  await nextTick()
  if (analysisMode.value === 'cross-model') {
    drawCrossModelCharts()
  } else if (analysisMode.value === 'cross-subject') {
    drawCrossSubjectCharts()
  }
})

// 监听分析模式变化，重新绘制（确保 DOM 更新）
watch(analysisMode, () => {
  if (result.value) {
    nextTick(() => {
      if (analysisMode.value === 'cross-model') {
        drawCrossModelCharts()
      } else if (analysisMode.value === 'cross-subject') {
        drawCrossSubjectCharts()
      }
    })
  }
})

// 开始分析
const startAnalysis = async () => {
  if (fileList.value.length === 0) {
    ElMessage.warning('请至少上传一个 JSON 文件')
    return
  }
  const formData = new FormData()
  fileList.value.forEach(file => formData.append('files', file.raw))
  formData.append('analysis_type', analysisMode.value)

  analyzing.value = true
  try {
    const res = await axios.post('/api/analyze', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    if (res.data.success) {
      result.value = res.data.data
      ElMessage.success('分析完成')
    } else {
      ElMessage.error(res.data.error || '分析失败')
    }
  } catch (err) {
    ElMessage.error('请求失败：' + (err.response?.data?.error || err.message))
  } finally {
    analyzing.value = false
  }
}

const clearFiles = () => {
  fileList.value = []
}

const saveResult = async () => {
  try {
    const { value: filename } = await ElMessageBox.prompt('请输入保存的文件名（不含扩展名）', '保存结果', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /^[a-zA-Z0-9_\-\u4e00-\u9fa5]+$/,
      inputErrorMessage: '文件名需为合法字符串'
    })
    if (!filename) return
    const blob = new Blob([JSON.stringify(result.value, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${filename}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('结果已保存')
  } catch { /* 用户取消 */ }
}

// 窗口大小变化时自适应图表
const handleResize = () => {
  if (modelAccuracyChart) modelAccuracyChart.resize()
  if (modeAccuracyChart) modeAccuracyChart.resize()
  if (subjectModeChart) subjectModeChart.resize()
  if (subjectSubjectChart) subjectSubjectChart.resize()
  if (subjectTypeChart) subjectTypeChart.resize()
}
window.addEventListener('resize', handleResize)

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  disposeCharts()
})
</script>

<style scoped>
.analysis-page {
  max-width: 1600px;
  margin: 0 auto;
  padding: 0 10px;
}

.result-row {
  margin-top: 20px;
}

.sub-title {
  font-weight: bold;
  margin-bottom: 10px;
  margin-top: 20px;
}

.result-card {
  margin-bottom: 20px;
  width: 100%;
}

.chart-card {
  margin-bottom: 0;
  width: 100%;
}

.chart-container {
  width: 100%;
  height: 320px;
}

/* 响应式：小屏幕时图表高度适当减小 */
@media (max-width: 768px) {
  .chart-container {
    height: 260px;
  }
}
</style>