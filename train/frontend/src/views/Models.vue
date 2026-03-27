<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <span>模型版本列表</span>
          <el-select v-model="filterCapId" placeholder="按能力筛选" clearable size="small" style="width:180px;" @change="load">
            <el-option v-for="c in capabilities" :key="c.id" :label="c.name_cn||c.name" :value="c.id" />
          </el-select>
        </div>
      </template>

      <el-table :data="models" style="width:100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column label="能力" width="130">
          <template #default="{row}">{{ capName(row.capability_id) }}</template>
        </el-table-column>
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column label="当前版本" width="100">
          <template #default="{row}">
            <el-tag v-if="row.is_current" type="success">
              <el-icon><StarFilled /></el-icon> 当前
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="model_path" label="模型路径" show-overflow-tooltip />
        <el-table-column label="导出时间" width="170">
          <template #default="{row}">{{ fmtTime(row.exported_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{row}">
            <el-button v-if="!row.is_current" link type="primary" @click="setCurrent(row)">设为当前版本</el-button>
            <el-tag v-else type="success" size="small">已是当前版本</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && models.length === 0" description="暂无模型版本，请先完成训练任务" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listCapabilities, listModels, setCurrentModel } from '../api/index.js'

const loading = ref(false)
const models = ref([])
const capabilities = ref([])
const filterCapId = ref(null)

const capName = (id) => {
  const c = capabilities.value.find(c => c.id === id)
  return c ? (c.name_cn || c.name) : `#${id}`
}

const fmtTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

const load = async () => {
  loading.value = true
  try {
    const params = filterCapId.value ? { capability_id: filterCapId.value } : {}
    const res = await listModels(params)
    models.value = res.data
  } finally { loading.value = false }
}

const setCurrent = async (row) => {
  try {
    await setCurrentModel(row.id)
    ElMessage.success(`已将 ${row.version} 设为当前版本`)
    await load()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  }
}

onMounted(async () => {
  const res = await listCapabilities()
  capabilities.value = res.data
  await load()
})
</script>
