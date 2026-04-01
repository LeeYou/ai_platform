<template>
  <el-menu
    :default-active="$route.path"
    router
    background-color="#304156"
    text-color="#bfcbd9"
    active-text-color="#409EFF"
  >
    <el-menu-item index="/">
      <el-icon><DataAnalysis /></el-icon>
      <span>📊 仪表盘</span>
    </el-menu-item>
    <el-menu-item index="/new">
      <el-icon><SetUp /></el-icon>
      <span>🔨 新建编译</span>
    </el-menu-item>
    <el-menu-item index="/history">
      <el-icon><List /></el-icon>
      <span>📋 编译历史</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup>
import { useRoute } from 'vue-router'
const $route = useRoute()
</script>
