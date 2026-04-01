<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <span style="font-size:16px;font-weight:bold;">🧪 编排测试</span>
      </template>

      <el-form label-width="140px" style="max-width:700px;">
        <el-form-item label="选择编排">
          <el-select
            v-model="selectedPipeline"
            placeholder="选择编排"
            filterable
            style="width:100%;"
          >
            <el-option
              v-for="p in pipelines"
              :key="p.pipeline_id"
              :label="`${p.name || p.pipeline_id} (${p.steps ? p.steps.length : 0} 步)`"
              :value="p.pipeline_id"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="上传图片">
          <el-upload
            :auto-upload="false"
            :limit="1"
            :on-change="onFileChange"
            :on-remove="onFileRemove"
            accept="image/*"
          >
            <el-button type="primary">
              <el-icon><Upload /></el-icon>
              选择文件
            </el-button>
          </el-upload>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="running"
            :disabled="!selectedPipeline || !imageFile"
            @click="doRun"
          >
            🚀 执行编排
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="result !== null" shadow="hover" style="margin-top:20px;">
      <template #header>
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:16px;font-weight:bold;">📋 编排结果</span>
          <el-tag :type="resultOk ? 'success' : 'danger'">{{ resultOk ? '成功' : '失败' }}</el-tag>
          <el-tag v-if="totalTime !== null" type="info">总耗时 {{ totalTime }} ms</el-tag>
        </div>
      </template>

      <div v-if="stepResults.length > 0" style="margin-bottom:16px;">
        <el-divider content-position="left">各步骤结果</el-divider>
        <el-timeline>
          <el-timeline-item
            v-for="(step, idx) in stepResults"
            :key="idx"
            :type="step.status === 'success' ? 'success' : step.status === 'skipped' ? 'info' : 'danger'"
          >
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
              <strong>{{ step.step_id || `步骤 ${idx + 1}` }}</strong>
              <el-tag size="small" :type="step.status === 'success' ? 'success' : step.status === 'skipped' ? 'info' : 'danger'">
                {{ step.status }}
              </el-tag>
              <el-tag size="small" type="info">{{ step.capability }}</el-tag>
              <el-tag v-if="step.time_ms != null" size="small">{{ step.time_ms }} ms</el-tag>
            </div>
            <el-input
              v-if="step.result"
              type="textarea"
              :rows="4"
              :model-value="JSON.stringify(step.result, null, 2)"
              readonly
              style="font-family:monospace;font-size:12px;"
            />
          </el-timeline-item>
        </el-timeline>
      </div>

      <el-divider content-position="left">最终结果</el-divider>
      <el-input
        type="textarea"
        :rows="10"
        :model-value="resultText"
        readonly
        style="font-family:monospace;font-size:12px;"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getPipelines, runPipeline, extractErrorMessage } from '../api/index.js'
import { ElMessage } from 'element-plus'

const route = useRoute()
const pipelines = ref([])
const selectedPipeline = ref('')
const imageFile = ref(null)
const running = ref(false)
const result = ref(null)
const resultOk = ref(false)
const resultText = ref('')
const totalTime = ref(null)
const stepResults = ref([])

function onFileChange(file) {
  imageFile.value = file.raw
}

function onFileRemove() {
  imageFile.value = null
}

async function doRun() {
  if (!selectedPipeline.value || !imageFile.value) {
    ElMessage.warning('请选择编排和上传图片')
    return
  }

  const formData = new FormData()
  formData.append('image', imageFile.value)

  running.value = true
  result.value = null
  stepResults.value = []
  const startTime = Date.now()

  try {
    const res = await runPipeline(selectedPipeline.value, formData)
    totalTime.value = Date.now() - startTime
    result.value = res.data
    resultOk.value = true
    resultText.value = JSON.stringify(res.data, null, 2)
    stepResults.value = res.data.steps || res.data.step_results || []
    ElMessage.success('编排执行完成')
  } catch (e) {
    totalTime.value = Date.now() - startTime
    resultOk.value = false
    result.value = e?.response?.data || e.message
    resultText.value = JSON.stringify(result.value, null, 2)
    stepResults.value = []
    ElMessage.error(extractErrorMessage(e))
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  try {
    const res = await getPipelines()
    pipelines.value = Array.isArray(res.data) ? res.data : (res.data.pipelines || [])
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }

  if (route.query.id) {
    selectedPipeline.value = route.query.id
  }
})
</script>
