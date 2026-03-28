<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>AI 能力配置</span>
          <el-button type="primary" :icon="Plus" @click="openAdd">新增能力</el-button>
        </div>
      </template>

      <el-table :data="capabilities" style="width:100%" v-loading="loading">
        <el-table-column prop="name" label="能力标识" width="140" />
        <el-table-column prop="name_cn" label="中文名称" width="120" />
        <el-table-column prop="description" label="描述" show-overflow-tooltip />
        <el-table-column prop="dataset_path" label="数据集路径" show-overflow-tooltip />
        <el-table-column prop="script_path" label="训练脚本" show-overflow-tooltip />
        <el-table-column label="操作" width="150">
          <template #default="{row}">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确定删除该能力？" @confirm="doDelete(row)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Add/Edit dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑能力' : '新增能力'" width="600px">
      <el-form :model="form" label-width="100px" ref="formRef">
        <el-form-item label="能力标识" prop="name" :rules="[{required:true,message:'必填'}]">
          <el-input v-model="form.name" :disabled="isEdit" placeholder="如 face_detect" />
        </el-form-item>
        <el-form-item label="中文名称">
          <el-input v-model="form.name_cn" placeholder="如 人脸检测" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="数据集路径">
          <el-input v-model="form.dataset_path" placeholder="/workspace/datasets/face_detect" />
        </el-form-item>
        <el-form-item label="训练脚本">
          <el-input v-model="form.script_path" placeholder="scripts/face_detect/train.py" />
        </el-form-item>
        <el-form-item label="超参数 (JSON)">
          <el-input
            v-model="form.hyperparams"
            type="textarea"
            :rows="6"
            :class="{ 'json-error': jsonError }"
            @input="validateJson"
            placeholder="{}"
          />
          <div v-if="jsonError" style="color:#f56c6c;font-size:12px;margin-top:4px;">{{ jsonError }}</div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="doSave" :disabled="!!jsonError">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { listCapabilities, createCapability, updateCapability, deleteCapability, extractErrorMessage } from '../api/index.js'

const loading = ref(false)
const capabilities = ref([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const jsonError = ref('')
const formRef = ref(null)

const form = ref({
  name: '', name_cn: '', description: '', dataset_path: '', script_path: '', hyperparams: '{}'
})

const validateJson = () => {
  try { JSON.parse(form.value.hyperparams); jsonError.value = '' } catch (e) { jsonError.value = e.message }
}

const openAdd = () => {
  isEdit.value = false
  editId.value = null
  form.value = { name: '', name_cn: '', description: '', dataset_path: '', script_path: '', hyperparams: '{}' }
  jsonError.value = ''
  dialogVisible.value = true
}

const openEdit = (row) => {
  isEdit.value = true
  editId.value = row.id
  form.value = {
    name: row.name,
    name_cn: row.name_cn,
    description: row.description,
    dataset_path: row.dataset_path,
    script_path: row.script_path,
    hyperparams: typeof row.hyperparams === 'string' ? row.hyperparams : JSON.stringify(row.hyperparams, null, 2)
  }
  jsonError.value = ''
  dialogVisible.value = true
}

const doSave = async () => {
  if (jsonError.value) return
  try {
    if (isEdit.value) {
      await updateCapability(editId.value, form.value)
      ElMessage.success('更新成功')
    } else {
      await createCapability(form.value)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    await load()
  } catch (e) {
    ElMessage.error('操作失败：' + extractErrorMessage(e))
  }
}

const doDelete = async (row) => {
  try {
    await deleteCapability(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error('删除失败：' + extractErrorMessage(e))
  }
}

const load = async () => {
  loading.value = true
  try {
    const res = await listCapabilities()
    capabilities.value = res.data
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
