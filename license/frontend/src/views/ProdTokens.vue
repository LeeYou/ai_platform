<template>
  <div>
    <el-alert
      title="🔐 安全说明：Token 明文仅在生成时显示一次，之后只存储 SHA-256 哈希值。请妥善保管 Token。"
      type="warning"
      show-icon
      :closable="false"
      style="margin-bottom:16px;"
    />

    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>🔑 生产服务管理令牌</span>
          <el-button type="primary" @click="openCreate"><el-icon><Plus /></el-icon> 生成新令牌</el-button>
        </div>
      </template>
      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="token_name" label="令牌名称" width="200" />
        <el-table-column prop="token_hash" label="哈希值" width="150">
          <template #default="{ row }">
            <el-tag size="small">{{ row.token_hash }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="environment" label="环境" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.environment" :type="getEnvType(row.environment)" size="small">
              {{ row.environment }}
            </el-tag>
            <span v-else style="color:#999;">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="created_by" label="创建人" width="120">
          <template #default="{ row }">{{ row.created_by || '-' }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column prop="expires_at" label="过期时间" width="180">
          <template #default="{ row }">
            <span v-if="row.expires_at" :style="getExpireStyle(row.expires_at)">
              {{ formatDateTime(row.expires_at) }}
            </span>
            <span v-else style="color:#67c23a;">永不过期</span>
          </template>
        </el-table-column>
        <el-table-column prop="is_active" label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
              {{ row.is_active ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="usage_count" label="使用次数" width="110" />
        <el-table-column prop="last_used_at" label="最后使用" width="180">
          <template #default="{ row }">
            {{ row.last_used_at ? formatDateTime(row.last_used_at) : '从未使用' }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              size="small"
              :type="row.is_active ? 'warning' : 'success'"
              plain
              @click="handleToggleStatus(row)"
            >
              {{ row.is_active ? '停用' : '启用' }}
            </el-button>
            <el-button size="small" type="danger" plain @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create Token Dialog -->
    <el-dialog v-model="createDialog" title="生成新管理令牌" width="600px">
      <el-alert
        title="令牌将使用密码学安全随机生成器（256位）。明文仅显示一次，请立即复制保存。"
        type="info"
        show-icon
        :closable="false"
        style="margin-bottom:16px;"
      />
      <el-form :model="createForm" :rules="createRules" ref="createFormRef" label-width="120px">
        <el-form-item label="令牌名称" prop="token_name">
          <el-input v-model="createForm.token_name" placeholder="如 prod-token-2026" />
        </el-form-item>
        <el-form-item label="环境标识" prop="environment">
          <el-select v-model="createForm.environment" placeholder="选择环境（可选）" clearable>
            <el-option label="生产环境 (production)" value="production" />
            <el-option label="预发布环境 (staging)" value="staging" />
            <el-option label="测试环境 (test)" value="test" />
          </el-select>
        </el-form-item>
        <el-form-item label="创建人" prop="created_by">
          <el-input v-model="createForm.created_by" placeholder="操作员姓名（可选）" />
        </el-form-item>
        <el-form-item label="过期时间" prop="expires_at">
          <el-date-picker
            v-model="createForm.expires_at"
            type="datetime"
            placeholder="选择过期时间（留空=永不过期）"
            format="YYYY-MM-DD HH:mm:ss"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width:100%;"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialog = false">取消</el-button>
        <el-button type="primary" @click="handleCreate" :loading="submitting">生成令牌</el-button>
      </template>
    </el-dialog>

    <!-- Token Created Success Dialog -->
    <el-dialog v-model="tokenCreatedDialog" title="✅ 令牌生成成功" width="700px" :close-on-click-modal="false">
      <el-alert
        title="⚠️ 请立即复制保存此令牌！它将仅显示一次，关闭后无法再次查看。"
        type="warning"
        show-icon
        :closable="false"
        style="margin-bottom:16px;"
      />
      <el-descriptions :column="1" border>
        <el-descriptions-item label="令牌名称">{{ createdToken.token_name }}</el-descriptions-item>
        <el-descriptions-item label="环境">{{ createdToken.environment || '-' }}</el-descriptions-item>
        <el-descriptions-item label="明文令牌" label-class-name="token-label">
          <div style="display:flex;align-items:center;gap:8px;">
            <el-input
              v-model="createdToken.plaintext_token"
              readonly
              type="textarea"
              :rows="3"
              style="font-family:monospace;font-size:13px;"
            />
            <el-button type="primary" @click="copyToken">
              <el-icon><CopyDocument /></el-icon> 复制
            </el-button>
          </div>
        </el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button type="primary" @click="tokenCreatedDialog = false">我已保存，关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, CopyDocument } from '@element-plus/icons-vue'
import { getProdTokens, createProdToken, updateProdToken, deleteProdToken, extractErrorMessage } from '../api/index.js'

const loading = ref(false)
const submitting = ref(false)
const list = ref([])
const createDialog = ref(false)
const tokenCreatedDialog = ref(false)
const createFormRef = ref()
const createForm = ref({
  token_name: '',
  environment: '',
  created_by: '',
  expires_at: null
})
const createdToken = ref({})

const createRules = {
  token_name: [{ required: true, message: '请输入令牌名称', trigger: 'blur' }],
}

function getEnvType(env) {
  const types = {
    production: 'danger',
    staging: 'warning',
    test: 'info',
  }
  return types[env] || ''
}

function getExpireStyle(expires_at) {
  if (!expires_at) return ''
  const now = new Date()
  const expireDate = new Date(expires_at)
  const daysLeft = (expireDate - now) / (1000 * 60 * 60 * 24)

  if (daysLeft < 0) return 'color:#f56c6c;font-weight:bold;'
  if (daysLeft < 7) return 'color:#e6a23c;font-weight:bold;'
  if (daysLeft < 30) return 'color:#e6a23c;'
  return ''
}

function formatDateTime(val) {
  if (!val) return '-'
  return val.replace('T', ' ').slice(0, 19)
}

async function loadList() {
  loading.value = true
  try {
    const res = await getProdTokens()
    list.value = res.data ?? []
  } catch (e) {
    ElMessage.error('加载令牌列表失败：' + extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

function openCreate() {
  createForm.value = {
    token_name: '',
    environment: '',
    created_by: '',
    expires_at: null
  }
  createDialog.value = true
}

async function handleCreate() {
  if (!createFormRef.value) return

  try {
    await createFormRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    const res = await createProdToken(createForm.value)
    createdToken.value = res.data
    createDialog.value = false
    tokenCreatedDialog.value = true
    ElMessage.success('令牌生成成功')
    await loadList()
  } catch (e) {
    ElMessage.error('生成令牌失败：' + extractErrorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function copyToken() {
  try {
    await navigator.clipboard.writeText(createdToken.value.plaintext_token)
    ElMessage.success('已复制到剪贴板')
  } catch (e) {
    ElMessage.error('复制失败，请手动复制')
  }
}

async function handleToggleStatus(row) {
  const action = row.is_active ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(
      `确定要${action}令牌「${row.token_name}」吗？`,
      '确认操作',
      { type: 'warning' }
    )

    await updateProdToken(row.id, { is_active: !row.is_active })
    ElMessage.success(`${action}成功`)
    await loadList()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(`${action}失败：` + extractErrorMessage(e))
    }
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确定要删除令牌「${row.token_name}」吗？此操作不可恢复。`,
      '确认删除',
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' }
    )

    await deleteProdToken(row.id)
    ElMessage.success('删除成功')
    await loadList()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error('删除失败：' + extractErrorMessage(e))
    }
  }
}

onMounted(() => {
  loadList()
})
</script>

<style scoped>
:deep(.token-label) {
  font-weight: bold;
  color: #e6a23c;
}
</style>
