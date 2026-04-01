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
    <el-menu-item index="/customers">
      <el-icon><User /></el-icon>
      <span>👥 客户管理</span>
    </el-menu-item>
    <el-menu-item index="/licenses">
      <el-icon><Document /></el-icon>
      <span>📋 授权管理</span>
    </el-menu-item>
    <el-menu-item index="/generate">
      <el-icon><Plus /></el-icon>
      <span>➕ 生成授权</span>
    </el-menu-item>
    <el-menu-item index="/keys">
      <el-icon><Key /></el-icon>
      <span>🔑 密钥管理</span>
    </el-menu-item>
    <el-menu-item index="/prod-tokens">
      <el-icon><Lock /></el-icon>
      <span>🔐 生产令牌</span>
    </el-menu-item>
  </el-menu>
</template>

<script setup>
import { useRoute } from 'vue-router'
const $route = useRoute()
</script>
