<template>
  <div>
    <el-card shadow="hover">
      <template #header>
        <span style="font-size:16px;font-weight:bold;">
          {{ isEdit ? '✏️ 编辑编排' : '➕ 新建编排' }}
        </span>
      </template>

      <el-form :model="form" label-width="140px" style="max-width:800px;">
        <el-form-item label="编排 ID">
          <el-input v-model="form.pipeline_id" :disabled="isEdit" placeholder="唯一标识，如 my-pipeline" />
        </el-form-item>
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="编排名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选描述" />
        </el-form-item>
      </el-form>

      <el-divider>编排步骤</el-divider>

      <div v-for="(step, idx) in form.steps" :key="step._key" style="margin-bottom:16px;">
        <el-card shadow="never" style="border:1px solid #dcdfe6;">
          <template #header>
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span>步骤 {{ idx + 1 }}：{{ step.step_id || '(未命名)' }}</span>
              <el-button type="danger" size="small" @click="removeStep(idx)">
                <el-icon><Delete /></el-icon> 删除
              </el-button>
            </div>
          </template>

          <el-form label-width="120px">
            <el-form-item label="步骤 ID">
              <el-input v-model="step.step_id" placeholder="自动生成或自定义" />
            </el-form-item>
            <el-form-item label="推理能力">
              <el-select v-model="step.capability" placeholder="选择能力" filterable style="width:100%;">
                <el-option v-for="cap in capabilities" :key="cap" :label="cap" :value="cap" />
              </el-select>
            </el-form-item>
            <el-form-item label="失败策略">
              <el-select v-model="step.on_failure" style="width:100%;">
                <el-option label="中止 (abort)" value="abort" />
                <el-option label="跳过 (skip)" value="skip" />
                <el-option label="使用默认值 (default)" value="default" />
              </el-select>
            </el-form-item>
            <el-form-item label="执行条件">
              <el-input v-model="step.condition" placeholder="可选，如 prev.score > 0.5" />
            </el-form-item>
            <el-form-item label="附加参数">
              <el-input v-model="step.options_str" type="textarea" :rows="2" placeholder='可选 JSON，如 {"threshold": 0.5}' />
            </el-form-item>
          </el-form>
        </el-card>
      </div>

      <el-button @click="addStep" style="margin-bottom:20px;">
        <el-icon><Plus /></el-icon> 添加步骤
      </el-button>

      <el-divider />

      <div style="display:flex;gap:12px;">
        <el-button type="warning" :loading="validating" :disabled="!form.pipeline_id" @click="doValidate">
          ✅ 验证
        </el-button>
        <el-button type="primary" :loading="saving" :disabled="!form.pipeline_id || !form.name" @click="doSave">
          💾 保存
        </el-button>
        <el-button @click="$router.push('/pipelines')">取消</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  getCapabilities,
  getPipeline,
  createPipeline,
  updatePipeline,
  validatePipeline,
  extractErrorMessage,
} from '../api/index.js'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()

const isEdit = computed(() => !!route.params.id)
const capabilities = ref([])
const saving = ref(false)
const validating = ref(false)
let stepCounter = 0

const form = ref({
  pipeline_id: '',
  name: '',
  description: '',
  steps: [],
})

function makeStep() {
  stepCounter++
  return {
    _key: Date.now() + stepCounter,
    step_id: `step_${stepCounter}`,
    capability: '',
    on_failure: 'abort',
    condition: '',
    options_str: '',
  }
}

function addStep() {
  form.value.steps.push(makeStep())
}

function removeStep(idx) {
  form.value.steps.splice(idx, 1)
}

function buildPayload() {
  const steps = form.value.steps.map(s => {
    const step = {
      step_id: s.step_id,
      capability: s.capability,
      on_failure: s.on_failure,
    }
    if (s.condition) step.condition = s.condition
    if (s.options_str && s.options_str.trim()) {
      try {
        step.options = JSON.parse(s.options_str)
      } catch {
        throw new Error(`步骤「${s.step_id}」的附加参数不是有效 JSON`)
      }
    }
    return step
  })
  return {
    pipeline_id: form.value.pipeline_id,
    name: form.value.name,
    description: form.value.description,
    steps,
  }
}

async function doValidate() {
  if (!isEdit.value) {
    ElMessage.warning('请先保存编排再验证')
    return
  }
  validating.value = true
  try {
    await validatePipeline(route.params.id)
    ElMessage.success('验证通过')
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  } finally {
    validating.value = false
  }
}

async function doSave() {
  saving.value = true
  try {
    const payload = buildPayload()
    if (isEdit.value) {
      await updatePipeline(route.params.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createPipeline(payload)
      ElMessage.success('创建成功')
    }
    router.push('/pipelines')
  } catch (e) {
    ElMessage.error(typeof e === 'string' ? e : (e.message || extractErrorMessage(e)))
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  try {
    const capRes = await getCapabilities()
    const data = capRes.data
    const raw = Array.isArray(data) ? data : (data.capabilities || [])
    capabilities.value = raw.map(c => typeof c === 'string' ? c : c.capability)
  } catch (e) {
    ElMessage.error(extractErrorMessage(e))
  }

  if (isEdit.value) {
    try {
      const res = await getPipeline(route.params.id)
      const p = res.data
      form.value.pipeline_id = p.pipeline_id
      form.value.name = p.name || ''
      form.value.description = p.description || ''
      form.value.steps = (p.steps || []).map(s => {
        stepCounter++
        return {
          _key: Date.now() + stepCounter,
          step_id: s.step_id || '',
          capability: s.capability || '',
          on_failure: s.on_failure || 'abort',
          condition: s.condition || '',
          options_str: s.options ? JSON.stringify(s.options, null, 2) : '',
        }
      })
    } catch (e) {
      ElMessage.error(extractErrorMessage(e))
    }
  }
})
</script>
