<template>
  <div>
    <el-card>
      <template #header>
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <span>👥 客户管理</span>
          <el-button type="primary" @click="openAdd"><el-icon><Plus /></el-icon> 新增客户</el-button>
        </div>
      </template>
      <el-table :data="list" stripe v-loading="loading">
        <el-table-column prop="customer_id" label="客户ID" width="220" show-overflow-tooltip />
        <el-table-column prop="name" label="名称" />
        <el-table-column prop="contact_person" label="联系人" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="created_at" label="创建时间" width="120">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination
        style="margin-top:16px;text-align:right;"
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        :current-page="page"
        @current-change="onPageChange"
      />
    </el-card>

    <!-- Add/Edit Dialog -->
    <el-dialog v-model="dialogVisible" :title="isEdit ? '编辑客户' : '新增客户'" width="480px">
      <el-form :model="form" :rules="rules" ref="formRef" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" placeholder="客户名称" />
        </el-form-item>
        <el-form-item label="联系人" prop="contact_person">
          <el-input v-model="form.contact_person" placeholder="联系人姓名" />
        </el-form-item>
        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" placeholder="联系邮箱" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.notes" type="textarea" rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="submitting">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getCustomers, createCustomer, updateCustomer, deleteCustomer } from '../api/index.js'

const loading = ref(false)
const submitting = ref(false)
const list = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref()
const form = ref({ name: '', contact_person: '', email: '', notes: '' })
const editingId = ref(null)

const rules = {
  name: [{ required: true, message: '请输入客户名称', trigger: 'blur' }],
  email: [{ type: 'email', message: '邮箱格式不正确', trigger: 'blur' }],
}

function formatDate(val) {
  if (!val) return '-'
  return val.slice(0, 10)
}

async function loadList() {
  loading.value = true
  try {
    const res = await getCustomers(page.value, pageSize)
    list.value = res.data?.items ?? res.data ?? []
    total.value = res.data?.total ?? list.value.length
  } catch (e) {
    ElMessage.error('加载客户列表失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function onPageChange(p) {
  page.value = p
  loadList()
}

function openAdd() {
  isEdit.value = false
  editingId.value = null
  form.value = { name: '', contact_person: '', email: '', notes: '' }
  dialogVisible.value = true
}

function openEdit(row) {
  isEdit.value = true
  editingId.value = row.customer_id
  form.value = { name: row.name, contact_person: row.contact_person, email: row.email, notes: row.notes || '' }
  dialogVisible.value = true
}

async function handleSubmit() {
  await formRef.value.validate()
  submitting.value = true
  try {
    if (isEdit.value) {
      await updateCustomer(editingId.value, form.value)
      ElMessage.success('更新成功')
    } else {
      await createCustomer(form.value)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    loadList()
  } catch (e) {
    ElMessage.error('操作失败：' + (e.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}

async function handleDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除客户「${row.name}」？`, '确认删除', { type: 'warning' })
    await deleteCustomer(row.customer_id)
    ElMessage.success('删除成功')
    loadList()
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

onMounted(loadList)
</script>
