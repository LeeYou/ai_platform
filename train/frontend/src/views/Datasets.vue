<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>数据集列表</span>
          <el-button :icon="Refresh" @click="load" :loading="loading">刷新</el-button>
        </div>
      </template>

      <el-table :data="datasets" style="width:100%" v-loading="loading">
        <el-table-column prop="name" label="能力名称" width="160" />
        <el-table-column prop="path" label="路径" show-overflow-tooltip />
        <el-table-column label="文件数量" width="100">
          <template #default="{row}">
            <el-tag type="info">{{ row.file_count }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="总大小" width="110">
          <template #default="{row}">{{ fmtSize(row.total_size_bytes) }}</template>
        </el-table-column>
        <el-table-column label="最后更新" width="170">
          <template #default="{row}">{{ fmtTime(row.last_modified) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{row}">
            <el-button link type="primary" @click="showDetail(row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!loading && datasets.length === 0" description="暂无数据集，请检查挂载路径" />
    </el-card>

    <!-- Detail drawer -->
    <el-drawer v-model="drawerVisible" :title="selected?.name" size="400px">
      <template v-if="selected">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="能力名称">{{ selected.name }}</el-descriptions-item>
          <el-descriptions-item label="路径">{{ selected.path }}</el-descriptions-item>
          <el-descriptions-item label="文件数量">
            <el-tag type="primary">{{ selected.file_count }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="总大小">{{ fmtSize(selected.total_size_bytes) }}</el-descriptions-item>
          <el-descriptions-item label="最后更新">{{ fmtTime(selected.last_modified) }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import { listDatasets } from '../api/index.js'

const loading = ref(false)
const datasets = ref([])
const drawerVisible = ref(false)
const selected = ref(null)

const fmtSize = (bytes) => {
  if (bytes >= 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${bytes} B`
}

const fmtTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

const showDetail = (row) => {
  selected.value = row
  drawerVisible.value = true
}

const load = async () => {
  loading.value = true
  try {
    const res = await listDatasets()
    datasets.value = res.data
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
