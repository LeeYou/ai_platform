<template>
  <div>
    <el-row :gutter="20" style="margin-bottom:20px;">
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header><span>📦 可编译能力</span></template>
          <div style="font-size:32px;font-weight:bold;text-align:center;">{{ capCount }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header><span>🔑 客户密钥对</span></template>
          <div style="font-size:32px;font-weight:bold;text-align:center;">{{ keyCount }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card shadow="hover">
          <template #header><span>🔨 总编译次数</span></template>
          <div style="font-size:32px;font-weight:bold;text-align:center;">{{ buildCount }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>⚡ 快捷操作</span></template>
          <el-button type="primary" @click="$router.push('/new')">
            <el-icon><SetUp /></el-icon>
            新建编译任务
          </el-button>
          <el-button @click="$router.push('/history')">
            <el-icon><List /></el-icon>
            查看编译历史
          </el-button>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span>📊 最近编译</span></template>
          <el-table :data="recentBuilds" stripe size="small" style="width:100%;">
            <el-table-column prop="capability" label="能力" width="160" />
            <el-table-column prop="status" label="状态" width="80">
              <template #default="{row}">
                <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="时间" />
          </el-table>
          <el-empty v-if="recentBuilds.length === 0" description="暂无编译记录" />
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getCapabilities, getKeyPairs, getBuilds, extractErrorMessage } from '../api/index.js'
import { ElMessage } from 'element-plus'

const capCount = ref(0)
const keyCount = ref(0)
const buildCount = ref(0)
const recentBuilds = ref([])

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

onMounted(async () => {
  try {
    const [capRes, keyRes, buildRes] = await Promise.allSettled([
      getCapabilities(),
      getKeyPairs(),
      getBuilds(),
    ])
    if (capRes.status === 'fulfilled') capCount.value = capRes.value.data.length
    if (keyRes.status === 'fulfilled') keyCount.value = keyRes.value.data.length
    if (buildRes.status === 'fulfilled') {
      const builds = buildRes.value.data
      buildCount.value = builds.length
      recentBuilds.value = builds.slice(-5).reverse()
    }
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
})
</script>
