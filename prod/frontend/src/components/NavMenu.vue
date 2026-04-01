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
    <el-menu-item index="/api-test">
      <el-icon><SetUp /></el-icon>
      <span>🧪 API 测试</span>
    </el-menu-item>
    <el-menu-item index="/pipelines">
      <el-icon><Connection /></el-icon>
      <span>🔗 AI 编排</span>
    </el-menu-item>
    <el-menu-item index="/pipeline-test">
      <el-icon><VideoPlay /></el-icon>
      <span>🧪 编排测试</span>
    </el-menu-item>
    <el-menu-item index="/status">
      <el-icon><List /></el-icon>
      <span>📋 服务状态</span>
    </el-menu-item>
    <el-menu-item index="/admin">
      <el-icon><Setting /></el-icon>
      <span>⚙️ 系统管理</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup>
import { useRoute } from 'vue-router'
const $route = useRoute()
</script>
