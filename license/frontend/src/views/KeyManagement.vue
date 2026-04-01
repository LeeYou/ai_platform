<template>
  <div>
    <el-alert
      title="⚠️ 安全提示：私钥绝不存储于数据库，请妥善保管私钥文件。一旦丢失将无法重新获取。"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom:16px;"
    />

    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>🔑 密钥管理</span>
          <el-button type="primary" @click="openGenerate"><el-icon><Plus /></el-icon> 生成新密钥对</el-button>
        </div>
      </template>
      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="created_at" label="创建时间" width="130">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="handleDownloadPubKey(row)">下载公钥</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Generate Key Dialog -->
    <el-dialog v-model="generateDialog" title="生成新密钥对" width="480px">
      <el-alert
        title="私钥将保存到您指定的服务器路径，数据库中仅存储公钥。请确保路径安全可写。"
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom:16px;"
      />
      <el-form :model="genForm" :rules="genRules" ref="genFormRef" label-width="120px">
        <el-form-item label="密钥名称" prop="name">
          <el-input v-model="genForm.name" placeholder="如 production-key-2024" />
        </el-form-item>
        <el-form-item label="私钥保存路径" prop="privkey_output_path">
          <el-input v-model="genForm.privkey_output_path" placeholder="/data/licenses/keys/客户名称/private_key.pem" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="generateDialog = false">取消</el-button>
        <el-button type="primary" @click="handleGenerate" :loading="submitting">生成密钥对</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getKeys, createKey, downloadPublicKey, extractErrorMessage } from '../api/index.js'

const loading = ref(false)
const submitting = ref(false)
const list = ref([])
const generateDialog = ref(false)
const genFormRef = ref()
const genForm = ref({ name: '', privkey_output_path: '' })

const genRules = {
  name: [{ required: true, message: '请输入密钥名称', trigger: 'blur' }],
  privkey_output_path: [{ required: true, message: '请输入私钥保存路径', trigger: 'blur' }],
}

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}

async function loadList() {
  loading.value = true
  try {
    const res = await getKeys()
    list.value = res.data?.items ?? res.data ?? []
  } catch (e) {
    ElMessage.error('加载密钥列表失败：' + extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

function openGenerate() {
  genForm.value = { name: '', privkey_output_path: '' }
  generateDialog.value = true
}

async function handleGenerate() {
  await genFormRef.value.validate()
  submitting.value = true
  try {
    await createKey(genForm.value)
    ElMessage.success('密钥对生成成功')
    generateDialog.value = false
    loadList()
  } catch (e) {
    ElMessage.error('生成失败：' + extractErrorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function handleDownloadPubKey(row) {
  try {
    const res = await downloadPublicKey(row.id)
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `${row.name || 'key_' + row.id}_public.pem`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('下载公钥失败：' + extractErrorMessage(e))
  }
}

onMounted(loadList)
</script>
