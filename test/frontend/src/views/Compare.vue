<template>
  <div>
    <el-card shadow="never" header="模型版本对比">
      <el-form :model="form" label-width="100px" style="max-width:560px;">
        <el-form-item label="AI 能力">
          <el-input v-model="form.capability" placeholder="如 desktop_recapture_detect" />
        </el-form-item>
        <el-form-item label="版本 A">
          <el-input v-model="form.version_a" placeholder="如 1.0.0" />
        </el-form-item>
        <el-form-item label="版本 B">
          <el-input v-model="form.version_b" placeholder="如 1.1.0" />
        </el-form-item>
        <el-form-item label="数据集路径">
          <el-input v-model="form.dataset_path" placeholder="/workspace/datasets/desktop_recapture_detect/test" />
        </el-form-item>
        <el-form-item label="最大样本数">
          <el-input-number v-model="form.max_samples" :min="1" :max="100" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="doCompare" :loading="loading">开始对比</el-button>
        </el-form-item>
      </el-form>

      <template v-if="result">
        <el-divider />
        <p style="margin-bottom:12px;color:#606266;">
          共对比 <b>{{ result.count }}</b> 个样本：
          版本 <el-tag size="small">{{ result.version_a }}</el-tag> 对比
          <el-tag size="small" type="success">{{ result.version_b }}</el-tag>
        </p>
        <el-table :data="result.comparisons" style="width:100%" size="small">
          <el-table-column label="文件" show-overflow-tooltip width="200">
            <template #default="{row}">{{ row.file?.split('/').pop() }}</template>
          </el-table-column>
          <el-table-column :label="`版本 A (${result.version_a})`">
            <template #default="{row}">
              <span :class="differs(row) ? 'diff' : ''">
                {{ summarize(row.result_a) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column :label="`版本 B (${result.version_b})`">
            <template #default="{row}">
              <span :class="differs(row) ? 'diff' : ''">
                {{ summarize(row.result_b) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="是否一致" width="90">
            <template #default="{row}">
              <el-tag :type="differs(row) ? 'danger' : 'success'" size="small">
                {{ differs(row) ? '不一致' : '一致' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { compareVersions, extractErrorMessage, buildUnauthorizedTroubleshootingMessage } from '../api/index.js'

const form = ref({ capability: '', version_a: '', version_b: '', dataset_path: '', max_samples: 20 })
const loading = ref(false)
const result = ref(null)

const summarize = (r) => {
  if (!r) return '-'
  if ('label' in r) return `${r.label} (${r.score_recaptured ?? r.top_score ?? ''})`
  if ('face_detected' in r) return `face: ${r.face_detected ? '是' : '否'}`
  if ('top_class' in r) return `class ${r.top_class}: ${r.top_score}`
  return JSON.stringify(r).substring(0, 40)
}

const differs = (row) => summarize(row.result_a) !== summarize(row.result_b)

const doCompare = async () => {
  loading.value = true
  result.value  = null
  try {
    const res = await compareVersions(form.value)
    result.value = res.data
  } catch (e) {
    const msg = e?.response?.status === 401
      ? buildUnauthorizedTroubleshootingMessage('版本对比')
      : '对比失败：' + extractErrorMessage(e)
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.diff { color: #f56c6c; font-weight: 600; }
</style>
