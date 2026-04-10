<template>
  <div>
    <el-card style="margin-bottom:16px;">
      <el-form inline>
        <el-form-item label="客户">
          <el-select v-model="filters.customer_id" clearable placeholder="全部客户" style="width:180px;">
            <el-option v-for="c in customerOptions" :key="c.customer_id" :label="c.name" :value="c.customer_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部状态" style="width:130px;">
            <el-option label="有效" value="active" />
            <el-option label="已过期" value="expired" />
            <el-option label="已吊销" value="revoked" />
          </el-select>
        </el-form-item>
        <el-form-item label="到期天数">
          <el-input-number v-model="filters.expiring_in_days" :min="1" :max="365" clearable placeholder="N天内" style="width:130px;" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="loadList">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <span>📋 授权列表</span>
      </template>
      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="license_id" label="授权ID" width="220" show-overflow-tooltip />
        <el-table-column prop="customer_name" label="客户" width="130" />
        <el-table-column prop="license_type" label="类型" width="100">
          <template #default="{ row }"><el-tag size="small">{{ row.license_type }}</el-tag></template>
        </el-table-column>
        <el-table-column prop="application_name" label="应用名称" width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.application_name || '-' }}</template>
        </el-table-column>
        <el-table-column prop="operating_system" label="操作系统" width="110">
          <template #default="{ row }">{{ row.operating_system || '-' }}</template>
        </el-table-column>
        <el-table-column prop="minimum_os_version" label="最低系统版本" width="140">
          <template #default="{ row }">{{ row.minimum_os_version || '不限制' }}</template>
        </el-table-column>
        <el-table-column prop="system_architecture" label="系统架构" width="120">
          <template #default="{ row }">{{ row.system_architecture || '不限制' }}</template>
        </el-table-column>
        <el-table-column prop="capabilities" label="能力" show-overflow-tooltip>
          <template #default="{ row }">{{ Array.isArray(row.capabilities) ? row.capabilities.join(', ') : row.capabilities }}</template>
        </el-table-column>
        <el-table-column prop="valid_from" label="生效日期" width="110">
          <template #default="{ row }">{{ formatDate(row.valid_from) }}</template>
        </el-table-column>
        <el-table-column prop="valid_until" label="到期日期" width="110">
          <template #default="{ row }">{{ row.valid_until ? formatDate(row.valid_until) : '永久' }}</template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }"><LicenseStatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column prop="days_remaining" label="剩余天数" width="100">
          <template #default="{ row }">
            <span v-if="row.days_remaining != null" :style="daysStyle(row.days_remaining)">{{ row.days_remaining }} 天</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="handleDownload(row)">下载</el-button>
            <el-button size="small" type="warning" plain @click="openRenew(row)" :disabled="row.status === 'revoked'">续期</el-button>
            <el-button size="small" type="danger" plain @click="handleRevoke(row)" :disabled="row.status !== 'active'">吊销</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        style="margin-top:16px;text-align:right;"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPageChange"
      />
    </el-card>

    <!-- Renew Dialog -->
    <el-dialog v-model="renewDialog" title="授权续期" width="440px">
      <el-form :model="renewForm" ref="renewFormRef" label-width="110px">
        <el-form-item label="新到期日期" prop="new_valid_until" :rules="[{ required: true, message: '请选择日期' }]">
          <el-date-picker v-model="renewForm.new_valid_until" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%;" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="renewDialog = false">取消</el-button>
        <el-button type="primary" @click="handleRenew" :loading="submitting">确认续期</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getLicenses, getCustomers, downloadLicense, renewLicense, revokeLicense, extractErrorMessage } from '../api/index.js'
import LicenseStatusTag from '../components/LicenseStatusTag.vue'

const loading = ref(false)
const submitting = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const customerOptions = ref([])
const filters = ref({ customer_id: '', status: '', expiring_in_days: null })
const renewDialog = ref(false)
const renewForm = ref({ new_valid_until: '' })
const renewFormRef = ref()
const renewingId = ref(null)

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}

function daysStyle(days) {
  if (days <= 7) return { color: '#F56C6C', fontWeight: 'bold' }
  if (days <= 30) return { color: '#E6A23C', fontWeight: 'bold' }
  return {}
}

async function loadList() {
  loading.value = true
  try {
    const params = { page: page.value, size: pageSize }
    if (filters.value.customer_id) params.customer_id = filters.value.customer_id
    if (filters.value.status) params.status = filters.value.status
    if (filters.value.expiring_in_days) params.expiring_in_days = filters.value.expiring_in_days
    const res = await getLicenses(params)
    list.value = res.data?.items ?? res.data ?? []
    total.value = res.data?.total ?? list.value.length
  } catch (e) {
    ElMessage.error('加载授权列表失败：' + extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

async function loadCustomers() {
  try {
    const res = await getCustomers(1, 200)
    customerOptions.value = res.data?.items ?? res.data ?? []
  } catch {}
}

function resetFilters() {
  filters.value = { customer_id: '', status: '', expiring_in_days: null }
  page.value = 1
  loadList()
}

function onPageChange(p) {
  page.value = p
  loadList()
}

async function handleDownload(row) {
  try {
    const res = await downloadLicense(row.license_id)
    const url = URL.createObjectURL(new Blob([res.data]))
    const a = document.createElement('a')
    a.href = url
    a.download = `license_${row.license_id}.bin`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    ElMessage.error('下载失败：' + extractErrorMessage(e))
  }
}

function openRenew(row) {
  renewingId.value = row.license_id
  renewForm.value = { new_valid_until: '' }
  renewDialog.value = true
}

async function handleRenew() {
  await renewFormRef.value.validate()
  submitting.value = true
  try {
    await renewLicense(renewingId.value, renewForm.value)
    ElMessage.success('续期成功')
    renewDialog.value = false
    loadList()
  } catch (e) {
    ElMessage.error('续期失败：' + extractErrorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function handleRevoke(row) {
  try {
    await ElMessageBox.confirm(`确定吊销授权「${row.license_id}」？吊销后不可恢复。`, '确认吊销', { type: 'warning' })
    await revokeLicense(row.license_id)
    ElMessage.success('吊销成功')
    loadList()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error('吊销失败：' + extractErrorMessage(e))
  }
}

onMounted(() => {
  loadList()
  loadCustomers()
})
</script>
