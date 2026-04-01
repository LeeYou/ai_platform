<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-size:16px;font-weight:bold;">📋 编译历史</span>
          <el-button size="small" @click="loadBuilds">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </template>

      <el-table :data="builds" stripe style="width:100%;" v-loading="loading">
        <el-table-column prop="capability" label="AI 能力" width="180" />
        <el-table-column prop="platform" label="平台" width="120" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{row}">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="200">
          <template #default="{row}">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="finished_at" label="完成时间" width="200">
          <template #default="{row}">{{ row.finished_at ? formatTime(row.finished_at) : '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="200">
          <template #default="{row}">
            <el-button size="small" @click="viewLogs(row)">
              <el-icon><Document /></el-icon> 日志
            </el-button>
            <el-button
              v-if="row.status === 'done'"
              size="small"
              type="success"
              @click="viewArtifacts(row)"
            >
              <el-icon><Download /></el-icon> 产物
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && builds.length === 0" description="暂无编译记录" />
    </el-card>

    <!-- Log Dialog -->
    <el-dialog v-model="showLogDialog" title="编译日志" width="80%">
      <el-input
        type="textarea"
        :rows="25"
        :model-value="logText"
        readonly
        style="font-family:monospace;font-size:12px;"
      />
    </el-dialog>

    <!-- Artifacts Dialog -->
    <el-dialog v-model="showArtifactDialog" title="编译产物" width="60%">
      <div style="margin-bottom:12px;">
        <el-button type="primary" @click="downloadAll">
          <el-icon><Download /></el-icon> 一键下载(tar.gz)
        </el-button>
      </div>
      <el-table :data="artifacts" stripe style="width:100%;" v-loading="artifactLoading">
        <el-table-column prop="filename" label="文件名" />
        <el-table-column prop="size" label="大小" width="120">
          <template #default="{row}">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{row}">
            <el-button size="small" type="primary" @click="doDownload(row)">
              <el-icon><Download /></el-icon> 下载
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!artifactLoading && artifacts.length === 0" description="暂无产物文件" />
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import {
  getBuilds,
  getBuildLogs,
  getArtifacts,
  downloadArtifact,
  downloadPackage,
  extractErrorMessage,
} from '../api/index.js'
import { ElMessage } from 'element-plus'

const builds = ref([])
const loading = ref(false)
const showLogDialog = ref(false)
const logText = ref('')
const showArtifactDialog = ref(false)
const artifacts = ref([])
const artifactLoading = ref(false)
const currentJobId = ref('')

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
function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN')
}
function formatSize(bytes) {
  if (!bytes || bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  let i = 0
  let size = bytes
  while (size >= 1024 && i < units.length - 1) { size /= 1024; i++ }
  return `${size.toFixed(1)} ${units[i]}`
}

async function loadBuilds() {
  loading.value = true
  try {
    const res = await getBuilds()
    builds.value = res.data.slice().reverse()
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

async function viewLogs(row) {
  try {
    const res = await getBuildLogs(row.job_id)
    logText.value = typeof res.data === 'string' ? res.data : res.data.toString()
    showLogDialog.value = true
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
}

async function viewArtifacts(row) {
  currentJobId.value = row.job_id
  artifactLoading.value = true
  showArtifactDialog.value = true
  try {
    const res = await getArtifacts(row.job_id)
    artifacts.value = res.data
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
    artifacts.value = []
  } finally {
    artifactLoading.value = false
  }
}

async function doDownload(item) {
  try {
    const res = await downloadArtifact(currentJobId.value, item.filename)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = item.filename
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
}

async function downloadAll() {
  try {
    const res = await downloadPackage(currentJobId.value)
    const url = window.URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    // Extract filename from Content-Disposition header if available
    const disposition = res.headers['content-disposition']
    let filename = `build_${currentJobId.value}.tar.gz`
    if (disposition) {
      const match = disposition.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/)
      if (match && match[1]) {
        filename = match[1].replace(/['"]/g, '')
      }
    }
    a.download = filename
    a.click()
    window.URL.revokeObjectURL(url)
    ElMessage.success('打包下载成功')
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
}

onMounted(() => { loadBuilds() })
</script>
