<template>
  <div>
    <el-row :gutter="20" style="margin-bottom:20px;">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="客户总数" :value="stats.totalCustomers">
            <template #prefix><el-icon color="#409EFF"><User /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="有效授权" :value="stats.activeLicenses">
            <template #prefix><el-icon color="#67C23A"><Document /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" style="border-left:4px solid #E6A23C;">
          <el-statistic title="30天内到期" :value="stats.expiring30">
            <template #prefix><el-icon color="#E6A23C"><Warning /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover" style="border-left:4px solid #F56C6C;">
          <el-statistic title="7天内到期" :value="stats.expiring7">
            <template #prefix><el-icon color="#F56C6C"><CircleClose /></el-icon></template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <el-card>
      <template #header>
        <span>⚠️ 即将到期授权（30天内）</span>
      </template>
      <el-table :data="expiringList" stripe v-loading="loading">
        <el-table-column prop="license_id" label="授权ID" width="220" show-overflow-tooltip />
        <el-table-column prop="customer_name" label="客户名称" />
        <el-table-column prop="license_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag size="small">{{ row.license_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="valid_until" label="到期日期" width="120">
          <template #default="{ row }">{{ formatDate(row.valid_until) }}</template>
        </el-table-column>
        <el-table-column prop="days_remaining" label="剩余天数" width="100">
          <template #default="{ row }">
            <span :style="daysStyle(row.days_remaining)">{{ row.days_remaining }} 天</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90">
          <template #default="{ row }">
            <LicenseStatusTag :status="row.status" />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getDashboardStats, getExpiringLicenses, extractErrorMessage } from '../api/index.js'
import LicenseStatusTag from '../components/LicenseStatusTag.vue'

const loading = ref(false)
const expiringList = ref([])
const stats = ref({ totalCustomers: 0, activeLicenses: 0, expiring30: 0, expiring7: 0 })

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}

function daysStyle(days) {
  if (days <= 7) return { color: '#F56C6C', fontWeight: 'bold' }
  if (days <= 30) return { color: '#E6A23C', fontWeight: 'bold' }
  return {}
}

async function loadData() {
  loading.value = true
  try {
    const [statsRes, expiring30Res] = await Promise.all([
      getDashboardStats(),
      getExpiringLicenses(30),
    ])
    const s = statsRes.data
    stats.value.totalCustomers = s.total_customers ?? 0
    stats.value.activeLicenses = s.active_licenses ?? 0
    stats.value.expiring30 = s.expiring_30 ?? 0
    stats.value.expiring7 = s.expiring_7 ?? 0
    expiringList.value = expiring30Res.data?.licenses ?? []
  } catch (e) {
    ElMessage.error('加载数据失败：' + extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>
