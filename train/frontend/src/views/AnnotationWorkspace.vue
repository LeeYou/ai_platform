<template>
  <div v-loading="loading">
    <!-- Top bar -->
    <el-card shadow="never" style="margin-bottom:16px;">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <div style="display:flex;align-items:center;gap:12px;">
          <el-button @click="$router.push('/annotations')" :icon="ArrowLeft">返回</el-button>
          <span style="font-size:16px;font-weight:600;">{{ project.name || '标注工作台' }}</span>
          <el-tag size="small">{{ typeLabels[project.annotation_type] || '' }}</el-tag>
          <el-tag size="small" type="info" v-if="project.network_type">{{ project.network_type }}</el-tag>
        </div>
        <div style="display:flex;align-items:center;gap:16px;">
          <span style="font-size:13px;color:#666;">{{ annotatedCount }}/{{ totalCount }} 已标注</span>
          <el-progress :percentage="totalCount > 0 ? Math.round(annotatedCount / totalCount * 100) : 0" style="width:200px;" :stroke-width="14" />
        </div>
      </div>
    </el-card>

    <el-row :gutter="16">
      <!-- Main canvas area -->
      <el-col :span="18">
        <el-card shadow="never" style="min-height:600px;">
          <!-- Navigation bar -->
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
            <div style="display:flex;align-items:center;gap:8px;">
              <el-button :disabled="currentIndex <= 0" @click="navigate(-1)" :icon="ArrowLeft" size="small">上一张</el-button>
              <span style="font-size:13px;">{{ currentIndex + 1 }} / {{ samples.length }}</span>
              <el-button :disabled="currentIndex >= samples.length - 1" @click="navigate(1)" size="small">
                下一张<el-icon class="el-icon--right"><ArrowRight /></el-icon>
              </el-button>
            </div>
            <div style="display:flex;align-items:center;gap:8px;">
              <el-select v-model="filterStatus" size="small" style="width:130px;" @change="loadSamples">
                <el-option label="全部样本" value="" />
                <el-option label="未标注" value="unannotated" />
                <el-option label="已标注" value="annotated" />
              </el-select>
              <el-input-number v-model="jumpIndex" :min="1" :max="samples.length" size="small" style="width:100px;" />
              <el-button size="small" @click="currentIndex = jumpIndex - 1">跳转</el-button>
            </div>
          </div>

          <!-- Image display area -->
          <div v-if="currentSample" style="display:flex;justify-content:center;align-items:center;min-height:480px;background:#f9f9f9;border:1px solid #eee;border-radius:4px;position:relative;overflow:hidden;" ref="canvasContainer">
            <!-- For classification types: simple image display -->
            <img v-if="isClassificationType" :src="currentImageUrl" style="max-width:100%;max-height:480px;object-fit:contain;" @error="imgError = true" />
            <div v-if="imgError" style="color:#999;">图片加载失败</div>

            <!-- For detection/OCR/segmentation: canvas overlay -->
            <div v-if="isCanvasType" style="position:relative;display:inline-block;">
              <canvas ref="annotationCanvas" @mousedown="onCanvasMouseDown" @mousemove="onCanvasMouseMove" @mouseup="onCanvasMouseUp" style="cursor:crosshair;display:block;" />
            </div>
          </div>
          <div v-else style="display:flex;justify-content:center;align-items:center;min-height:480px;color:#999;">
            {{ samples.length === 0 ? '暂无样本，请检查数据集路径' : '请选择样本' }}
          </div>

          <!-- File path display -->
          <div v-if="currentSample" style="margin-top:8px;font-size:12px;color:#999;text-align:center;">
            {{ currentSample.file_path }}
            <el-tag v-if="currentSample.annotated" type="success" size="small" style="margin-left:8px;">已标注</el-tag>
            <el-tag v-else type="info" size="small" style="margin-left:8px;">未标注</el-tag>
          </div>
        </el-card>
      </el-col>

      <!-- Right panel: annotation tools -->
      <el-col :span="6">
        <el-card shadow="never" style="min-height:600px;">
          <template #header><span>标注工具</span></template>

          <!-- Binary Classification Tool -->
          <div v-if="project.annotation_type === 'binary_classification'">
            <p style="font-size:13px;color:#666;margin-bottom:16px;">点击按钮或使用快捷键标注：</p>
            <div v-for="label in labels" :key="label.id" style="margin-bottom:12px;">
              <el-button :type="currentLabel === label.id ? 'primary' : 'default'" style="width:100%;height:48px;font-size:16px;" @click="annotateClassification(label.id)">
                {{ label.name }} <span style="font-size:12px;color:#999;margin-left:8px;">(快捷键 {{ label.id }})</span>
              </el-button>
            </div>
            <el-divider />
            <p style="font-size:12px;color:#999;">快捷键：← 上一张 | → 下一张 | 0/1 标注</p>
          </div>

          <!-- Multi Classification Tool -->
          <div v-if="project.annotation_type === 'multi_classification'">
            <p style="font-size:13px;color:#666;margin-bottom:12px;">选择类别标签：</p>
            <div v-for="label in labels" :key="label.id" style="margin-bottom:8px;">
              <el-button :type="currentLabel === label.id ? 'primary' : 'default'" style="width:100%;" @click="annotateClassification(label.id)">
                {{ label.name }} <span style="font-size:11px;color:#999;">({{ label.id }})</span>
              </el-button>
            </div>
            <el-divider />
            <p style="font-size:12px;color:#999;">快捷键：数字键对应标签ID</p>
          </div>

          <!-- Object Detection Tool -->
          <div v-if="project.annotation_type === 'object_detection'">
            <p style="font-size:13px;color:#666;margin-bottom:12px;">在图片上拖拽绘制检测框：</p>
            <div style="margin-bottom:12px;">
              <span style="font-size:13px;">当前标签：</span>
              <el-select v-model="activeLabel" size="small" style="width:100%;margin-top:4px;">
                <el-option v-for="label in labels" :key="label.id" :label="label.name" :value="label.name" />
              </el-select>
            </div>
            <el-divider />
            <p style="font-size:13px;font-weight:600;margin-bottom:8px;">已标注框 ({{ boxes.length }})</p>
            <div v-for="(box, i) in boxes" :key="i" style="display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-bottom:1px solid #f0f0f0;">
              <span style="font-size:12px;">{{ box.label }} [{{ Math.round(box.x) }},{{ Math.round(box.y) }},{{ Math.round(box.w) }},{{ Math.round(box.h) }}]</span>
              <el-button link type="danger" size="small" @click="removeBox(i)">删除</el-button>
            </div>
            <el-button v-if="boxes.length > 0" type="primary" style="width:100%;margin-top:12px;" @click="saveDetectionAnnotation">保存标注</el-button>
          </div>

          <!-- OCR Tool -->
          <div v-if="project.annotation_type === 'ocr'">
            <p style="font-size:13px;color:#666;margin-bottom:12px;">在图片上绘制文字区域（4点）：</p>
            <el-divider />
            <p style="font-size:13px;font-weight:600;margin-bottom:8px;">已标注区域 ({{ ocrRegions.length }})</p>
            <div v-for="(region, i) in ocrRegions" :key="i" style="padding:8px 0;border-bottom:1px solid #f0f0f0;">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <span style="font-size:12px;color:#666;">区域 {{ i + 1 }}</span>
                <el-button link type="danger" size="small" @click="removeOcrRegion(i)">删除</el-button>
              </div>
              <el-input v-model="region.text" size="small" placeholder="输入文字内容" style="margin-top:4px;" @change="saveOcrAnnotation" />
            </div>
            <el-button v-if="ocrRegions.length > 0" type="primary" style="width:100%;margin-top:12px;" @click="saveOcrAnnotation">保存标注</el-button>
          </div>

          <!-- Segmentation Tool -->
          <div v-if="project.annotation_type === 'segmentation'">
            <p style="font-size:13px;color:#666;margin-bottom:12px;">在图片上绘制分割多边形：</p>
            <div style="margin-bottom:12px;">
              <span style="font-size:13px;">当前标签：</span>
              <el-select v-model="activeLabel" size="small" style="width:100%;margin-top:4px;">
                <el-option v-for="label in labels" :key="label.id" :label="label.name" :value="label.name" />
              </el-select>
            </div>
            <p style="font-size:12px;color:#999;">点击添加多边形顶点，双击完成绘制</p>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  getAnnotationProject, listAnnotationSamples, saveAnnotation,
  annotationImageUrl, extractErrorMessage
} from '../api/index.js'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => Number(route.params.id))

const loading = ref(false)
const project = ref({})
const samples = ref([])
const currentIndex = ref(0)
const filterStatus = ref('')
const jumpIndex = ref(1)
const totalCount = ref(0)
const annotatedCount = ref(0)
const imgError = ref(false)

// Labels parsed from project.label_config
const labels = computed(() => {
  try {
    const cfg = typeof project.value.label_config === 'string'
      ? JSON.parse(project.value.label_config)
      : (project.value.label_config || {})
    return cfg.labels || []
  } catch { return [] }
})

const typeLabels = {
  binary_classification: '二分类', multi_classification: '多分类',
  object_detection: '目标检测', ocr: 'OCR文字识别', segmentation: '图像分割'
}

const isClassificationType = computed(() =>
  ['binary_classification', 'multi_classification'].includes(project.value.annotation_type)
)
const isCanvasType = computed(() =>
  ['object_detection', 'ocr', 'segmentation'].includes(project.value.annotation_type)
)

const currentSample = computed(() => samples.value[currentIndex.value] || null)
const currentImageUrl = computed(() => {
  if (!currentSample.value) return ''
  return annotationImageUrl(currentSample.value.file_path, project.value.dataset_path)
})

// Classification state
const currentLabel = ref(null)

// Detection state
const boxes = ref([])
const activeLabel = ref('')

// OCR state
const ocrRegions = ref([])

// Canvas refs
const annotationCanvas = ref(null)
const canvasContainer = ref(null)
let canvasImg = null
let isDrawing = false
let drawStart = { x: 0, y: 0 }
let drawCurrent = { x: 0, y: 0 }

// Load project and samples
const loadProject = async () => {
  try {
    const res = await getAnnotationProject(projectId.value)
    project.value = res.data
    if (labels.value.length > 0) {
      activeLabel.value = labels.value[0].name
    }
  } catch (e) {
    ElMessage.error('加载项目失败：' + extractErrorMessage(e))
  }
}

const loadSamples = async () => {
  loading.value = true
  try {
    const params = { offset: 0, limit: 9999 }
    if (filterStatus.value) params.status = filterStatus.value
    const res = await listAnnotationSamples(projectId.value, params)
    samples.value = res.data.samples || []
    totalCount.value = res.data.total || 0
    annotatedCount.value = samples.value.filter(s => s.annotated).length
    if (currentIndex.value >= samples.value.length) currentIndex.value = Math.max(0, samples.value.length - 1)
  } catch (e) {
    ElMessage.error('加载样本失败：' + extractErrorMessage(e))
  } finally {
    loading.value = false
  }
}

// Navigation
const navigate = (dir) => {
  const newIdx = currentIndex.value + dir
  if (newIdx >= 0 && newIdx < samples.value.length) {
    currentIndex.value = newIdx
    jumpIndex.value = newIdx + 1
  }
}

const goToNextUnannotated = () => {
  const idx = samples.value.findIndex((s, i) => i > currentIndex.value && !s.annotated)
  if (idx >= 0) {
    currentIndex.value = idx
    jumpIndex.value = idx + 1
  } else {
    const idx2 = samples.value.findIndex(s => !s.annotated)
    if (idx2 >= 0) {
      currentIndex.value = idx2
      jumpIndex.value = idx2 + 1
    } else {
      ElMessage.success('所有样本已标注完成！')
    }
  }
}

// Classification annotation
const annotateClassification = async (labelId) => {
  if (!currentSample.value) return
  currentLabel.value = labelId
  const labelObj = labels.value.find(l => l.id === labelId)
  try {
    await saveAnnotation(projectId.value, {
      file_path: currentSample.value.file_path,
      annotation_data: JSON.stringify({ label: labelId, label_name: labelObj?.name || String(labelId) }),
    })
    if (currentSample.value) {
      currentSample.value.annotated = true
      currentSample.value.annotation_data = { label: labelId, label_name: labelObj?.name }
    }
    annotatedCount.value = samples.value.filter(s => s.annotated).length
    goToNextUnannotated()
  } catch (e) {
    ElMessage.error('保存标注失败：' + extractErrorMessage(e))
  }
}

// Detection annotation
const saveDetectionAnnotation = async () => {
  if (!currentSample.value || boxes.value.length === 0) return
  try {
    await saveAnnotation(projectId.value, {
      file_path: currentSample.value.file_path,
      annotation_data: JSON.stringify({ boxes: boxes.value }),
    })
    currentSample.value.annotated = true
    annotatedCount.value = samples.value.filter(s => s.annotated).length
    ElMessage.success('标注已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + extractErrorMessage(e))
  }
}

const removeBox = (index) => { boxes.value.splice(index, 1) }

// OCR annotation
const saveOcrAnnotation = async () => {
  if (!currentSample.value || ocrRegions.value.length === 0) return
  try {
    await saveAnnotation(projectId.value, {
      file_path: currentSample.value.file_path,
      annotation_data: JSON.stringify({ regions: ocrRegions.value }),
    })
    currentSample.value.annotated = true
    annotatedCount.value = samples.value.filter(s => s.annotated).length
    ElMessage.success('标注已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + extractErrorMessage(e))
  }
}

const removeOcrRegion = (index) => { ocrRegions.value.splice(index, 1) }

// Canvas drawing for object detection
const drawCanvas = () => {
  const canvas = annotationCanvas.value
  if (!canvas || !canvasImg) return
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
  ctx.drawImage(canvasImg, 0, 0, canvas.width, canvas.height)

  // Draw existing boxes
  for (const box of boxes.value) {
    ctx.strokeStyle = '#FF0000'
    ctx.lineWidth = 2
    ctx.strokeRect(box.x, box.y, box.w, box.h)
    ctx.fillStyle = 'rgba(255,0,0,0.15)'
    ctx.fillRect(box.x, box.y, box.w, box.h)
    ctx.fillStyle = '#FF0000'
    ctx.font = '12px sans-serif'
    ctx.fillText(box.label, box.x + 2, box.y - 4)
  }

  // Draw OCR regions
  for (const region of ocrRegions.value) {
    if (region.points && region.points.length > 0) {
      ctx.strokeStyle = '#00AA00'
      ctx.lineWidth = 2
      ctx.beginPath()
      ctx.moveTo(region.points[0][0], region.points[0][1])
      for (let i = 1; i < region.points.length; i++) {
        ctx.lineTo(region.points[i][0], region.points[i][1])
      }
      ctx.closePath()
      ctx.stroke()
      ctx.fillStyle = 'rgba(0,170,0,0.15)'
      ctx.fill()
      if (region.text) {
        ctx.fillStyle = '#00AA00'
        ctx.font = '12px sans-serif'
        ctx.fillText(region.text, region.points[0][0], region.points[0][1] - 4)
      }
    }
  }

  // Draw current drawing rect
  if (isDrawing && project.value.annotation_type === 'object_detection') {
    const x = Math.min(drawStart.x, drawCurrent.x)
    const y = Math.min(drawStart.y, drawCurrent.y)
    const w = Math.abs(drawCurrent.x - drawStart.x)
    const h = Math.abs(drawCurrent.y - drawStart.y)
    ctx.strokeStyle = '#0066FF'
    ctx.lineWidth = 2
    ctx.setLineDash([5, 3])
    ctx.strokeRect(x, y, w, h)
    ctx.setLineDash([])
  }
}

const getCanvasCoords = (e) => {
  const canvas = annotationCanvas.value
  const rect = canvas.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

const onCanvasMouseDown = (e) => {
  if (project.value.annotation_type === 'object_detection') {
    isDrawing = true
    drawStart = getCanvasCoords(e)
    drawCurrent = { ...drawStart }
  }
}

const onCanvasMouseMove = (e) => {
  if (isDrawing) {
    drawCurrent = getCanvasCoords(e)
    drawCanvas()
  }
}

const onCanvasMouseUp = (e) => {
  if (isDrawing && project.value.annotation_type === 'object_detection') {
    isDrawing = false
    const end = getCanvasCoords(e)
    const x = Math.min(drawStart.x, end.x)
    const y = Math.min(drawStart.y, end.y)
    const w = Math.abs(end.x - drawStart.x)
    const h = Math.abs(end.y - drawStart.y)
    if (w > 5 && h > 5) {
      boxes.value.push({ x, y, w, h, label: activeLabel.value || 'unknown' })
    }
    drawCanvas()
  }
}

// Load image onto canvas
const loadCanvasImage = (url) => {
  if (!annotationCanvas.value) return
  canvasImg = new Image()
  canvasImg.crossOrigin = 'anonymous'
  canvasImg.onload = () => {
    const canvas = annotationCanvas.value
    if (!canvas) return
    const maxW = canvasContainer.value?.clientWidth - 40 || 800
    const maxH = 480
    let w = canvasImg.naturalWidth
    let h = canvasImg.naturalHeight
    const scale = Math.min(maxW / w, maxH / h, 1)
    w = Math.round(w * scale)
    h = Math.round(h * scale)
    canvas.width = w
    canvas.height = h
    drawCanvas()
  }
  canvasImg.src = url
}

// Watch current sample changes
watch(currentIndex, () => {
  imgError.value = false
  currentLabel.value = null
  boxes.value = []
  ocrRegions.value = []

  if (currentSample.value?.annotated && currentSample.value?.annotation_data) {
    const ann = currentSample.value.annotation_data
    if (ann.label !== undefined) currentLabel.value = ann.label
    if (ann.boxes) boxes.value = [...ann.boxes]
    if (ann.regions) ocrRegions.value = ann.regions.map(r => ({ ...r }))
  }

  if (isCanvasType.value) {
    nextTick(() => loadCanvasImage(currentImageUrl.value))
  }
})

// Keyboard shortcuts
const onKeyDown = (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return

  if (e.key === 'ArrowLeft') { navigate(-1); e.preventDefault() }
  if (e.key === 'ArrowRight') { navigate(1); e.preventDefault() }

  if (isClassificationType.value) {
    const num = parseInt(e.key)
    if (!isNaN(num)) {
      const label = labels.value.find(l => l.id === num)
      if (label) annotateClassification(label.id)
    }
  }
}

onMounted(async () => {
  await loadProject()
  await loadSamples()
  window.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', onKeyDown)
})
</script>
