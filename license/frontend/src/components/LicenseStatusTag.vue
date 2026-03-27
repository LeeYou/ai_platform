<template>
  <el-tag :type="tagType" size="small">{{ label }}</el-tag>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: {
    type: String,
    required: true,
  },
})

const tagType = computed(() => {
  switch (props.status) {
    case 'active': return 'success'
    case 'expired': return 'danger'
    case 'revoked': return 'info'
    default: return ''
  }
})

const label = computed(() => {
  switch (props.status) {
    case 'active': return '有效'
    case 'expired': return '已过期'
    case 'revoked': return '已吊销'
    default: return props.status
  }
})
</script>
