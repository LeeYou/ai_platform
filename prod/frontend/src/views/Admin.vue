<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <span style="font-size:16px;font-weight:bold;">⚙️ 系统管理</span>
      </template>

      <el-alert
        :title="hasToken ? '已读取浏览器中的管理Token，可直接执行管理操作。' : '请先通过右上角“设置管理Token”录入令牌。若后端沿用默认配置，通常为 changeme。'"
        :type="hasToken ? 'success' : 'warning'"
        :closable="false"
        show-icon
        style="max-width:700px;margin-bottom:16px;"
      />

      <el-form label-width="140px" style="max-width:700px;">
        <el-form-item>
          <el-button
            type="warning"
            :loading="reloading"
            :disabled="!hasToken"
            @click="doReload"
          >
            🔄 全量重载
          </el-button>
          <el-button
            type="info"
            :loading="loadingABTests"
            :disabled="!hasToken"
            @click="fetchABTests"
          >
            📊 加载 A/B 测试
          </el-button>
          <el-button
            type="primary"
            :loading="reloadingABTests"
            :disabled="!hasToken"
            @click="doReloadABTests"
          >
            ♻️ 重载 A/B 配置
          </el-button>
        </el-form-item>
      </el-form>

      <el-divider />

      <el-empty
        v-if="Object.keys(abTests).length === 0"
        description="暂无已加载的 A/B 测试配置"
      />

      <div v-else>
        <el-card
          v-for="(info, capability) in abTests"
          :key="capability"
          shadow="never"
          style="margin-bottom:16px;"
        >
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span>{{ capability }}</span>
              <el-tag size="small">{{ info.strategy || 'random' }}</el-tag>
            </div>
          </template>

          <el-table :data="info.variants || []" size="small" border>
            <el-table-column prop="version" label="版本" min-width="160" />
            <el-table-column prop="weight" label="权重" width="120" />
            <el-table-column prop="weight_pct" label="占比(%)" width="120" />
          </el-table>
        </el-card>
      </div>

      <el-alert
        v-if="message"
        :title="message"
        :type="messageType"
        show-icon
        :closable="false"
        style="max-width:600px;"
      />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { adminReload, extractErrorMessage, getAdminToken, listABTests, reloadABTests } from '../api/index.js'
import { ElMessage } from 'element-plus'

const token = ref('')
const hasToken = computed(() => !!token.value)
const reloading = ref(false)
const loadingABTests = ref(false)
const reloadingABTests = ref(false)
const message = ref('')
const messageType = ref('success')
const abTests = ref({})

function syncToken() {
  token.value = getAdminToken()
}

async function doReload() {
  if (!token.value) {
    ElMessage.warning('请输入管理员令牌')
    return
  }

  reloading.value = true
  message.value = ''

  try {
    const res = await adminReload(token.value)
    message.value = res.data?.message || res.data?.detail || '重载成功'
    messageType.value = 'success'
    ElMessage.success('重载成功')
  } catch (e) {
    message.value = extractErrorMessage(e)
    messageType.value = 'error'
    ElMessage.error(message.value)
  } finally {
    reloading.value = false
  }
}

async function fetchABTests() {
  if (!token.value) {
    ElMessage.warning('请输入管理员令牌')
    return
  }

  loadingABTests.value = true
  try {
    const res = await listABTests(token.value)
    abTests.value = res.data?.ab_tests || {}
    ElMessage.success('A/B 测试配置已加载')
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  } finally {
    loadingABTests.value = false
  }
}

async function doReloadABTests() {
  if (!token.value) {
    ElMessage.warning('请输入管理员令牌')
    return
  }

  reloadingABTests.value = true
  try {
    const res = await reloadABTests(token.value)
    abTests.value = res.data?.ab_tests || {}
    message.value = `已重载 ${res.data?.active_tests || 0} 个 A/B 测试`
    messageType.value = 'success'
    ElMessage.success(message.value)
  } catch (e) {
    message.value = extractErrorMessage(e)
    messageType.value = 'error'
    ElMessage.error(message.value)
  } finally {
    reloadingABTests.value = false
  }
}

onMounted(() => {
  syncToken()
  window.addEventListener('storage', syncToken)
  window.addEventListener('ai-admin-token-changed', syncToken)
})

onBeforeUnmount(() => {
  window.removeEventListener('storage', syncToken)
  window.removeEventListener('ai-admin-token-changed', syncToken)
})
</script>
