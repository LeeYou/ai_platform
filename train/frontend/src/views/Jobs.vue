<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span>训练任务</span>
            <el-select v-model="filterCapId" placeholder="按能力筛选" clearable size="small" style="width:160px;" @change="load">
              <el-option v-for="c in capabilities" :key="c.id" :label="c.name_cn||c.name" :value="c.id" />
            </el-select>
          </div>
          <el-button type="primary" :icon="Plus" @click="openNew">新建训练</el-button>
        </div>
      </template>

      <el-table :data="jobs" style="width:100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="能力" width="140">
          <template #default="{row}">
            <div>{{ capName(row.capability_id) }}</div>
            <div style="color:#909399;font-size:12px;">v{{ row.version }}</div>
          </template>
        </el-table-column>
        <el-table-column label="状态与进度" width="200">
          <template #default="{row}">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              <span v-if="jobProgress[row.id]" style="font-size:12px;color:#606266;">
                {{ jobProgress[row.id].current }}/{{ jobProgress[row.id].total }}
              </span>
            </div>
            <el-progress
              v-if="jobProgress[row.id] && jobProgress[row.id].total > 0"
              :percentage="Math.round((jobProgress[row.id].current / jobProgress[row.id].total) * 100)"
              :status="row.status === 'done' ? 'success' : (row.status === 'failed' ? 'exception' : undefined)"
              :stroke-width="6"
            />
          </template>
        </el-table-column>
        <el-table-column label="训练指标" width="180">
          <template #default="{row}">
            <div v-if="jobMetrics[row.id]" style="font-size:12px;">
              <div v-if="jobMetrics[row.id].loss !== null">
                <span style="color:#909399;">损失:</span> {{ jobMetrics[row.id].loss.toFixed(4) }}
              </div>
              <div v-if="jobMetrics[row.id].accuracy !== null">
                <span style="color:#909399;">精度:</span> {{ (jobMetrics[row.id].accuracy * 100).toFixed(2) }}%
              </div>
              <div v-if="jobMetrics[row.id].speed">
                <span style="color:#909399;">速度:</span> {{ jobMetrics[row.id].speed }}
              </div>
            </div>
            <span v-else style="color:#c0c4cc;font-size:12px;">-</span>
          </template>
        </el-table-column>
        <el-table-column label="时长" width="120">
          <template #default="{row}">
            <div style="font-size:12px;">
              <div v-if="row.started_at">
                <el-icon><Timer /></el-icon>
                {{ formatDuration(row) }}
              </div>
              <div v-if="jobMetrics[row.id]?.eta" style="color:#909399;">
                剩余: {{ jobMetrics[row.id].eta }}
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="时间信息" width="160">
          <template #default="{row}">
            <div style="font-size:12px;">
              <div v-if="row.started_at" style="color:#606266;">
                开始: {{ fmtTime(row.started_at, true) }}
              </div>
              <div v-if="row.finished_at" style="color:#909399;">
                结束: {{ fmtTime(row.finished_at, true) }}
              </div>
              <div v-if="!row.started_at" style="color:#c0c4cc;">
                等待中...
              </div>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{row}">
            <el-button link type="primary" @click="openMonitor(row)">监控</el-button>
            <el-button v-if="row.status==='running'" link type="warning" @click="doPause(row)">暂停</el-button>
            <el-button v-if="row.status==='paused'" link type="success" @click="doResume(row)">继续</el-button>
            <el-button v-if="['running','paused'].includes(row.status)" link type="danger" @click="doStop(row)">停止</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- New job dialog -->
    <el-dialog v-model="newDialogVisible" title="新建训练任务" width="720px" destroy-on-close>
      <el-form :model="newForm" label-width="120px" ref="newFormRef">
        <el-form-item label="AI 能力" prop="capability_id" :rules="[{required:true,message:'必填'}]">
          <el-select v-model="newForm.capability_id" placeholder="请选择" style="width:100%" @change="onCapabilityChange">
            <el-option v-for="c in capabilities" :key="c.id" :label="c.name_cn||c.name" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="版本号" prop="version" :rules="[{required:true,message:'必填'}]">
          <el-input v-model="newForm.version" placeholder="如 1.0.0" />
        </el-form-item>

        <el-divider content-position="left">训练参数 (可选，覆盖默认值)</el-divider>

        <el-form-item label="训练轮次" prop="epochs">
          <el-input-number v-model="newForm.params.epochs" :min="1" :max="1000" placeholder="如 100" style="width:100%" />
          <div style="color:#909399;font-size:12px;margin-top:4px;">训练的总轮次数</div>
        </el-form-item>

        <el-form-item label="批大小" prop="batch">
          <el-input-number v-model="newForm.params.batch" :min="1" :max="256" placeholder="如 16" style="width:100%" />
          <div style="color:#909399;font-size:12px;margin-top:4px;">每批次训练的样本数量</div>
        </el-form-item>

        <el-form-item label="图像尺寸" prop="imgsz">
          <el-input-number v-model="newForm.params.imgsz" :min="32" :max="2048" :step="32" placeholder="如 640" style="width:100%" />
          <div style="color:#909399;font-size:12px;margin-top:4px;">输入图像的尺寸（像素）</div>
        </el-form-item>

        <el-form-item label="学习率" prop="lr0">
          <el-input-number v-model="newForm.params.lr0" :min="0.00001" :max="1" :step="0.001" :precision="5" placeholder="如 0.01" style="width:100%" />
          <div style="color:#909399;font-size:12px;margin-top:4px;">初始学习率</div>
        </el-form-item>

        <el-form-item label="GPU 设备" prop="device">
          <el-input v-model="newForm.params.device" placeholder="如 0 或 cpu 或 auto" />
          <div style="color:#909399;font-size:12px;margin-top:4px;">GPU设备ID（0, 1等）或 cpu 或 auto</div>
        </el-form-item>

        <el-form-item label="基础模型" prop="pretrained">
          <el-input v-model="newForm.params.pretrained" placeholder="如 yolov8n.pt" />
          <div style="color:#909399;font-size:12px;margin-top:4px;">预训练权重文件（可选）</div>
        </el-form-item>

        <el-collapse v-model="advancedOpen" style="margin-bottom:16px;">
          <el-collapse-item title="高级参数（JSON格式）" name="advanced">
            <el-input
              v-model="newForm.customParams"
              type="textarea"
              :rows="6"
              placeholder='{"optimizer": "adam", "augment": true, ...}'
              :class="{ 'json-error': customParamsError }"
              @input="validateCustomParams"
            />
            <div v-if="customParamsError" style="color:#f56c6c;font-size:12px;margin-top:4px;">{{ customParamsError }}</div>
            <div style="color:#909399;font-size:12px;margin-top:4px;">
              这里的参数会与上面的参数合并，如果有冲突，以这里为准
            </div>
          </el-collapse-item>
        </el-collapse>

        <el-alert
          v-if="selectedCapability"
          title="能力默认参数"
          type="info"
          :closable="false"
          style="margin-bottom:16px;"
        >
          <pre style="margin:0;font-size:12px;">{{ JSON.stringify(selectedCapability.hyperparams, null, 2) }}</pre>
        </el-alert>
      </el-form>
      <template #footer>
        <el-button @click="newDialogVisible=false">取消</el-button>
        <el-button type="primary" @click="doCreate" :disabled="!!customParamsError">提交</el-button>
      </template>
    </el-dialog>

    <!-- Professional Training Monitor Drawer -->
    <el-drawer
      v-model="monitorDrawerVisible"
      :title="`训练监控 — ${selectedJob?.id ? `Job #${selectedJob.id}` : ''} — ${selectedJob ? capName(selectedJob.capability_id) : ''}`"
      size="85%"
      destroy-on-close
    >
      <div v-if="selectedJob" style="display:flex;flex-direction:column;height:100%;gap:16px;">
        <!-- Status Overview Cards -->
        <el-row :gutter="16">
          <el-col :span="6">
            <el-card shadow="hover" :body-style="{padding: '16px'}">
              <div style="display:flex;align-items:center;gap:12px;">
                <el-icon :size="32" :color="statusType(selectedJob.status) === 'success' ? '#67C23A' : '#409EFF'">
                  <CircleCheck v-if="selectedJob.status === 'done'" />
                  <CircleClose v-else-if="selectedJob.status === 'failed'" />
                  <Loading v-else-if="selectedJob.status === 'running'" />
                  <VideoPause v-else-if="selectedJob.status === 'paused'" />
                  <Clock v-else />
                </el-icon>
                <div style="flex:1;">
                  <div style="color:#909399;font-size:12px;">训练状态</div>
                  <div style="font-size:18px;font-weight:bold;">{{ statusLabel(selectedJob.status) }}</div>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" :body-style="{padding: '16px'}">
              <div style="display:flex;align-items:center;gap:12px;">
                <el-icon :size="32" color="#E6A23C"><Timer /></el-icon>
                <div style="flex:1;">
                  <div style="color:#909399;font-size:12px;">运行时长</div>
                  <div style="font-size:18px;font-weight:bold;">{{ formatDuration(selectedJob) }}</div>
                  <div v-if="monitorMetrics.eta" style="color:#909399;font-size:11px;">剩余: {{ monitorMetrics.eta }}</div>
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" :body-style="{padding: '16px'}">
              <div style="display:flex;align-items:center;gap:12px;">
                <el-icon :size="32" color="#67C23A"><Promotion /></el-icon>
                <div style="flex:1;">
                  <div style="color:#909399;font-size:12px;">训练进度</div>
                  <div style="font-size:18px;font-weight:bold;">
                    {{ monitorProgress.current }}/{{ monitorProgress.total }}
                  </div>
                  <el-progress
                    :percentage="monitorProgress.total > 0 ? Math.round((monitorProgress.current / monitorProgress.total) * 100) : 0"
                    :stroke-width="4"
                    :show-text="false"
                  />
                </div>
              </div>
            </el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover" :body-style="{padding: '16px'}">
              <div style="display:flex;align-items:center;gap:12px;">
                <el-icon :size="32" color="#409EFF"><DataLine /></el-icon>
                <div style="flex:1;">
                  <div style="color:#909399;font-size:12px;">训练速度</div>
                  <div style="font-size:14px;font-weight:bold;">{{ monitorMetrics.speed || '-' }}</div>
                  <div v-if="monitorMetrics.samplesPerSec" style="color:#909399;font-size:11px;">
                    {{ monitorMetrics.samplesPerSec }} samples/s
                  </div>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <!-- Training Metrics Charts -->
        <el-row :gutter="16" style="flex:1;min-height:0;">
          <el-col :span="12" style="height:100%;">
            <el-card shadow="never" style="height:100%;display:flex;flex-direction:column;">
              <template #header>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <span><el-icon><TrendCharts /></el-icon> 损失曲线</span>
                  <el-tag v-if="chartData.loss.length" size="small">
                    当前: {{ chartData.loss[chartData.loss.length - 1]?.toFixed(4) || '-' }}
                  </el-tag>
                </div>
              </template>
              <div style="flex:1;min-height:0;">
                <v-chart v-if="chartData.loss.length" :option="lossChartOption" style="height:100%;" autoresize />
                <el-empty v-else description="等待训练数据..." :image-size="80" />
              </div>
            </el-card>
          </el-col>
          <el-col :span="12" style="height:100%;">
            <el-card shadow="never" style="height:100%;display:flex;flex-direction:column;">
              <template #header>
                <div style="display:flex;justify-content:space-between;align-items:center;">
                  <span><el-icon><TrendCharts /></el-icon> 精度曲线</span>
                  <el-tag v-if="chartData.accuracy.length" size="small" type="success">
                    当前: {{ (chartData.accuracy[chartData.accuracy.length - 1] * 100)?.toFixed(2) || '-' }}%
                  </el-tag>
                </div>
              </template>
              <div style="flex:1;min-height:0;">
                <v-chart v-if="chartData.accuracy.length" :option="accuracyChartOption" style="height:100%;" autoresize />
                <el-empty v-else description="等待训练数据..." :image-size="80" />
              </div>
            </el-card>
          </el-col>
        </el-row>

        <!-- Training Hyperparameters & System Info -->
        <el-row :gutter="16">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><el-icon><Setting /></el-icon> 训练参数</template>
              <el-descriptions :column="2" size="small" border>
                <el-descriptions-item v-for="(value, key) in displayHyperparams" :key="key" :label="key">
                  {{ value }}
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><el-icon><Monitor /></el-icon> 系统信息</template>
              <el-descriptions :column="1" size="small" border>
                <el-descriptions-item label="任务ID">{{ selectedJob.id }}</el-descriptions-item>
                <el-descriptions-item label="版本">{{ selectedJob.version }}</el-descriptions-item>
                <el-descriptions-item label="创建时间">{{ fmtTime(selectedJob.created_at) }}</el-descriptions-item>
                <el-descriptions-item v-if="selectedJob.started_at" label="开始时间">
                  {{ fmtTime(selectedJob.started_at) }}
                </el-descriptions-item>
                <el-descriptions-item v-if="selectedJob.finished_at" label="完成时间">
                  {{ fmtTime(selectedJob.finished_at) }}
                </el-descriptions-item>
                <el-descriptions-item v-if="selectedJob.error_msg" label="错误信息">
                  <el-text type="danger">{{ selectedJob.error_msg }}</el-text>
                </el-descriptions-item>
              </el-descriptions>
            </el-card>
          </el-col>
        </el-row>

        <!-- Training Logs Terminal -->
        <el-card shadow="never" style="flex:1;min-height:200px;display:flex;flex-direction:column;">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
              <div style="display:flex;align-items:center;gap:8px;">
                <span><el-icon><Document /></el-icon> 训练日志</span>
                <el-tag size="small" type="info">
                  {{ displayedLogStats.total }} 行 ({{ displayedLogStats.epochLines }} epoch)
                </el-tag>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;">
                <el-radio-group v-model="logFilterMode" size="small">
                  <el-radio-button value="smart">智能显示</el-radio-button>
                  <el-radio-button value="epoch-only">仅Epoch</el-radio-button>
                  <el-radio-button value="full">全部</el-radio-button>
                </el-radio-group>
                <el-button-group size="small">
                  <el-button @click="autoScroll = !autoScroll" :type="autoScroll ? 'primary' : ''">
                    <el-icon><Bottom /></el-icon> 自动滚动
                  </el-button>
                  <el-button @click="clearLogs"><el-icon><Delete /></el-icon> 清空</el-button>
                </el-button-group>
              </div>
            </div>
          </template>
          <div
            ref="logContainer"
            style="flex:1;background:#1e1e1e;color:#d4d4d4;font-family:'Consolas','Monaco','Courier New',monospace;font-size:13px;padding:12px;border-radius:4px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;line-height:1.5;"
          >{{ displayedLogs || '等待日志输出...' }}</div>
        </el-card>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch, onUnmounted } from 'vue'
import {
  Plus, Timer, CircleCheck, CircleClose, Loading, VideoPause, Clock,
  Promotion, DataLine, TrendCharts, Setting, Monitor, Document, Bottom, Delete
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, TitleComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  listCapabilities, listJobs, createJob,
  stopJob, pauseJob, resumeJob, getJobLogs, extractErrorMessage, getAdminToken
} from '../api/index.js'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, TitleComponent, CanvasRenderer])

const loading = ref(false)
const capabilities = ref([])
const jobs = ref([])
const filterCapId = ref(null)

// Job progress and metrics tracking for table display
const jobProgress = ref({})  // { jobId: { current: 10, total: 100 } }
const jobMetrics = ref({})   // { jobId: { loss, accuracy, speed, eta } }

// Auto-refresh for running jobs
let autoRefreshTimer = null

const newDialogVisible = ref(false)
const newFormRef = ref(null)
const newForm = ref({
  capability_id: null,
  version: '1.0.0',
  params: {
    epochs: null,
    batch: null,
    imgsz: null,
    lr0: null,
    device: '',
    pretrained: ''
  },
  customParams: ''
})
const advancedOpen = ref([])
const customParamsError = ref('')
const selectedCapability = computed(() =>
  capabilities.value.find(c => c.id === newForm.value.capability_id)
)

const monitorDrawerVisible = ref(false)
const selectedJob = ref(null)
const logText = ref('')
const logContainer = ref(null)
const autoScroll = ref(true)
const logFilterMode = ref('smart') // 'full', 'smart', 'epoch-only'
let wsConn = null
let monitorRefreshTimer = null

const chartData = ref({ epochs: [], loss: [], accuracy: [] })

// Log filtering for performance
const logLines = ref([]) // Store all log lines
const MAX_HEAD_LINES = 200
const MAX_TAIL_LINES = 200

// Monitor-specific metrics
const monitorProgress = computed(() => {
  if (!selectedJob.value) return { current: 0, total: 0 }
  return jobProgress.value[selectedJob.value.id] || { current: 0, total: 0 }
})

const monitorMetrics = computed(() => {
  if (!selectedJob.value) return {}
  return jobMetrics.value[selectedJob.value.id] || {}
})

const displayHyperparams = computed(() => {
  if (!selectedJob.value?.hyperparams) return {}
  const params = typeof selectedJob.value.hyperparams === 'object'
    ? selectedJob.value.hyperparams
    : {}
  // Filter out empty values and format
  const filtered = {}
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== '') {
      filtered[key] = value
    }
  }
  return filtered
})

// Filtered logs for display - improves performance with large logs
const displayedLogs = computed(() => {
  if (logFilterMode.value === 'full') {
    return logText.value
  } else if (logFilterMode.value === 'epoch-only') {
    // Only show EPOCH lines for compact view
    return logLines.value
      .filter(line => line.includes('[EPOCH'))
      .join('\n')
  } else {
    // Smart mode: show first 200 + last 200 lines
    const lines = logLines.value
    if (lines.length <= MAX_HEAD_LINES + MAX_TAIL_LINES) {
      return lines.join('\n')
    }
    const head = lines.slice(0, MAX_HEAD_LINES)
    const tail = lines.slice(-MAX_TAIL_LINES)
    const omitted = lines.length - MAX_HEAD_LINES - MAX_TAIL_LINES
    return head.join('\n') +
           `\n\n... [已省略 ${omitted} 行中间日志以提升性能] ...\n\n` +
           tail.join('\n')
  }
})

const displayedLogStats = computed(() => {
  const total = logLines.value.length
  const epochLines = logLines.value.filter(line => line.includes('[EPOCH')).length
  return { total, epochLines }
})

// Enhanced chart options
const lossChartOption = computed(() => ({
  title: { show: false },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'cross' },
    formatter: (params) => {
      const point = params[0]
      return `Epoch ${point.axisValue}<br/>Loss: ${point.value?.toFixed(6) || '-'}`
    }
  },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category',
    data: chartData.value.epochs,
    name: 'Epoch',
    nameLocation: 'center',
    nameGap: 30
  },
  yAxis: {
    type: 'value',
    name: 'Loss',
    nameLocation: 'center',
    nameGap: 45,
    scale: true
  },
  series: [{
    name: '损失值',
    type: 'line',
    data: chartData.value.loss,
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { width: 2, color: '#409EFF' },
    itemStyle: { color: '#409EFF' },
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(64, 158, 255, 0.3)' },
          { offset: 1, color: 'rgba(64, 158, 255, 0.05)' }
        ]
      }
    }
  }]
}))

const accuracyChartOption = computed(() => ({
  title: { show: false },
  tooltip: {
    trigger: 'axis',
    axisPointer: { type: 'cross' },
    formatter: (params) => {
      const point = params[0]
      return `Epoch ${point.axisValue}<br/>Accuracy: ${(point.value * 100)?.toFixed(2) || '-'}%`
    }
  },
  grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
  xAxis: {
    type: 'category',
    data: chartData.value.epochs,
    name: 'Epoch',
    nameLocation: 'center',
    nameGap: 30
  },
  yAxis: {
    type: 'value',
    name: 'Accuracy',
    nameLocation: 'center',
    nameGap: 45,
    min: 0,
    max: 1,
    axisLabel: {
      formatter: (value) => `${(value * 100).toFixed(0)}%`
    }
  },
  series: [{
    name: '准确率',
    type: 'line',
    data: chartData.value.accuracy,
    smooth: true,
    symbol: 'circle',
    symbolSize: 6,
    lineStyle: { width: 2, color: '#67C23A' },
    itemStyle: { color: '#67C23A' },
    areaStyle: {
      color: {
        type: 'linear',
        x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: 'rgba(103, 194, 58, 0.3)' },
          { offset: 1, color: 'rgba(103, 194, 58, 0.05)' }
        ]
      }
    }
  }]
}))

const capName = (id) => {
  const c = capabilities.value.find(c => c.id === id)
  return c ? (c.name_cn || c.name) : `#${id}`
}

const statusType = (s) => ({
  running: 'primary',
  done: 'success',
  failed: 'danger',
  paused: 'warning',
  pending: 'info'
}[s] || 'info')

const statusLabel = (s) => ({
  running: '训练中',
  done: '已完成',
  failed: '失败',
  paused: '已暂停',
  pending: '等待中'
}[s] || s)

const fmtTime = (t, short = false) => {
  if (!t) return '-'
  // Parse the timestamp - handle both ISO strings and Unix timestamps
  let date
  if (typeof t === 'string') {
    // If timestamp doesn't include timezone info, treat as UTC
    if (!t.includes('Z') && !t.includes('+') && !t.includes('-', 10)) {
      date = new Date(t + 'Z')
    } else {
      date = new Date(t)
    }
  } else {
    date = new Date(t)
  }

  if (isNaN(date.getTime())) return '-'

  if (short) {
    return date.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    })
  }
  return date.toLocaleString('zh-CN')
}

const formatDuration = (job) => {
  if (!job.started_at) return '-'

  // Parse timestamps properly
  let start
  if (typeof job.started_at === 'string') {
    if (!job.started_at.includes('Z') && !job.started_at.includes('+') && !job.started_at.includes('-', 10)) {
      start = new Date(job.started_at + 'Z').getTime()
    } else {
      start = new Date(job.started_at).getTime()
    }
  } else {
    start = new Date(job.started_at).getTime()
  }

  let end
  if (job.finished_at) {
    if (typeof job.finished_at === 'string') {
      if (!job.finished_at.includes('Z') && !job.finished_at.includes('+') && !job.finished_at.includes('-', 10)) {
        end = new Date(job.finished_at + 'Z').getTime()
      } else {
        end = new Date(job.finished_at).getTime()
      }
    } else {
      end = new Date(job.finished_at).getTime()
    }
  } else {
    end = Date.now()
  }

  const duration = Math.floor((end - start) / 1000) // seconds

  const hours = Math.floor(duration / 3600)
  const minutes = Math.floor((duration % 3600) / 60)
  const seconds = duration % 60

  if (hours > 0) {
    return `${hours}h ${minutes}m ${seconds}s`
  } else if (minutes > 0) {
    return `${minutes}m ${seconds}s`
  } else {
    return `${seconds}s`
  }
}

const load = async () => {
  loading.value = true
  try {
    const params = filterCapId.value ? { capability_id: filterCapId.value } : {}
    const res = await listJobs(params)
    jobs.value = res.data

    // Update progress and metrics for each job
    for (const job of jobs.value) {
      await updateJobMetrics(job)
    }
  } finally {
    loading.value = false
  }
}

const updateJobMetrics = async (job) => {
  // Only fetch logs for running/done jobs to extract metrics
  if (!['running', 'done', 'paused'].includes(job.status)) return

  try {
    const res = await getJobLogs(job.id)
    const logs = res.data || ''

    // Parse metrics from logs
    const lines = logs.split('\n')
    let currentEpoch = 0
    let totalEpochs = 0
    let lastLoss = null
    let lastAccuracy = null
    let epochStartTime = null
    let totalTime = 0
    let epochCount = 0

    for (const line of lines) {
      // Parse epoch progress: [EPOCH 10/100]
      const epochMatch = line.match(/\[EPOCH\s+(\d+)\/(\d+)\]/)
      if (epochMatch) {
        currentEpoch = parseInt(epochMatch[1])
        totalEpochs = parseInt(epochMatch[2])
      }

      // Parse loss and mAP50/accuracy (YOLO outputs mAP50, other models may output accuracy)
      const metricsMatch = line.match(/loss=([\d.]+)\s+(?:mAP50|accuracy|mAP)=([\d.]+)/)
      if (metricsMatch) {
        lastLoss = parseFloat(metricsMatch[1])
        lastAccuracy = parseFloat(metricsMatch[2])
      }

      // Parse time per epoch
      const timeMatch = line.match(/(\d+\.?\d*)s\/epoch/)
      if (timeMatch) {
        const timePerEpoch = parseFloat(timeMatch[1])
        totalTime += timePerEpoch
        epochCount++
      }
    }

    // Calculate metrics
    const avgTimePerEpoch = epochCount > 0 ? totalTime / epochCount : 0
    const remainingEpochs = totalEpochs - currentEpoch
    const etaSeconds = Math.floor(avgTimePerEpoch * remainingEpochs)

    jobProgress.value[job.id] = {
      current: currentEpoch,
      total: totalEpochs
    }

    jobMetrics.value[job.id] = {
      loss: lastLoss,
      accuracy: lastAccuracy,
      speed: avgTimePerEpoch > 0 ? `${avgTimePerEpoch.toFixed(1)}s/epoch` : null,
      samplesPerSec: null, // Could be calculated if batch size is known
      eta: etaSeconds > 0 ? formatSeconds(etaSeconds) : null
    }
  } catch (e) {
    // Silently ignore errors in metrics fetching
  }
}

const formatSeconds = (seconds) => {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60

  if (h > 0) return `${h}h${m}m`
  if (m > 0) return `${m}m${s}s`
  return `${s}s`
}

const startAutoRefresh = () => {
  stopAutoRefresh()
  autoRefreshTimer = setInterval(async () => {
    const hasRunningJobs = jobs.value.some(j => j.status === 'running')
    if (hasRunningJobs) {
      await load()
    }
  }, 10000) // Refresh every 10 seconds
}

const stopAutoRefresh = () => {
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer)
    autoRefreshTimer = null
  }
}

const onCapabilityChange = () => {
  newForm.value.params = {
    epochs: null,
    batch: null,
    imgsz: null,
    lr0: null,
    device: '',
    pretrained: ''
  }
  newForm.value.customParams = ''
  customParamsError.value = ''
}

const validateCustomParams = () => {
  if (!newForm.value.customParams.trim()) {
    customParamsError.value = ''
    return
  }
  try {
    JSON.parse(newForm.value.customParams)
    customParamsError.value = ''
  } catch (e) {
    customParamsError.value = e.message
  }
}

const openNew = () => {
  newForm.value = {
    capability_id: null,
    version: '1.0.0',
    params: {
      epochs: null,
      batch: null,
      imgsz: null,
      lr0: null,
      device: '',
      pretrained: ''
    },
    customParams: ''
  }
  advancedOpen.value = []
  customParamsError.value = ''
  newDialogVisible.value = true
}

const doCreate = async () => {
  if (!newFormRef.value) {
    ElMessage.warning('请填写必填项')
    return
  }

  try {
    await newFormRef.value.validate()
  } catch {
    ElMessage.warning('请填写必填项')
    return
  }

  if (customParamsError.value) {
    ElMessage.warning('高级参数JSON格式错误')
    return
  }

  const hyperparams = {}

  if (newForm.value.params.epochs !== null) hyperparams.epochs = newForm.value.params.epochs
  if (newForm.value.params.batch !== null) hyperparams.batch_size = newForm.value.params.batch
  if (newForm.value.params.imgsz !== null) hyperparams.imgsz = newForm.value.params.imgsz
  if (newForm.value.params.lr0 !== null) hyperparams.lr0 = newForm.value.params.lr0
  if (newForm.value.params.device) hyperparams.device = newForm.value.params.device
  if (newForm.value.params.pretrained) hyperparams.pretrained = newForm.value.params.pretrained

  if (newForm.value.customParams.trim()) {
    try {
      const custom = JSON.parse(newForm.value.customParams)
      Object.assign(hyperparams, custom)
    } catch (e) {
      ElMessage.error('高级参数JSON格式错误: ' + e.message)
      return
    }
  }

  const payload = {
    capability_id: newForm.value.capability_id,
    version: newForm.value.version,
    hyperparams: Object.keys(hyperparams).length > 0 ? JSON.stringify(hyperparams) : null
  }

  try {
    await createJob(payload)
    ElMessage.success('训练任务已提交')
    newDialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error('创建失败：' + extractErrorMessage(e))
  }
}

const doPause = async (row) => {
  await pauseJob(row.id)
  ElMessage.success('已暂停')
  await load()
}

const doResume = async (row) => {
  await resumeJob(row.id)
  ElMessage.success('已继续')
  await load()
}

const doStop = async (row) => {
  await stopJob(row.id)
  ElMessage.success('已停止')
  await load()
}

const _parseEpoch = (line) => {
  // Match both accuracy and mAP50 formats
  const m = line.match(/\[EPOCH\s+(\d+)\/(\d+)\]\s+loss=([\d.]+)\s+(?:mAP50|accuracy|mAP)=([\d.]+)/)
  if (m) return { epoch: parseInt(m[1]), loss: parseFloat(m[3]), accuracy: parseFloat(m[4]) }
  return null
}

const openMonitor = async (row) => {
  selectedJob.value = row
  logText.value = ''
  logLines.value = []
  chartData.value = { epochs: [], loss: [], accuracy: [] }
  monitorDrawerVisible.value = true

  // Load existing logs
  try {
    const res = await getJobLogs(row.id)
    logText.value = res.data
    logLines.value = res.data.split('\n').filter(line => line.trim())
    for (const line of logLines.value) {
      const ep = _parseEpoch(line)
      if (ep) {
        chartData.value.epochs.push(ep.epoch)
        chartData.value.loss.push(ep.loss)
        chartData.value.accuracy.push(ep.accuracy)
      }
    }
  } catch (e) { /* ignore */ }

  // Update metrics immediately
  await updateJobMetrics(row)

  // Start real-time updates for running/pending jobs
  if (['running', 'pending'].includes(row.status)) {
    _connectWs(row.id)
    _startMonitorRefresh()
  }
}

const clearLogs = () => {
  logText.value = ''
  logLines.value = []
}

const _startMonitorRefresh = () => {
  _stopMonitorRefresh()
  monitorRefreshTimer = setInterval(async () => {
    if (!selectedJob.value || !monitorDrawerVisible.value) {
      _stopMonitorRefresh()
      return
    }

    // Refresh job data
    try {
      const res = await listJobs()
      const updated = res.data.find(j => j.id === selectedJob.value.id)
      if (updated) {
        selectedJob.value = updated
        await updateJobMetrics(updated)

        // If job is no longer running, stop refresh and close WebSocket
        if (!['running', 'pending'].includes(updated.status)) {
          _stopMonitorRefresh()
          if (wsConn) {
            wsConn.close()
            wsConn = null
          }
        }
      }
    } catch (e) {
      console.error('Failed to refresh monitor data:', e)
    }
  }, 3000) // Refresh every 3 seconds for responsive UI
}

const _stopMonitorRefresh = () => {
  if (monitorRefreshTimer) {
    clearInterval(monitorRefreshTimer)
    monitorRefreshTimer = null
  }
}

const _connectWs = (jobId) => {
  if (wsConn) { wsConn.close(); wsConn = null }
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const token = getAdminToken()
  const suffix = token ? `?token=${encodeURIComponent(token)}` : ''
  wsConn = new WebSocket(`${protocol}://${location.host}/ws/logs/${jobId}${suffix}`)

  wsConn.onopen = () => {
    console.log('WebSocket connected for job', jobId)
  }

  wsConn.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'done') {
        console.log('Training completed, closing WebSocket')
        wsConn.close()
        load() // Refresh job list
        return
      }
      if (msg.type === 'log') {
        // Append to full log text for full mode
        logText.value += msg.line

        // Append to log lines array for efficient filtering
        const newLine = msg.line.trim()
        if (newLine) {
          logLines.value.push(newLine)
        }

        // Parse and update metrics in real-time
        const ep = _parseEpoch(msg.line)
        if (ep && selectedJob.value) {
          // Update chart data
          chartData.value.epochs.push(ep.epoch)
          chartData.value.loss.push(ep.loss)
          chartData.value.accuracy.push(ep.accuracy)

          // Update jobProgress immediately for responsive UI
          const epochMatch = msg.line.match(/\[EPOCH\s+(\d+)\/(\d+)\]/)
          if (epochMatch) {
            const currentEpoch = parseInt(epochMatch[1])
            const totalEpochs = parseInt(epochMatch[2])
            jobProgress.value[selectedJob.value.id] = {
              current: currentEpoch,
              total: totalEpochs
            }
          }

          // Update jobMetrics immediately with latest values
          jobMetrics.value[selectedJob.value.id] = {
            loss: ep.loss,
            accuracy: ep.accuracy,
            speed: jobMetrics.value[selectedJob.value.id]?.speed || null,
            eta: jobMetrics.value[selectedJob.value.id]?.eta || null
          }
        }

        // Auto-scroll to bottom if enabled (debounced for performance)
        if (autoScroll.value) {
          nextTick(() => {
            if (logContainer.value) {
              logContainer.value.scrollTop = logContainer.value.scrollHeight
            }
          })
        }
      }
    } catch (e) {
      // If not JSON, append as plain text
      logText.value += ev.data
      const newLine = ev.data.trim()
      if (newLine) {
        logLines.value.push(newLine)
      }

      // Auto-scroll for plain text too
      if (autoScroll.value) {
        nextTick(() => {
          if (logContainer.value) {
            logContainer.value.scrollTop = logContainer.value.scrollHeight
          }
        })
      }
    }
  }

  wsConn.onerror = (err) => {
    console.error('WebSocket error:', err)
    if (wsConn) wsConn.close()
  }

  wsConn.onclose = () => {
    console.log('WebSocket closed for job', jobId)
  }
}

watch(monitorDrawerVisible, (v) => {
  if (!v) {
    _stopMonitorRefresh()
    if (wsConn) {
      wsConn.close()
      wsConn = null
    }
  }
})

onMounted(async () => {
  const [c] = await Promise.all([listCapabilities()])
  capabilities.value = c.data
  await load()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
  _stopMonitorRefresh()
  if (wsConn) wsConn.close()
})
</script>

<style scoped>
.json-error {
  border-color: #f56c6c !important;
}
</style>
