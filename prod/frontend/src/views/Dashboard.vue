<template>
  <div>
    <el-row :gutter="20" style="margin-bottom:20px;">
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span> 服务状态</span></template>
          <div style="text-align:center;">
            <el-tag :type="healthOk ? 'success' : 'danger'" size="large">
              {{ healthOk ? '正常运行' : '异常' }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span> 已加载能力</span></template>
          <div style="font-size:32px;font-weight:bold;text-align:center;">{{ capCount }}</div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span> 许可证状态</span></template>
          <div style="text-align:center;">
            <el-tag :type="licenseValid ? 'success' : 'danger'" size="large">
              {{ licenseValid ? '有效' : '无效/过期' }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <template #header><span> GPU 状态</span></template>
          <div style="text-align:center;">
            <el-tag :type="gpuAvailable ? 'success' : 'info'" size="large">
              {{ gpuAvailable ? 'GPU 可用' : '仅 CPU' }}
            </el-tag>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-bottom:20px;">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span> 许可证信息</span></template>
          <el-descriptions :column="1" border size="small">
            <el-descriptions-item label="到期时间">{{ licenseExpiryDisplay }}</el-descriptions-item>
            <el-descriptions-item label="剩余天数">
              <el-tag :type="licenseDaysTagType" v-if="licenseDays !== null">
                {{ licenseDaysDisplay }}
              </el-tag>
              <span v-else>—</span>
            </el-descriptions-item>
            <el-descriptions-item label="许可类型">{{ licenseType || '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span> 快捷操作</span></template>
          <el-button type="primary" @click="$router.push('/api-test')">
            <el-icon><SetUp /></el-icon>
            API 推理测试
          </el-button>
          <el-button @click="$router.push('/pipelines')">
            <el-icon><Connection /></el-icon>
            管理编排
          </el-button>
          <el-button @click="$router.push('/status')">
            <el-icon><List /></el-icon>
            查看状态
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, ref, onMounted } from 'vue'
import { getHealth, getCapabilities, getLicense, extractErrorMessage } from '../api/index.js'
import { ElMessage } from 'element-plus'

const healthOk = ref(false)
const capCount = ref(0)
const licenseValid = ref(false)
const licenseExpiry = ref('')
const licenseDays = ref(null)
const licenseType = ref('')
const gpuAvailable = ref(false)

const licenseExpiryDisplay = computed(() => {
  if (licenseExpiry.value) return licenseExpiry.value
  if (licenseValid.value && licenseDays.value === -1) return '长期有效'
  return '—'
})

const licenseDaysDisplay = computed(() => {
  if (licenseDays.value === -1) return '长期有效'
  if (licenseDays.value !== null) return `${licenseDays.value} 天`
  return '—'
})

const licenseDaysTagType = computed(() => {
  if (licenseDays.value === -1) return 'success'
  if (licenseDays.value > 30) return 'success'
  if (licenseDays.value > 7) return 'warning'
  return 'danger'
})

onMounted(async () => {
  try {
    const [healthRes, capRes, licRes] = await Promise.allSettled([
      getHealth(),
      getCapabilities(),
      getLicense(),
    ])
    if (healthRes.status === 'fulfilled') {
      const h = healthRes.value.data
      healthOk.value = h.status === 'ok' || h.status === 'healthy' || !!h.healthy
      gpuAvailable.value = !!h.gpu_available
    }
    if (capRes.status === 'fulfilled') {
      const caps = capRes.value.data
      capCount.value = Array.isArray(caps) ? caps.length : (caps.capabilities ? caps.capabilities.length : 0)
    }
    if (licRes.status === 'fulfilled') {
      const lic = licRes.value.data
      licenseValid.value = lic.status === 'active' || lic.status === 'valid' || lic.valid === true
      licenseExpiry.value = lic.valid_until || lic.expiry || lic.expires_at || lic.expiration || ''
      licenseDays.value = lic.days_remaining ?? lic.remaining_days ?? null
      licenseType.value = lic.status || lic.type || lic.license_type || ''
    }
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
})
</script>
