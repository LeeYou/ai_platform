<template>
  <div>
    <el-card shadow="never" header="单样本推理测试">
      <el-form :model="form" label-width="100px" style="max-width:520px;">
        <el-form-item label="AI 能力">
          <el-input v-model="form.capability" placeholder="如 recapture_detect" />
        </el-form-item>
        <el-form-item label="模型版本">
          <el-input v-model="form.version" placeholder="如 1.0.0" />
        </el-form-item>
        <el-form-item label="测试图片">
          <el-upload
            :auto-upload="false"
            :on-change="onFileChange"
            :limit="1"
            accept="image/*"
            list-type="picture-card"
          >
            <el-icon><Plus /></el-icon>
            <template #tip><div style="font-size:12px;color:#909399;">JPG / PNG / BMP</div></template>
          </el-upload>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doInfer" :loading="loading"
                     :disabled="!form.capability||!form.version||!selectedFile">
            开始推理
          </el-button>
        </el-form-item>
      </el-form>

      <el-divider v-if="result" />

      <el-row v-if="result" :gutter="24">
        <el-col :span="12">
          <el-card shadow="never" header="可视化结果">
            <img v-if="visImage" :src="`data:image/jpeg;base64,${visImage}`"
                 style="width:100%;border-radius:4px;" />
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never" header="推理结果">
            <el-descriptions :column="1" border size="small">
              <el-descriptions-item v-for="(v,k) in result" :key="k" :label="String(k)">
                {{ typeof v === 'boolean' ? (v ? '是' : '否') : v }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { singleInfer, extractErrorMessage } from '../api/index.js'

const route = useRoute()
const form = ref({
  capability: route.query.capability || '',
  version:    route.query.version    || '',
})
const selectedFile = ref(null)
const loading = ref(false)
const result = ref(null)
const visImage = ref(null)

const onFileChange = (file) => { selectedFile.value = file.raw }

const doInfer = async () => {
  if (!selectedFile.value) return
  loading.value = true
  result.value  = null
  visImage.value = null
  try {
    const fd = new FormData()
    fd.append('capability', form.value.capability)
    fd.append('version',    form.value.version)
    fd.append('file',       selectedFile.value)
    const res = await singleInfer(fd)
    result.value   = res.data.result
    visImage.value = res.data.vis_image
  } catch (e) {
    ElMessage.error('推理失败：' + extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}
</script>
