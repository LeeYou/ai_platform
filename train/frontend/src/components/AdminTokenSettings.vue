<template>
  <div>
    <el-button :type="hasToken ? 'success' : 'warning'" plain @click="openDialog">
      <el-icon><Lock /></el-icon>
      <span style="margin-left:8px;">{{ hasToken ? '已设置管理Token' : '设置管理Token' }}</span>
    </el-button>

    <el-dialog v-model="dialogVisible" title="设置管理Token" width="520px">
      <el-alert
        :title="statusTitle"
        :type="hasToken ? 'success' : 'warning'"
        :closable="false"
        show-icon
      />

      <el-form label-width="100px" style="margin-top:16px;">
        <el-form-item label="存储位置">
          <el-radio-group v-model="selectedStorage">
            <el-radio value="local">localStorage</el-radio>
            <el-radio value="session">sessionStorage</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="管理Token">
          <el-input
            v-model="draftToken"
            type="password"
            show-password
            placeholder="请输入 AI_ADMIN_TOKEN"
          />
        </el-form-item>
      </el-form>

      <div style="color:#909399;font-size:12px;line-height:1.6;">
        推荐优先使用 sessionStorage；localStorage 会持久保存 Token，仅在确认当前浏览器环境可信时再使用。未单独配置后端 AI_ADMIN_TOKEN 时，默认值通常为 changeme。
      </div>

      <template #footer>
        <el-button @click="clearToken">清除</el-button>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="saveToken">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

const ENV_TOKEN = (import.meta.env.VITE_AI_ADMIN_TOKEN || '').trim()

const dialogVisible = ref(false)
const draftToken = ref('')
const activeToken = ref('')
const activeStorage = ref('')
const selectedStorage = ref('session')

const hasToken = computed(() => !!activeToken.value)
const statusTitle = computed(() => {
  if (!hasToken.value) return '当前浏览器尚未设置管理Token'
  if (activeStorage.value === 'env') return '当前使用构建注入的 VITE_AI_ADMIN_TOKEN'
  return `当前使用 ${activeStorage.value === 'session' ? 'sessionStorage' : 'localStorage'} 中的管理Token`
})

function syncFromStorage() {
  const localToken = window.localStorage.getItem('ai_admin_token')?.trim() || ''
  const sessionToken = window.sessionStorage.getItem('ai_admin_token')?.trim() || ''

  if (localToken) {
    activeToken.value = localToken
    activeStorage.value = 'local'
    selectedStorage.value = 'local'
    draftToken.value = localToken
    return
  }

  if (sessionToken) {
    activeToken.value = sessionToken
    activeStorage.value = 'session'
    selectedStorage.value = 'session'
    draftToken.value = sessionToken
    return
  }

  activeToken.value = ENV_TOKEN
  activeStorage.value = ENV_TOKEN ? 'env' : ''
  selectedStorage.value = 'session'
  draftToken.value = ENV_TOKEN
}

function emitTokenChanged() {
  window.dispatchEvent(new Event('ai-admin-token-changed'))
}

function openDialog() {
  syncFromStorage()
  dialogVisible.value = true
}

function saveToken() {
  const token = draftToken.value.trim()
  if (!token) {
    ElMessage.warning('请输入管理Token')
    return
  }

  if (selectedStorage.value === 'session') {
    window.localStorage.removeItem('ai_admin_token')
    window.sessionStorage.setItem('ai_admin_token', token)
  } else {
    window.sessionStorage.removeItem('ai_admin_token')
    window.localStorage.setItem('ai_admin_token', token)
  }

  syncFromStorage()
  dialogVisible.value = false
  emitTokenChanged()
  ElMessage.success('管理Token已保存')
}

function clearToken() {
  window.localStorage.removeItem('ai_admin_token')
  window.sessionStorage.removeItem('ai_admin_token')
  syncFromStorage()
  dialogVisible.value = false
  emitTokenChanged()
  ElMessage.success(ENV_TOKEN ? '已清除浏览器中的管理Token，当前仍会回退到 VITE_AI_ADMIN_TOKEN' : '管理Token已清除')
}

function handleTokenChanged() {
  syncFromStorage()
}

onMounted(() => {
  syncFromStorage()
  window.addEventListener('storage', handleTokenChanged)
  window.addEventListener('ai-admin-token-changed', handleTokenChanged)
})

onBeforeUnmount(() => {
  window.removeEventListener('storage', handleTokenChanged)
  window.removeEventListener('ai-admin-token-changed', handleTokenChanged)
})
</script>
