<template>
  <div>
    <el-card shadow="never" header="可用模型列表">
      <el-table :data="models" v-loading="loading" style="width:100%">
        <el-table-column prop="capability" label="能力标识" width="160" />
        <el-table-column prop="version" label="版本" width="100" />
        <el-table-column label="能力中文名" width="140">
          <template #default="{row}">{{ row.manifest?.capability_name_cn || '-' }}</template>
        </el-table-column>
        <el-table-column label="后端" width="120">
          <template #default="{row}">{{ row.manifest?.backend || '-' }}</template>
        </el-table-column>
        <el-table-column label="最后更新" width="170">
          <template #default="{row}">{{ fmtTime(row.last_modified) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{row}">
            <el-button link type="primary" @click="goSingle(row)">单样本测试</el-button>
            <el-button link type="success" @click="goBatch(row)">批量测试</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!loading && models.length===0" description="暂无模型，请先完成训练和导出" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listModels } from '../api/index.js'

const loading = ref(false)
const models = ref([])
const router = useRouter()
const fmtTime = (t) => t ? new Date(t).toLocaleString('zh-CN') : '-'

const goSingle = (row) => router.push({ path: '/single', query: { capability: row.capability, version: row.version } })
const goBatch  = (row) => router.push({ path: '/batch',  query: { capability: row.capability, version: row.version } })

onMounted(async () => {
  loading.value = true
  try { const r = await listModels(); models.value = r.data } finally { loading.value = false }
})
</script>
