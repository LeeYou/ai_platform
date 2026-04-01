<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span style="font-size:16px;font-weight:bold;">🔗 AI 编排管理</span>
          <el-button type="primary" @click="$router.push('/pipelines/new')">
            <el-icon><Plus /></el-icon>
            新建编排
          </el-button>
        </div>
      </template>

      <el-table :data="pipelines" stripe style="width:100%;" v-loading="loading">
        <el-table-column prop="pipeline_id" label="编排 ID" width="180" />
        <el-table-column prop="name" label="名称" width="180" />
        <el-table-column prop="description" label="描述" />
        <el-table-column label="步骤数" width="80" align="center">
          <template #default="{ row }">
            {{ row.steps ? row.steps.length : 0 }}
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag :type="row.enabled !== false ? 'success' : 'info'" size="small">
              {{ row.enabled !== false ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="$router.push(`/pipelines/${row.pipeline_id}/edit`)">
              <el-icon><Edit /></el-icon> 编辑
            </el-button>
            <el-button
              size="small"
              :type="row.enabled !== false ? 'warning' : 'success'"
              @click="toggleEnable(row)"
            >
              {{ row.enabled !== false ? '禁用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" @click="doDelete(row)">
              <el-icon><Delete /></el-icon> 删除
            </el-button>
            <el-button size="small" type="primary" @click="goTest(row)">
              测试
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && pipelines.length === 0" description="暂无编排配置" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getPipelines, deletePipeline, updatePipeline, extractErrorMessage } from '../api/index.js'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

const router = useRouter()
const pipelines = ref([])
const loading = ref(false)

async function loadPipelines() {
  loading.value = true
  try {
    const res = await getPipelines()
    pipelines.value = Array.isArray(res.data) ? res.data : (res.data.pipelines || [])
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

async function doDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除编排「${row.name || row.pipeline_id}」？`, '确认删除', {
      type: 'warning',
    })
    await deletePipeline(row.pipeline_id)
    ElMessage.success('删除成功')
    loadPipelines()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(extractErrorMessage(e))
  }
}

async function toggleEnable(row) {
  try {
    const newEnabled = row.enabled === false
    await updatePipeline(row.pipeline_id, { ...row, enabled: newEnabled })
    ElMessage.success(newEnabled ? '已启用' : '已禁用')
    loadPipelines()
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
}

function goTest(row) {
  router.push({ path: '/pipeline-test', query: { id: row.pipeline_id } })
}

onMounted(() => { loadPipelines() })
</script>
