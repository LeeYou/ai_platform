<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <span style="font-size:16px;font-weight:bold;">🔨 新建编译任务</span>
      </template>

      <el-alert
        v-if="capabilityDiagnostics"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom:16px;"
      >
        <template #title>当前没有可编译能力，请先排查训练服务和源码目录</template>
        <div>训练服务：{{ capabilityDiagnostics.train_service_url }}</div>
        <div>
          训练服务连通性：
          {{ capabilityDiagnostics.train_service_reachable ? '正常' : (capabilityDiagnostics.train_service_error || '失败') }}
        </div>
        <div>训练侧能力数：{{ capabilityDiagnostics.train_capabilities.length }}</div>
        <div>
          源码目录：
          {{ capabilityDiagnostics.capability_source_dir }}
          （{{ capabilityDiagnostics.capability_source_dir_exists ? '存在' : '不存在' }}）
        </div>
        <div>本地源码能力数：{{ capabilityDiagnostics.source_capabilities.length }}</div>
      </el-alert>

      <el-form :model="form" label-width="140px" style="max-width:700px;">
        <!-- Key Pair selection -->
        <el-form-item label="客户密钥对">
          <el-select
            v-model="form.key_pair_id"
            placeholder="选择客户密钥对（自动绑定公钥指纹）"
            clearable
            filterable
            style="width:100%;"
            @change="onKeyPairChange"
          >
            <el-option
              v-for="kp in keyPairs"
              :key="kp.id"
              :label="`${kp.name} (ID: ${kp.id})`"
              :value="kp.id"
            />
          </el-select>
          <div v-if="selectedFingerprint" style="margin-top:4px;color:#67c23a;font-size:12px;">
            ✅ 公钥指纹: {{ selectedFingerprint.slice(0, 16) }}...{{ selectedFingerprint.slice(-16) }}
          </div>
          <div style="margin-top:4px;color:#909399;font-size:12px;">
            选择密钥对后，编译时将自动将客户公钥指纹写入 SO 库
          </div>
        </el-form-item>

        <!-- Capability selection -->
        <el-form-item label="AI 推理能力">
          <el-select
            v-model="form.capability"
            placeholder="选择要编译的 AI 能力"
            filterable
            style="width:100%;"
          >
            <el-option
              v-for="cap in capabilities"
              :key="cap"
              :label="cap"
              :value="cap"
            />
          </el-select>
        </el-form-item>

        <!-- Build type -->
        <el-form-item label="编译类型">
          <el-radio-group v-model="form.build_type">
            <el-radio value="Release">Release（发布版）</el-radio>
            <el-radio value="Debug">Debug（调试版）</el-radio>
            <el-radio value="RelWithDebInfo">RelWithDebInfo</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- Platform -->
        <el-form-item label="目标平台">
          <el-select v-model="form.platform" style="width:100%;">
            <el-option label="Linux x86_64" value="linux_x86_64" />
          </el-select>
        </el-form-item>

        <!-- Extra cmake args -->
        <el-form-item label="额外 CMake 参数">
          <el-input
            v-model="extraArgsStr"
            placeholder="可选，空格分隔，如 -DFOO=ON -DBAR=OFF"
          />
        </el-form-item>

        <!-- Submit -->
        <el-form-item>
          <el-button
            type="primary"
            :loading="submitting"
            :disabled="!form.capability"
            @click="submitBuild"
          >
            🚀 开始编译
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- Build result dialog -->
    <el-dialog
      v-model="showLogDialog"
      title="编译进度"
      width="80%"
      :close-on-click-modal="false"
    >
      <div style="margin-bottom:8px;">
        <el-tag :type="statusType(currentBuild?.status)">{{ statusLabel(currentBuild?.status) }}</el-tag>
        <span style="margin-left:8px;color:#606266;">{{ currentBuild?.capability }}</span>
      </div>
      <el-input
        ref="logArea"
        type="textarea"
        :rows="20"
        :model-value="logText"
        readonly
        style="font-family:monospace;font-size:12px;"
      />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import {
  getCapabilities,
  getCapabilityDiagnostics,
  getKeyPairs,
  triggerBuild,
  connectBuildWs,
  extractErrorMessage,
} from '../api/index.js'
import { ElMessage } from 'element-plus'

const capabilities = ref([])
const capabilityDiagnostics = ref(null)
const keyPairs = ref([])
const selectedFingerprint = ref('')
const submitting = ref(false)
const showLogDialog = ref(false)
const logText = ref('')
const currentBuild = ref(null)
const logArea = ref(null)
const extraArgsStr = ref('')

const form = ref({
  capability: '',
  platform: 'linux_x86_64',
  build_type: 'Release',
  key_pair_id: null,
})

function statusType(s) {
  if (s === 'done') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'running') return 'warning'
  return 'info'
}
function statusLabel(s) {
  const m = { pending: '排队中', running: '编译中', done: '成功', failed: '失败' }
  return m[s] || s
}

function onKeyPairChange(kpId) {
  if (!kpId) {
    selectedFingerprint.value = ''
    return
  }
  const kp = keyPairs.value.find(k => k.id === kpId)
  selectedFingerprint.value = kp?.fingerprint || ''
}

async function submitBuild() {
  if (!form.value.capability) {
    ElMessage.warning('请选择要编译的 AI 能力')
    return
  }
  submitting.value = true

  const payload = {
    capability: form.value.capability,
    platform: form.value.platform,
    build_type: form.value.build_type,
  }
  if (form.value.key_pair_id) {
    payload.key_pair_id = form.value.key_pair_id
  }
  const extra = extraArgsStr.value.trim()
  if (extra) {
    payload.extra_cmake_args = extra.split(/\s+/)
  }

  try {
    const res = await triggerBuild(payload)
    currentBuild.value = res.data
    logText.value = ''
    showLogDialog.value = true
    streamLogs(res.data.job_id)
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function loadCapabilityDiagnostics() {
  try {
    const res = await getCapabilityDiagnostics()
    capabilityDiagnostics.value = res.data
  } catch {
    capabilityDiagnostics.value = {
      train_service_url: '未知',
      train_service_reachable: false,
      train_service_error: '诊断接口调用失败',
      train_capabilities: [],
      capability_source_dir: '未知',
      capability_source_dir_exists: false,
      source_capabilities: [],
    }
  }
}

function streamLogs(jobId) {
  const ws = connectBuildWs(jobId)
  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'log') {
        logText.value += msg.line
        nextTick(() => {
          const ta = logArea.value?.$el?.querySelector('textarea')
          if (ta) ta.scrollTop = ta.scrollHeight
        })
      } else if (msg.type === 'done') {
        currentBuild.value = { ...currentBuild.value, status: msg.status || 'done' }
        ws.close()
      }
    } catch { /* ignore parse errors */ }
  }
  ws.onerror = () => {
    logText.value += '\n[WebSocket 连接错误]\n'
  }
  ws.onclose = () => {
    if (currentBuild.value?.status === 'running' || currentBuild.value?.status === 'pending') {
      currentBuild.value = { ...currentBuild.value, status: 'done' }
    }
  }
}

onMounted(async () => {
  try {
    const [capRes, keyRes] = await Promise.allSettled([getCapabilities(), getKeyPairs()])
    if (capRes.status === 'fulfilled') {
      capabilities.value = capRes.value.data
      if (capabilities.value.length === 0) {
        await loadCapabilityDiagnostics()
      }
    } else {
      await loadCapabilityDiagnostics()
    }
    if (keyRes.status === 'fulfilled') keyPairs.value = keyRes.value.data
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
})
</script>
