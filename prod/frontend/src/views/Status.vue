<template>
  <div>
    <el-row :gutter="20" style="margin-bottom:20px;">
      <el-col :span="24">
        <el-card shadow="hover">
          <template #header><span style="font-size:16px;font-weight:bold;">🧠 已加载能力</span></template>
          <el-table :data="capabilities" stripe style="width:100%;" v-loading="loading">
            <el-table-column prop="name" label="能力名称" width="200">
              <template #default="{ row }">
                {{ typeof row === 'string' ? row : (row.name || row.capability || '—') }}
              </template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="100">
              <template #default="{ row }">
                <el-tag v-if="typeof row === 'object'" :type="row.status === 'ready' ? 'success' : 'warning'" size="small">
                  {{ row.status || '就绪' }}
                </el-tag>
                <el-tag v-else type="success" size="small">就绪</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="model_version" label="模型版本" width="160">
              <template #default="{ row }">
                {{ typeof row === 'object' ? (row.model_version || row.version || '—') : '—' }}
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源">
              <template #default="{ row }">
                {{ typeof row === 'object' ? (row.source || row.model_path || '—') : '—' }}
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!loading && capabilities.length === 0" description="暂无已加载能力" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="20" style="margin-bottom:20px;">
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span style="font-size:16px;font-weight:bold;">📜 许可证信息</span></template>
          <el-descriptions :column="1" border size="small" v-loading="licLoading">
            <el-descriptions-item label="状态">
              <el-tag :type="licData.valid ? 'success' : 'danger'">
                {{ licData.valid ? '有效' : '无效/过期' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="到期时间">{{ licData.expiry || '—' }}</el-descriptions-item>
            <el-descriptions-item label="剩余天数">
              <span v-if="licData.days != null">{{ licData.days }} 天</span>
              <span v-else>—</span>
            </el-descriptions-item>
            <el-descriptions-item label="许可类型">{{ licData.type || '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="hover">
          <template #header><span style="font-size:16px;font-weight:bold;">💓 健康详情</span></template>
          <el-descriptions :column="1" border size="small" v-loading="healthLoading">
            <el-descriptions-item label="服务状态">
              <el-tag :type="healthData.ok ? 'success' : 'danger'">
                {{ healthData.ok ? '正常' : '异常' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="GPU">
              <el-tag :type="healthData.gpu ? 'success' : 'info'">
                {{ healthData.gpu ? '可用' : '不可用' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="版本">{{ healthData.version || '—' }}</el-descriptions-item>
            <el-descriptions-item label="运行时间">{{ healthData.uptime || '—' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getCapabilities, getLicense, getHealth, extractErrorMessage } from '../api/index.js'
import { ElMessage } from 'element-plus'

const capabilities = ref([])
const loading = ref(false)
const licLoading = ref(false)
const healthLoading = ref(false)

const licData = ref({ valid: false, expiry: '', days: null, type: '' })
const healthData = ref({ ok: false, gpu: false, version: '', uptime: '' })

onMounted(async () => {
  loading.value = true
  licLoading.value = true
  healthLoading.value = true

  try {
    const [capRes, licRes, healthRes] = await Promise.allSettled([
      getCapabilities(),
      getLicense(),
      getHealth(),
    ])

    if (capRes.status === 'fulfilled') {
      const data = capRes.value.data
      if (Array.isArray(data)) {
        capabilities.value = data
      } else if (data.capabilities) {
        capabilities.value = data.capabilities
      }
    }

    if (licRes.status === 'fulfilled') {
      const lic = licRes.value.data
      licData.value = {
        valid: lic.valid === true || lic.status === 'valid',
        expiry: lic.expiry || lic.expires_at || lic.expiration || '',
        days: lic.days_remaining ?? lic.remaining_days ?? null,
        type: lic.type || lic.license_type || '',
      }
    }

    if (healthRes.status === 'fulfilled') {
      const h = healthRes.value.data
      healthData.value = {
        ok: h.status === 'ok' || h.status === 'healthy' || !!h.healthy,
        gpu: !!h.gpu_available,
        version: h.version || '',
        uptime: h.uptime || '',
      }
    }
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  } finally {
    loading.value = false
    licLoading.value = false
    healthLoading.value = false
  }
})
</script>
