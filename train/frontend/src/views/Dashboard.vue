<template>
  <div>
    <div style="margin-bottom:24px;">
      <el-row :gutter="16">
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic title="AI 能力总数" :value="stats.capabilityCount">
              <template #prefix><el-icon color="#409EFF"><Setting /></el-icon></template>
            </el-statistic>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic title="运行中任务" :value="stats.runningJobs">
              <template #prefix><el-icon color="#67C23A"><VideoPlay /></el-icon></template>
            </el-statistic>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic title="已完成任务" :value="stats.doneJobs">
              <template #prefix><el-icon color="#909399"><CircleCheck /></el-icon></template>
            </el-statistic>
          </el-card>
        </el-col>
        <el-col :span="6">
          <el-card shadow="never">
            <el-statistic title="模型版本总数" :value="stats.modelCount">
              <template #prefix><el-icon color="#E6A23C"><Box /></el-icon></template>
            </el-statistic>
          </el-card>
        </el-col>
      </el-row>
    </div>

    <el-row :gutter="16">
      <el-col :span="16">
        <el-card shadow="never" header="最近训练任务">
          <el-table :data="recentJobs" style="width:100%" v-loading="loading">
            <el-table-column prop="id" label="ID" width="60" />
            <el-table-column label="能力" width="120">
              <template #default="{row}">
                {{ capabilityName(row.capability_id) }}
              </template>
            </el-table-column>
            <el-table-column prop="version" label="版本" width="90" />
            <el-table-column label="状态" width="100">
              <template #default="{row}">
                <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="创建时间">
              <template #default="{row}">{{ fmtTime(row.created_at) }}</template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="never" header="快捷操作">
          <div style="display:flex;flex-direction:column;gap:12px;margin-top:8px;">
            <el-button type="primary" @click="$router.push('/jobs')">
              <el-icon><VideoPlay /></el-icon> 新建训练任务
            </el-button>
            <el-button @click="$router.push('/models')">
              <el-icon><Box /></el-icon> 查看模型列表
            </el-button>
            <el-button @click="$router.push('/capabilities')">
              <el-icon><Setting /></el-icon> 管理能力配置
            </el-button>
            <el-button @click="$router.push('/datasets')">
              <el-icon><FolderOpen /></el-icon> 查看数据集
            </el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listCapabilities, listJobs, listModels } from '../api/index.js'

const loading = ref(false)
const capabilities = ref([])
const jobs = ref([])
const models = ref([])

const stats = computed(() => ({
  capabilityCount: capabilities.value.length,
  runningJobs: jobs.value.filter(j => j.status === 'running').length,
  doneJobs: jobs.value.filter(j => j.status === 'done').length,
  modelCount: models.value.length,
}))

const recentJobs = computed(() => jobs.value.slice(0, 10))

const capabilityName = (id) => {
  const c = capabilities.value.find(c => c.id === id)
  return c ? (c.name_cn || c.name) : `#${id}`
}

const statusType = (s) => ({
  running: 'primary', done: 'success', failed: 'danger', paused: 'warning', pending: 'info'
}[s] || 'info')

const fmtTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

onMounted(async () => {
  loading.value = true
  try {
    const [c, j, m] = await Promise.all([listCapabilities(), listJobs(), listModels()])
    capabilities.value = c.data
    jobs.value = j.data
    models.value = m.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
})
</script>
