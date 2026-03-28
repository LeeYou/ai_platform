<template>
  <div>
    <el-card>
      <template #header><span>➕ 生成授权</span></template>

      <el-steps :active="step" finish-status="success" style="margin-bottom:32px;">
        <el-step title="选择客户" />
        <el-step title="配置授权" />
        <el-step title="机器绑定 & 确认" />
      </el-steps>

      <!-- Step 0: Select Customer -->
      <div v-if="step === 0">
        <el-form label-width="110px" style="max-width:500px;">
          <el-form-item label="选择客户" required>
            <el-select v-model="form.customer_id" filterable placeholder="请选择客户" style="width:100%;">
              <el-option v-for="c in customerOptions" :key="c.customer_id" :label="c.name" :value="c.customer_id" />
            </el-select>
          </el-form-item>
        </el-form>
        <el-button type="primary" @click="nextStep" :disabled="!form.customer_id">下一步</el-button>
      </div>

      <!-- Step 1: Configure License -->
      <div v-if="step === 1">
        <el-form :model="form" ref="configFormRef" label-width="130px" style="max-width:600px;">
          <el-form-item label="授权类型" prop="license_type" :rules="[{required:true,message:'请选择类型'}]">
            <el-select v-model="form.license_type" style="width:100%;">
              <el-option label="试用版 (trial)" value="trial" />
              <el-option label="商业版 (commercial)" value="commercial" />
              <el-option label="永久版 (permanent)" value="permanent" />
            </el-select>
          </el-form-item>
          <el-form-item label="功能能力">
            <el-checkbox v-model="form.allCapabilities" @change="toggleAll" label="全部功能 (*)" />
            <el-divider direction="vertical" />
            <el-checkbox-group v-model="form.capabilities" :disabled="form.allCapabilities">
              <el-checkbox value="face_detect" label="face_detect" />
              <el-checkbox value="handwriting_reco" label="handwriting_reco" />
              <el-checkbox value="recapture_detect" label="recapture_detect" />
              <el-checkbox value="id_card_classify" label="id_card_classify" />
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="生效日期" prop="valid_from" :rules="[{required:true,message:'请选择生效日期'}]">
            <el-date-picker v-model="form.valid_from" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%;" />
          </el-form-item>
          <el-form-item v-if="form.license_type !== 'permanent'" label="到期日期" prop="valid_until" :rules="[{required:true,message:'请选择到期日期'}]">
            <el-date-picker v-model="form.valid_until" type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width:100%;" />
          </el-form-item>
          <el-form-item label="最大实例数">
            <el-input-number v-model="form.max_instances" :min="1" :max="999" />
          </el-form-item>
          <el-form-item label="版本约束">
            <el-input v-model="form.version_constraint" placeholder="如 >=1.0.0,<2.0.0（可选）" />
          </el-form-item>
        </el-form>
        <el-button @click="step--" style="margin-right:8px;">上一步</el-button>
        <el-button type="primary" @click="nextStep">下一步</el-button>
      </div>

      <!-- Step 2: Machine Binding & Review -->
      <div v-if="step === 2">
        <el-form :model="form" ref="bindFormRef" label-width="130px" style="max-width:600px;">
          <el-form-item label="机器指纹">
            <el-input v-model="form.machine_fingerprint" placeholder="可选，留空表示不绑定机器" />
          </el-form-item>
          <el-form-item label="私钥文件路径" prop="privkey_path" :rules="[{required:true,message:'请输入私钥文件路径'}]">
            <el-input v-model="form.privkey_path" placeholder="/path/to/private_key.pem" />
          </el-form-item>
        </el-form>

        <el-descriptions title="授权摘要" :column="2" border style="max-width:600px;margin:20px 0;">
          <el-descriptions-item label="客户">{{ customerName }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ form.license_type }}</el-descriptions-item>
          <el-descriptions-item label="功能">{{ form.allCapabilities ? '*（全部）' : form.capabilities.join(', ') }}</el-descriptions-item>
          <el-descriptions-item label="生效日期">{{ form.valid_from }}</el-descriptions-item>
          <el-descriptions-item label="到期日期">{{ form.license_type === 'permanent' ? '永久' : form.valid_until }}</el-descriptions-item>
          <el-descriptions-item label="最大实例">{{ form.max_instances }}</el-descriptions-item>
          <el-descriptions-item label="机器指纹">{{ form.machine_fingerprint || '不绑定' }}</el-descriptions-item>
        </el-descriptions>

        <el-button @click="step--" style="margin-right:8px;">上一步</el-button>
        <el-button type="success" @click="handleSubmit" :loading="submitting">生成并下载授权</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { getCustomers, createLicense, downloadLicense, extractErrorMessage } from '../api/index.js'

const step = ref(0)
const submitting = ref(false)
const customerOptions = ref([])
const configFormRef = ref()
const bindFormRef = ref()

const form = ref({
  customer_id: '',
  license_type: 'commercial',
  allCapabilities: false,
  capabilities: [],
  valid_from: '',
  valid_until: '',
  max_instances: 1,
  version_constraint: '',
  machine_fingerprint: '',
  privkey_path: '',
})

const customerName = computed(() => {
  const c = customerOptions.value.find(x => x.customer_id === form.value.customer_id)
  return c ? c.name : form.value.customer_id
})

function toggleAll(val) {
  if (val) form.value.capabilities = []
}

async function nextStep() {
  if (step.value === 1) {
    await configFormRef.value.validate()
  }
  step.value++
}

async function handleSubmit() {
  await bindFormRef.value.validate()
  submitting.value = true
  try {
    const payload = {
      customer_id: form.value.customer_id,
      license_type: form.value.license_type,
      capabilities: form.value.allCapabilities ? ['*'] : form.value.capabilities,
      valid_from: form.value.valid_from,
      valid_until: form.value.license_type === 'permanent' ? null : form.value.valid_until,
      max_instances: form.value.max_instances,
      version_constraint: form.value.version_constraint || null,
      machine_fingerprint: form.value.machine_fingerprint || null,
      privkey_path: form.value.privkey_path,
    }
    const res = await createLicense(payload)
    const licenseId = res.data?.license_id ?? res.data?.id
    ElMessage.success('授权生成成功，正在下载...')

    if (licenseId) {
      const dlRes = await downloadLicense(licenseId)
      const url = URL.createObjectURL(new Blob([dlRes.data]))
      const a = document.createElement('a')
      a.href = url
      a.download = `license_${licenseId}.bin`
      a.click()
      URL.revokeObjectURL(url)
    }

    // reset
    step.value = 0
    form.value = {
      customer_id: '', license_type: 'commercial', allCapabilities: false,
      capabilities: [], valid_from: '', valid_until: '', max_instances: 1,
      version_constraint: '', machine_fingerprint: '', privkey_path: '',
    }
  } catch (e) {
    ElMessage.error('生成授权失败：' + extractErrorMessage(e))
  } finally {
    submitting.value = false
  }
}

async function loadCustomers() {
  try {
    const res = await getCustomers(1, 200)
    customerOptions.value = res.data?.items ?? res.data ?? []
  } catch {}
}

onMounted(loadCustomers)
</script>
