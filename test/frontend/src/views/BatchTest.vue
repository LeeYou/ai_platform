<template>
  <div>
    <el-card shadow="never" header="批量推理测试">
      <el-form :model="form" label-width="100px" style="max-width:560px;">
        <el-form-item label="AI 能力">
          <el-input v-model="form.capability" placeholder="如 recapture_detect" />
        </el-form-item>
        <el-form-item label="模型版本">
          <el-input v-model="form.version" placeholder="如 1.0.0" />
        </el-form-item>
        <el-form-item label="数据集路径">
          <el-input v-model="form.dataset_path" placeholder="/workspace/datasets/recapture_detect/test" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doSubmit" :loading="submitting">提交批量测试</el-button>
        </el-form-item>
      </el-form>

      <template v-if="job">
        <el-divider />
        <el-descriptions title="任务状态" :column="3" border>
          <el-descriptions-item label="任务 ID">{{ job.job_id }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="statusType(job.status)">{{ job.status }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="精度">
            {{ job.accuracy != null ? (job.accuracy * 100).toFixed(2) + '%' : '-' }}
          </el-descriptions-item>
        </el-descriptions>

        <div style="margin-top:16px;">
          <span style="font-size:13px;color:#606266;">进度：{{ job.done }} / {{ job.total }}</span>
          <el-progress
            :percentage="job.total > 0 ? Math.round(job.done/job.total*100) : 0"
            :status="job.status==='done' ? 'success' : (job.status==='failed' ? 'exception' : undefined)"
            style="margin-top:8px;"
          />
        </div>

        <el-table v-if="report" :data="report.results?.slice(0,50)" style="width:100%;margin-top:16px;" size="small">
          <el-table-column label="文件" show-overflow-tooltip>
            <template #default="{row}">{{ row.file?.split('/').pop() }}</template>
          </el-table-column>
          <el-table-column label="结果" show-overflow-tooltip>
            <template #default="{row}">{{ JSON.stringify(row).substring(0,80) }}</template>
          </el-table-column>
        </el-table>
        <div v-if="report?.results?.length > 50" style="margin-top:8px;color:#909399;font-size:12px;">
          仅显示前 50 条，完整结果已保存至服务器日志。
        </div>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { batchInfer, getBatchJob, getBatchReport } from '../api/index.js'

const route = useRoute()
const form = ref({
  capability:   route.query.capability || '',
  version:      route.query.version    || '',
  dataset_path: '',
})
const submitting = ref(false)
const job    = ref(null)
const report = ref(null)
let pollTimer = null

const statusType = (s) => ({ running:'primary', done:'success', failed:'danger', pending:'info' }[s] || 'info')

const poll = async () => {
  if (!job.value) return
  try {
    const r = await getBatchJob(job.value.job_id)
    job.value = r.data
    if (r.data.status === 'done') {
      clearInterval(pollTimer)
      const rr = await getBatchReport(job.value.job_id)
      report.value = rr.data
    } else if (r.data.status === 'failed') {
      clearInterval(pollTimer)
    }
  } catch { /* ignore */ }
}

const doSubmit = async () => {
  submitting.value = true
  try {
    const res = await batchInfer(form.value)
    job.value = res.data
    report.value = null
    pollTimer = setInterval(poll, 1000)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    submitting.value = false
  }
}

onBeforeUnmount(() => { if (pollTimer) clearInterval(pollTimer) })
</script>
