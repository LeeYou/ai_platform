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
          <el-form-item label="操作系统" prop="operating_system" :rules="[{required:true,message:'请选择操作系统'}]">
            <el-select v-model="form.operating_system" placeholder="请选择操作系统" style="width:100%;">
              <el-option label="Windows" value="windows" />
              <el-option label="Linux" value="linux" />
              <el-option label="Android" value="android" />
              <el-option label="iOS" value="ios" />
            </el-select>
          </el-form-item>
          <el-form-item label="应用名称" prop="application_name" :rules="[{required:true,message:'请输入应用名称'}]">
            <el-input v-model="form.application_name" placeholder="仅用于标识授权对应的应用" />
          </el-form-item>
          <el-form-item label="签名密钥对" prop="key_pair_id" :rules="[{required:true,message:'请选择签名密钥对'}]">
            <el-select v-model="form.key_pair_id" filterable placeholder="选择该客户的密钥对" style="width:100%;">
              <el-option v-for="k in keyPairOptions" :key="k.id" :label="k.name" :value="k.id" />
            </el-select>
            <div style="color:#909399;font-size:12px;margin-top:4px;">
              一客户一密钥对：请选择该客户专属的密钥对
            </div>
            <div v-if="unavailableKeyPairCount" style="color:#E6A23C;font-size:12px;margin-top:4px;">
              {{ unavailableKeyPairCount }} 个启用中的密钥对因私钥缺失已自动隐藏，请先在“密钥管理”中补充可用密钥对。
            </div>
          </el-form-item>
          <el-form-item label="功能能力">
            <el-checkbox v-model="form.allCapabilities" @change="toggleAll" label="全部功能 (*)" />
            <el-divider direction="vertical" />
            <el-checkbox-group v-model="form.capabilities" :disabled="form.allCapabilities">
              <el-checkbox v-for="cap in capabilityOptions" :key="cap" :value="cap" :label="cap" />
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
          <el-form-item label="最低系统版本">
            <el-input v-model="form.minimum_os_version" placeholder="可选，不填表示不限制，如 22.04 / 10.0.19045" />
          </el-form-item>
          <el-form-item label="系统架构">
            <el-select v-model="form.system_architecture" clearable placeholder="可选，不填表示不限制" style="width:100%;">
              <el-option label="x86_64" value="x86_64" />
              <el-option label="arm64" value="arm64" />
              <el-option label="x86" value="x86" />
              <el-option label="armv7" value="armv7" />
            </el-select>
          </el-form-item>
        </el-form>
        <el-button @click="step--" style="margin-right:8px;">上一步</el-button>
        <el-button type="primary" @click="nextStep">下一步</el-button>
      </div>

      <!-- Step 2: Machine Binding & Review -->
      <div v-if="step === 2">
        <el-form :model="form" label-width="130px" style="max-width:600px;">
          <el-form-item label="机器指纹">
            <el-input v-model="form.machine_fingerprint" placeholder="可选，留空表示不绑定机器" />
          </el-form-item>
        </el-form>

        <el-descriptions title="授权摘要" :column="2" border style="max-width:600px;margin:20px 0;">
          <el-descriptions-item label="客户">{{ customerName }}</el-descriptions-item>
          <el-descriptions-item label="签名密钥">{{ keyPairName }}</el-descriptions-item>
          <el-descriptions-item label="类型">{{ form.license_type }}</el-descriptions-item>
          <el-descriptions-item label="操作系统">{{ form.operating_system || '-' }}</el-descriptions-item>
          <el-descriptions-item label="应用名称">{{ form.application_name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="功能">{{ form.allCapabilities ? '*（全部）' : form.capabilities.join(', ') }}</el-descriptions-item>
          <el-descriptions-item label="生效日期">{{ form.valid_from }}</el-descriptions-item>
          <el-descriptions-item label="到期日期">{{ form.license_type === 'permanent' ? '永久' : form.valid_until }}</el-descriptions-item>
          <el-descriptions-item label="最大实例">{{ form.max_instances }}</el-descriptions-item>
          <el-descriptions-item label="最低系统版本">{{ form.minimum_os_version || '不限制' }}</el-descriptions-item>
          <el-descriptions-item label="系统架构">{{ form.system_architecture || '不限制' }}</el-descriptions-item>
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
import { getCustomers, getKeys, getCapabilities, createLicense, downloadLicense, extractErrorMessage } from '../api/index.js'

const step = ref(0)
const submitting = ref(false)
const customerOptions = ref([])
const keyPairOptions = ref([])
const capabilityOptions = ref([])
const configFormRef = ref()
const unavailableKeyPairCount = ref(0)

  const form = ref({
    customer_id: '',
    key_pair_id: null,
    license_type: 'commercial',
    operating_system: '',
    application_name: '',
    allCapabilities: false,
    capabilities: [],
    valid_from: '',
    valid_until: '',
    max_instances: 1,
    version_constraint: '',
    minimum_os_version: '',
    system_architecture: '',
    machine_fingerprint: '',
  })

const customerName = computed(() => {
  const c = customerOptions.value.find(x => x.customer_id === form.value.customer_id)
  return c ? c.name : form.value.customer_id
})

const keyPairName = computed(() => {
  const k = keyPairOptions.value.find(x => x.id === form.value.key_pair_id)
  return k ? k.name : '-'
})

function toggleAll(val) {
  if (val) form.value.capabilities = []
}

function isPrivateKeyUnavailable(keyPair) {
  return keyPair?.private_key_available === false
}

async function nextStep() {
  if (step.value === 1) {
    await configFormRef.value.validate()
  }
  step.value++
}

async function handleSubmit() {
  submitting.value = true
  try {
    const payload = {
      customer_id: form.value.customer_id,
      key_pair_id: form.value.key_pair_id,
      license_type: form.value.license_type,
      operating_system: form.value.operating_system,
      application_name: form.value.application_name,
      capabilities: form.value.allCapabilities ? ['*'] : form.value.capabilities,
      valid_from: form.value.valid_from,
      valid_until: form.value.license_type === 'permanent' ? null : form.value.valid_until,
      max_instances: form.value.max_instances,
      version_constraint: form.value.version_constraint || null,
      minimum_os_version: form.value.minimum_os_version || null,
      system_architecture: form.value.system_architecture || null,
      machine_fingerprint: form.value.machine_fingerprint || null,
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
      customer_id: '', key_pair_id: null, license_type: 'commercial', operating_system: '', application_name: '', allCapabilities: false,
      capabilities: [], valid_from: '', valid_until: '', max_instances: 1,
      version_constraint: '', minimum_os_version: '', system_architecture: '', machine_fingerprint: '',
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

async function loadKeyPairs() {
  try {
    const res = await getKeys()
    const all = res.data?.items ?? res.data ?? []
    unavailableKeyPairCount.value = all.filter(k => k.is_active && isPrivateKeyUnavailable(k)).length
    keyPairOptions.value = all.filter(k => k.is_active && !isPrivateKeyUnavailable(k))
    if (!keyPairOptions.value.some(k => k.id === form.value.key_pair_id)) {
      form.value.key_pair_id = null
    }
    if (unavailableKeyPairCount.value > 0) {
      ElMessage.warning(`有 ${unavailableKeyPairCount.value} 个启用中的密钥对因私钥缺失不可用于生成授权，请重新生成或改选其他密钥对`)
    }
  } catch {}
}

async function loadCapabilities() {
  try {
    const res = await getCapabilities()
    capabilityOptions.value = res.data?.map(c => c.name) ?? []
  } catch (e) {
    ElMessage.warning('加载能力列表失败：' + extractErrorMessage(e))
  }
}

onMounted(() => {
  loadCustomers()
  loadKeyPairs()
  loadCapabilities()
})
</script>
