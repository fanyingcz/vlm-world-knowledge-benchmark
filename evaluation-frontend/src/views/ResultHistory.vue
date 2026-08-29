<template>
  <div>
    <el-card>
      <template #header>
        <span>评测历史记录</span>
      </template>

      <!-- 搜索栏 -->
      <el-form :inline="true" :model="searchForm" class="search-form">
        <el-form-item label="学科">
          <!-- 修改：将 value 从 opt.key 改为 opt.name，使筛选值与数据库一致 -->
          <el-select v-model="searchForm.subject" placeholder="全部" clearable @change="onSearch">
            <el-option
              v-for="opt in subjectOptions"
              :key="opt.key"
              :label="opt.name"
              :value="opt.name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="模型">
          <el-select v-model="searchForm.model_name" placeholder="全部" clearable @change="onSearch">
            <el-option
              v-for="(name, key) in modelOptions"
              :key="key"
              :label="name"
              :value="name"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="测试模式">
          <el-select v-model="searchForm.test_mode" placeholder="全部" clearable @change="onSearch">
            <el-option :value="1" label="直接提问" />
            <el-option :value="2" label="自身pre" />
            <el-option :value="3" label="自定义提示词" />
            <el-option :value="4" label="跨学科pre" />
          </el-select>
        </el-form-item>
        <el-form-item label="文件名">
          <el-input
            v-model="searchForm.filename"
            placeholder="输入结果文件名"
            clearable
            @clear="onSearch"
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSearch">搜索</el-button>
          <el-button @click="resetSearch">重置</el-button>
        </el-form-item>
      </el-form>

      <!-- 表格：排序事件触发后端请求 -->
      <el-table
        :data="records"
        border
        stripe
        @sort-change="handleSortChange"
      >
        <el-table-column
          prop="username"
          label="用户"
          width="120"
          sortable="custom"
          :sort-orders="sortOrderCycle"
        />
        <el-table-column
          prop="subject"
          label="学科"
          width="100"
          sortable="custom"
          :sort-orders="sortOrderCycle"
        />
        <el-table-column
          prop="model_name"
          label="模型"
          min-width="150"
          sortable="custom"
          :sort-orders="sortOrderCycle"
        />
        <el-table-column
          prop="test_mode"
          label="测试模式"
          width="100"
          sortable="custom"
          :sort-orders="sortOrderCycle"
          :formatter="modeFormatter"
        />
        <el-table-column
          prop="accuracy"
          label="加权准确率(%)"
          width="120"
          sortable="custom"
          :sort-orders="sortOrderCycle"
        >
          <template #default="{ row }">
            {{ row.accuracy ?? '-' }}
          </template>
        </el-table-column>
        <el-table-column
          prop="start_time"
          label="开始时间"
          width="170"
          sortable="custom"
          :sort-orders="sortOrderCycle"
        />
        <el-table-column
          prop="end_time"
          label="结束时间"
          width="170"
          sortable="custom"
          :sort-orders="sortOrderCycle"
        />
        <el-table-column prop="result_filename" label="结果文件" min-width="180" />
        <el-table-column v-if="isAdmin" label="操作" width="80">
          <template #default="{ row }">
            <el-popconfirm title="确定删除该记录？" @confirm="deleteRecord(row.id)">
              <template #reference>
                <el-button type="danger" size="small">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 10px; text-align: right;">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @size-change="fetchHistory"
          @current-change="fetchHistory"
        />
      </div>
    </el-card>

    <!-- ========== 图表区域 ========== -->
    <!-- 总体图表（固定） -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="12">
        <el-card>
          <template #header>总体表现 - 按测试模式</template>
          <div ref="chartOverallModeRef" style="height: 300px"></div>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card>
          <template #header>总体表现 - 按测试模型</template>
          <div ref="chartOverallModelRef" style="height: 300px"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 自由组合图表（两张） -->
    <el-row :gutter="20" style="margin-top: 20px">
      <el-col :span="12" v-for="(chart, index) in freeCharts" :key="index">
        <el-card>
          <template #header>
            <div style="display: flex; gap: 12px; align-items: center;">
              <span style="white-space: nowrap;">自由图表 {{ index + 1 }}</span>
              <el-select v-model="chart.subject" placeholder="学科" @change="() => renderFreeChart(index)" style="width: 140px;">
                <el-option
                  v-for="subj in availableSubjects"
                  :key="subj"
                  :label="subj"
                  :value="subj"
                />
              </el-select>
              <el-select v-model="chart.type" placeholder="维度" @change="() => renderFreeChart(index)" style="width: 140px;">
                <el-option label="测试模式" value="mode" />
                <el-option label="测试模型" value="model" />
              </el-select>
            </div>
          </template>
          <div
            :ref="(el) => setFreeChartRef(index, el)"
            style="height: 300px"
          ></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted, nextTick } from 'vue'
import axios from 'axios'
import { ElMessage } from 'element-plus'
import * as echarts from 'echarts'

// ---------- 排序配置 ----------
const sortOrderCycle = ['descending', 'ascending', null]  // 降序 → 升序 → 取消

// ---------- 搜索表单 ----------
const searchForm = reactive({
  subject: '',
  model_name: '',
  test_mode: null,
  filename: ''
})

const subjectOptions = ref([])
const modelOptions = ref({})

const fetchOptions = async () => {
  try {
    const [subRes, modRes] = await Promise.all([
      axios.get('/api/subjects'),
      axios.get('/api/models')
    ])
    const subs = []
    for (const [key, info] of Object.entries(subRes.data)) {
      subs.push({ key, name: info.name })
    }
    subjectOptions.value = subs
    modelOptions.value = modRes.data
  } catch (err) {
    console.error('获取筛选选项失败', err)
  }
}

// ---------- 表格数据 ----------
const records = ref([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

const modeFormatter = (row) => {
  const map = { 1: '直接提问', 2: '自身pre', 3: '自定义提示词', 4: '跨学科pre' }
  return map[row.test_mode] || row.test_mode
}

// 当前排序状态，会被发送给后端
const currentSort = reactive({
  prop: null,
  order: null
})

// 将前端表格列的 prop 映射为后端 sort_by 参数
const columnPropToSortKey = (prop) => {
  const map = {
    username: 'user',
    subject: 'subject',
    model_name: 'model',
    test_mode: 'test_mode',
    accuracy: 'accuracy',
    start_time: 'start_time',
    end_time: 'end_time',
    result_filename: 'filename'
  }
  return map[prop] || prop
}

// 处理表格排序变化
const handleSortChange = ({ prop, order }) => {
  currentSort.prop = prop
  currentSort.order = order
  currentPage.value = 1  // 排序后重置到第一页
  fetchHistory()
}

// 获取历史记录（含排序参数）
const fetchHistory = async () => {
  try {
    const params = {
      page: currentPage.value,
      limit: pageSize.value
    }
    if (searchForm.subject) params.subject = searchForm.subject
    if (searchForm.model_name) params.model_name = searchForm.model_name
    if (searchForm.test_mode != null) params.test_mode = searchForm.test_mode
    if (searchForm.filename) params.filename = searchForm.filename

    // 传递排序参数
    if (currentSort.prop && currentSort.order) {
      params.sort_by = columnPropToSortKey(currentSort.prop)
      params.sort_order = currentSort.order
    }

    const res = await axios.get('/api/evaluation-history', { params })
    records.value = res.data.records
    total.value = res.data.total
  } catch (err) {
    ElMessage.error('获取历史记录失败')
  }
}

const onSearch = () => {
  currentPage.value = 1
  fetchHistory()
}

const resetSearch = () => {
  searchForm.subject = ''
  searchForm.model_name = ''
  searchForm.test_mode = null
  searchForm.filename = ''
  currentPage.value = 1
  fetchHistory()
}

const isAdmin = computed(() => {
  try {
    const user = JSON.parse(localStorage.getItem('user') || '{}')
    return user.role === 'admin'
  } catch {
    return false
  }
})

const deleteRecord = async (id) => {
  try {
    await axios.delete(`/api/evaluation-history/${id}`)
    ElMessage.success('删除成功')
    fetchHistory()
  } catch (err) {
    ElMessage.error('删除失败')
  }
}

// ========== 图表逻辑 ==========
const chartOverallModeRef = ref(null)
const chartOverallModelRef = ref(null)

const freeCharts = reactive([
  { subject: '物理', type: 'mode' },
  { subject: '物理', type: 'model' }
])

const freeChartRefs = ref([])
const setFreeChartRef = (index, el) => {
  freeChartRefs.value[index] = el
}

const chartData = ref(null)

const availableSubjects = computed(() => {
  if (!chartData.value?.subjects) return []
  return Object.keys(chartData.value.subjects)
})

const chartInstances = []

const renderBarChart = (domElement, dataObj, title) => {
  if (!domElement || !dataObj) return

  const existing = echarts.getInstanceByDom(domElement)
  if (existing) existing.dispose()

  const chart = echarts.init(domElement)
  chartInstances.push(chart)

  const modeNames = { 1: '直接提问', 2: '自身pre', 3: '自定义提示词', 4: '跨学科pre' }
  const xData = Object.keys(dataObj).map(k => {
    return isNaN(Number(k)) ? k : (modeNames[Number(k)] || k)
  })
  const seriesData = Object.values(dataObj).map(v => parseFloat(v))

  chart.setOption({
    title: {
      text: title,
      left: 'center',
      textStyle: { fontSize: 14 }
    },
    tooltip: {
      trigger: 'axis',
      formatter: (params) => {
        return `${params[0].name}<br/>加权准确率：${params[0].value}%`
      }
    },
    xAxis: {
      type: 'category',
      data: xData,
      axisLabel: { rotate: 15 }
    },
    yAxis: {
      type: 'value',
      name: '加权准确率(%)',
      min: 0,
      max: 100
    },
    series: [{
      type: 'bar',
      data: seriesData,
      label: {
        show: true,
        position: 'top',
        formatter: '{c}%'
      },
      itemStyle: { color: '#409EFF' }
    }],
    grid: { top: 40, bottom: 60, left: 60, right: 20 }
  })

  const resizeHandler = () => chart.resize()
  window.addEventListener('resize', resizeHandler)
  chart._resizeHandler = resizeHandler
}

const renderFreeChart = (index) => {
  const el = freeChartRefs.value[index]
  if (!el || !chartData.value) return

  const cfg = freeCharts[index]
  const subjectData = chartData.value.subjects?.[cfg.subject]
  if (!subjectData) {
    renderBarChart(el, {}, `${cfg.subject}（暂无数据）`)
    return
  }

  const dataObj = subjectData[cfg.type]
  const typeLabel = cfg.type === 'mode' ? '按测试模式' : '按测试模型'
  renderBarChart(el, dataObj, `${cfg.subject} - ${typeLabel}`)
}

const fetchChartData = async () => {
  try {
    const res = await axios.get('/api/chart-data')
    chartData.value = res.data
    await nextTick()

    renderBarChart(chartOverallModeRef.value, res.data.overall_mode, '总体 - 按测试模式')
    renderBarChart(chartOverallModelRef.value, res.data.overall_model, '总体 - 按测试模型')

    const subs = Object.keys(res.data.subjects || {})
    freeCharts.forEach(chart => {
      if (!subs.includes(chart.subject) && subs.length) {
        chart.subject = subs[0]
      }
    })

    renderFreeChart(0)
    renderFreeChart(1)
  } catch (err) {
    ElMessage.error('获取图表数据失败')
  }
}

onUnmounted(() => {
  chartInstances.forEach(chart => {
    if (chart._resizeHandler) {
      window.removeEventListener('resize', chart._resizeHandler)
    }
    chart.dispose()
  })
})

onMounted(() => {
  fetchOptions()
  fetchHistory()
  fetchChartData()
})
</script>

<style scoped>
.search-form {
  margin-bottom: 15px;
}
</style>