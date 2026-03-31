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
        <el-table-column label="能力" width="120">
          <template #default="{row}">{{ capName(row.capability_id) }}</template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="90" />
        <el-table-column label="状态" width="90">
          <template #default="{row}">
            <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始时间" width="160">
          <template #default="{row}">{{ fmtTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="完成时间" width="160">
          <template #default="{row}">{{ fmtTime(row.finished_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="220">
          <template #default="{row}">
            <el-button link type="primary" @click="openLogs(row)">查看日志</el-button>
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

    <!-- Log drawer -->
    <el-drawer v-model="logDrawerVisible" :title="`训练日志 — Job #${selectedJob?.id}`" size="680px" destroy-on-close>
      <div style="display:flex;flex-direction:column;height:100%;gap:12px;">
        <!-- ECharts loss/accuracy chart -->
        <el-card shadow="never" style="flex-shrink:0;" v-if="chartData.loss.length">
          <v-chart :option="chartOption" style="height:200px;" autoresize />
        </el-card>
        <!-- Log terminal -->
        <div
          ref="logContainer"
          style="flex:1;background:#1e1e1e;color:#d4d4d4;font-family:monospace;font-size:13px;padding:12px;border-radius:4px;overflow-y:auto;white-space:pre-wrap;word-break:break-all;"
        >{{ logText }}</div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import {
  listCapabilities, listJobs, createJob,
  stopJob, pauseJob, resumeJob, getJobLogs, extractErrorMessage
} from '../api/index.js'

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer])

const loading = ref(false)
const capabilities = ref([])
const jobs = ref([])
const filterCapId = ref(null)

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

const logDrawerVisible = ref(false)
const selectedJob = ref(null)
const logText = ref('')
const logContainer = ref(null)
let wsConn = null

const chartData = ref({ epochs: [], loss: [], accuracy: [] })

const chartOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { data: ['损失值', '准确率'] },
  xAxis: { type: 'category', data: chartData.value.epochs, name: '轮次' },
  yAxis: { type: 'value' },
  series: [
    { name: '损失值', type: 'line', data: chartData.value.loss, smooth: true },
    { name: '准确率', type: 'line', data: chartData.value.accuracy, smooth: true },
  ]
}))

const capName = (id) => {
  const c = capabilities.value.find(c => c.id === id)
  return c ? (c.name_cn || c.name) : `#${id}`
}
const statusType = (s) => ({ running:'primary', done:'success', failed:'danger', paused:'warning', pending:'info' }[s] || 'info')
const fmtTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

const load = async () => {
  loading.value = true
  try {
    const params = filterCapId.value ? { capability_id: filterCapId.value } : {}
    const res = await listJobs(params)
    jobs.value = res.data
  } finally { loading.value = false }
}

const onCapabilityChange = () => {
  // Reset params when capability changes
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

  // Build hyperparams object
  const hyperparams = {}

  // Add non-null basic params
  if (newForm.value.params.epochs !== null) hyperparams.epochs = newForm.value.params.epochs
  if (newForm.value.params.batch !== null) hyperparams.batch = newForm.value.params.batch
  if (newForm.value.params.imgsz !== null) hyperparams.imgsz = newForm.value.params.imgsz
  if (newForm.value.params.lr0 !== null) hyperparams.lr0 = newForm.value.params.lr0
  if (newForm.value.params.device) hyperparams.device = newForm.value.params.device
  if (newForm.value.params.pretrained) hyperparams.pretrained = newForm.value.params.pretrained

  // Merge with custom params (custom params override)
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

const doPause = async (row) => { await pauseJob(row.id); await load() }
const doResume = async (row) => { await resumeJob(row.id); await load() }
const doStop = async (row) => { await stopJob(row.id); await load() }

const _parseEpoch = (line) => {
  const m = line.match(/\[EPOCH\s+(\d+)\/(\d+)\]\s+loss=([\d.]+)\s+accuracy=([\d.]+)/)
  if (m) return { epoch: m[1], loss: parseFloat(m[3]), accuracy: parseFloat(m[4]) }
  return null
}

const openLogs = async (row) => {
  selectedJob.value = row
  logText.value = ''
  chartData.value = { epochs: [], loss: [], accuracy: [] }
  logDrawerVisible.value = true

  // Load existing logs
  try {
    const res = await getJobLogs(row.id)
    logText.value = res.data
    for (const line of res.data.split('\n')) {
      const ep = _parseEpoch(line)
      if (ep) {
        chartData.value.epochs.push(ep.epoch)
        chartData.value.loss.push(ep.loss)
        chartData.value.accuracy.push(ep.accuracy)
      }
    }
  } catch (e) { /* ignore */ }

  if (['running', 'pending'].includes(row.status)) {
    _connectWs(row.id)
  }
}

const _connectWs = (jobId) => {
  if (wsConn) { wsConn.close(); wsConn = null }
  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  wsConn = new WebSocket(`${protocol}://${location.host}/ws/logs/${jobId}`)
  wsConn.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'done') { wsConn.close(); return }
      if (msg.type === 'log') {
        logText.value += msg.line
        const ep = _parseEpoch(msg.line)
        if (ep) {
          chartData.value.epochs.push(ep.epoch)
          chartData.value.loss.push(ep.loss)
          chartData.value.accuracy.push(ep.accuracy)
        }
      }
    } catch { logText.value += ev.data }
    nextTick(() => {
      if (logContainer.value) logContainer.value.scrollTop = logContainer.value.scrollHeight
    })
  }
  wsConn.onerror = () => { if (wsConn) wsConn.close() }
}

watch(logDrawerVisible, (v) => {
  if (!v && wsConn) { wsConn.close(); wsConn = null }
})

onMounted(async () => {
  const [c] = await Promise.all([listCapabilities()])
  capabilities.value = c.data
  await load()
})
</script>

<style scoped>
.json-error {
  border-color: #f56c6c !important;
}
</style>
