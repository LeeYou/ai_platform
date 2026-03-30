<template>
  <div>
    <el-card shadow="never">
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>样本标注项目</span>
          <el-button type="primary" :icon="Plus" @click="openAdd">新建标注项目</el-button>
        </div>
      </template>

      <el-table :data="projects" style="width:100%" v-loading="loading">
        <el-table-column prop="name" label="项目名称" width="180">
          <template #default="{row}">
            <el-link type="primary" @click="$router.push(`/annotations/${row.id}`)">{{ row.name }}</el-link>
          </template>
        </el-table-column>
        <el-table-column label="AI能力" width="120">
          <template #default="{row}">
            {{ capabilityMap[row.capability_id] || row.capability_id }}
          </template>
        </el-table-column>
        <el-table-column label="标注类型" width="120">
          <template #default="{row}">
            <el-tag size="small">{{ typeLabels[row.annotation_type] || row.annotation_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="network_type" label="网络选型" width="120" />
        <el-table-column label="标注进度" width="200">
          <template #default="{row}">
            <el-progress :percentage="row.total_samples > 0 ? Math.round(row.annotated_samples / row.total_samples * 100) : 0" :stroke-width="12" />
            <span style="font-size:12px;color:#999;">{{ row.annotated_samples }}/{{ row.total_samples }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{row}">
            <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="260">
          <template #default="{row}">
            <el-button link type="primary" @click="$router.push(`/annotations/${row.id}`)">开始标注</el-button>
            <el-button link type="success" @click="doExport(row)">导出</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确定删除该标注项目？所有标注记录将被删除。" @confirm="doDelete(row)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑标注项目' : '新建标注项目'" width="650px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="项目名称" required>
          <el-input v-model="form.name" placeholder="如：活体检测v2标注" />
        </el-form-item>
        <el-form-item label="AI能力" required>
          <el-select v-model="form.capability_id" placeholder="选择关联的AI能力" style="width:100%;">
            <el-option v-for="c in capabilities" :key="c.id" :label="`${c.name_cn || c.name} (${c.name})`" :value="c.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="标注类型" required>
          <el-select v-model="form.annotation_type" placeholder="选择标注类型" style="width:100%;" :disabled="isEdit">
            <el-option label="二分类" value="binary_classification" />
            <el-option label="多分类" value="multi_classification" />
            <el-option label="目标检测" value="object_detection" />
            <el-option label="OCR文字识别" value="ocr" />
            <el-option label="图像分割" value="segmentation" />
          </el-select>
        </el-form-item>
        <el-form-item label="神经网络选型">
          <el-select v-model="form.network_type" placeholder="选择或输入网络类型" filterable allow-create style="width:100%;">
            <el-option-group label="分类网络">
              <el-option label="ResNet18" value="resnet18" />
              <el-option label="ResNet50" value="resnet50" />
              <el-option label="MobileNetV3" value="mobilenetv3" />
              <el-option label="EfficientNet-B0" value="efficientnet_b0" />
            </el-option-group>
            <el-option-group label="检测网络">
              <el-option label="YOLOv8n" value="yolov8n" />
              <el-option label="YOLOv8s" value="yolov8s" />
              <el-option label="SSD-MobileNet" value="ssd_mobilenet" />
            </el-option-group>
            <el-option-group label="OCR网络">
              <el-option label="CRNN" value="crnn" />
              <el-option label="PP-OCRv4" value="ppocr_v4" />
            </el-option-group>
            <el-option-group label="分割网络">
              <el-option label="U-Net" value="unet" />
              <el-option label="DeepLabV3+" value="deeplabv3plus" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="数据集路径">
          <el-input v-model="form.dataset_path" placeholder="/workspace/datasets/face_detect" />
        </el-form-item>
        <el-form-item label="标签配置">
          <el-input v-model="form.label_config" type="textarea" :rows="6" :class="{ 'json-error': jsonError }" @input="validateJson" placeholder='{"labels": [{"id": 0, "name": "负样本"}, {"id": 1, "name": "正样本"}]}' />
          <div v-if="jsonError" style="color:#f56c6c;font-size:12px;margin-top:4px;">{{ jsonError }}</div>
        </el-form-item>
        <el-form-item label="状态" v-if="isEdit">
          <el-select v-model="form.status" style="width:100%;">
            <el-option label="进行中" value="in_progress" />
            <el-option label="已完成" value="completed" />
            <el-option label="已归档" value="archived" />
          </el-select>
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
import {
  listAnnotationProjects, createAnnotationProject, updateAnnotationProject,
  deleteAnnotationProject, exportAnnotations, listCapabilities, extractErrorMessage
} from '../api/index.js'

const loading = ref(false)
const projects = ref([])
const capabilities = ref([])
const capabilityMap = ref({})
const dialogVisible = ref(false)
const isEdit = ref(false)
const editId = ref(null)
const jsonError = ref('')

const typeLabels = {
  binary_classification: '二分类',
  multi_classification: '多分类',
  object_detection: '目标检测',
  ocr: 'OCR文字识别',
  segmentation: '图像分割',
}

const statusLabel = (s) => ({ in_progress: '进行中', completed: '已完成', archived: '已归档' }[s] || s)
const statusType = (s) => ({ in_progress: '', completed: 'success', archived: 'info' }[s] || 'info')

const form = ref({
  name: '', capability_id: null, annotation_type: '', network_type: '',
  dataset_path: '', label_config: '{"labels": []}', status: 'in_progress'
})

const validateJson = () => {
  try { JSON.parse(form.value.label_config); jsonError.value = '' } catch (e) { jsonError.value = e.message }
}

const openAdd = () => {
  isEdit.value = false; editId.value = null
  form.value = { name: '', capability_id: null, annotation_type: '', network_type: '', dataset_path: '', label_config: '{"labels": []}', status: 'in_progress' }
  jsonError.value = ''
  dialogVisible.value = true
}

const openEdit = (row) => {
  isEdit.value = true; editId.value = row.id
  form.value = {
    name: row.name, capability_id: row.capability_id, annotation_type: row.annotation_type,
    network_type: row.network_type, dataset_path: row.dataset_path,
    label_config: typeof row.label_config === 'string' ? row.label_config : JSON.stringify(row.label_config, null, 2),
    status: row.status
  }
  jsonError.value = ''
  dialogVisible.value = true
}

const doSave = async () => {
  if (jsonError.value) return
  try {
    if (isEdit.value) {
      const { capability_id, annotation_type, ...updateData } = form.value
      await updateAnnotationProject(editId.value, updateData)
      ElMessage.success('更新成功')
    } else {
      await createAnnotationProject(form.value)
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
    await deleteAnnotationProject(row.id)
    ElMessage.success('已删除')
    await load()
  } catch (e) {
    ElMessage.error('删除失败：' + extractErrorMessage(e))
  }
}

const doExport = async (row) => {
  try {
    const res = await exportAnnotations(row.id)
    ElMessage.success(res.data.message || '导出成功')
  } catch (e) {
    ElMessage.error('导出失败：' + extractErrorMessage(e))
  }
}

const load = async () => {
  loading.value = true
  try {
    const [projRes, capRes] = await Promise.all([listAnnotationProjects(), listCapabilities()])
    projects.value = projRes.data
    capabilities.value = capRes.data
    capabilityMap.value = {}
    for (const c of capRes.data) {
      capabilityMap.value[c.id] = c.name_cn || c.name
    }
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
