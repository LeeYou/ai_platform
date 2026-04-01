<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <span style="font-size:16px;font-weight:bold;">🧪 API 推理测试</span>
      </template>

      <el-form label-width="140px" style="max-width:700px;">
        <el-form-item label="推理能力">
          <el-select
            v-model="capability"
            placeholder="选择推理能力"
            filterable
            style="width:100%;"
          >
            <el-option
              v-for="cap in capabilities"
              :key="cap"
              :label="cap"
              :value="cap"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="上传图片">
          <el-upload
            ref="uploadRef"
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
            <template #tip>
              <div style="color:#909399;font-size:12px;">支持常见图片格式</div>
            </template>
          </el-upload>
        </el-form-item>

        <el-form-item label="附加参数 (JSON)">
          <el-input
            v-model="optionsStr"
            type="textarea"
            :rows="4"
            placeholder='可选，如 {"threshold": 0.5}'
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="running"
            :disabled="!capability || !imageFile"
            @click="doInfer"
          >
            🚀 执行推理
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card v-if="result !== null" shadow="hover" style="margin-top:20px;">
      <template #header>
        <div style="display:flex;align-items:center;gap:12px;">
          <span style="font-size:16px;font-weight:bold;">📋 推理结果</span>
          <el-tag :type="resultOk ? 'success' : 'danger'">{{ resultOk ? '成功' : '失败' }}</el-tag>
          <el-tag v-if="inferTime !== null" type="info">耗时 {{ inferTime }} ms</el-tag>
        </div>
      </template>
      <el-input
        type="textarea"
        :rows="15"
        :model-value="resultText"
        readonly
        style="font-family:monospace;font-size:12px;"
      />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getCapabilities, infer, extractErrorMessage } from '../api/index.js'
import { ElMessage } from 'element-plus'

const capabilities = ref([])
const capability = ref('')
const imageFile = ref(null)
const optionsStr = ref('')
const running = ref(false)
const result = ref(null)
const resultOk = ref(false)
const resultText = ref('')
const inferTime = ref(null)
const uploadRef = ref(null)

function onFileChange(file) {
  imageFile.value = file.raw
}

function onFileRemove() {
  imageFile.value = null
}

async function doInfer() {
  if (!capability.value || !imageFile.value) {
    ElMessage.warning('请选择能力和上传图片')
    return
  }

  const formData = new FormData()
  formData.append('image', imageFile.value)

  if (optionsStr.value.trim()) {
    try {
      JSON.parse(optionsStr.value)
      formData.append('options', optionsStr.value.trim())
    } catch {
      ElMessage.error('附加参数不是有效的 JSON')
      return
    }
  }

  running.value = true
  result.value = null
  const startTime = Date.now()

  try {
    const res = await infer(capability.value, formData)
    inferTime.value = Date.now() - startTime
    result.value = res.data
    resultOk.value = true
    resultText.value = JSON.stringify(res.data, null, 2)
    ElMessage.success('推理完成')
  } catch (e) {
    inferTime.value = Date.now() - startTime
    resultOk.value = false
    result.value = e?.response?.data || e.message
    resultText.value = JSON.stringify(result.value, null, 2)
    ElMessage.error(extractErrorMessage(e))
  } finally {
    running.value = false
  }
}

onMounted(async () => {
  try {
    const res = await getCapabilities()
    const data = res.data
    // Backend returns {capabilities: [{capability: "name", version: "...", ...}]}
    const raw = Array.isArray(data) ? data : (data.capabilities || [])
    capabilities.value = raw.map(c => typeof c === 'string' ? c : c.capability)
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }
})
</script>
