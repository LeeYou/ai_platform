<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <span style="font-size:16px;font-weight:bold;">⚙️ 系统管理</span>
      </template>

      <el-form label-width="140px" style="max-width:600px;">
        <el-form-item label="管理员令牌">
          <el-input
            v-model="token"
            type="password"
            show-password
            placeholder="输入管理员 Bearer Token"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="warning"
            :loading="reloading"
            :disabled="!token"
            @click="doReload"
          >
            🔄 全量重载
          </el-button>
        </el-form-item>
      </el-form>

      <el-divider />

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
import { ref } from 'vue'
import { adminReload, extractErrorMessage } from '../api/index.js'
import { ElMessage } from 'element-plus'

const token = ref('')
const reloading = ref(false)
const message = ref('')
const messageType = ref('success')

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
    ElMessage.error(extractErrorMessage(e))
  } finally {
    reloading.value = false
  }
}
</script>
