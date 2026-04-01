<template>
  <el-container style="height:100vh;">
    <el-aside width="200px" style="background:#001529;">
      <div style="padding:24px 16px 8px;color:#fff;font-size:15px;font-weight:600;">AI 测试管理平台</div>
      <div style="color:#8c8c8c;font-size:11px;padding:0 16px 16px;">agilestar.cn</div>
      <el-menu :default-active="activeMenu" background-color="#001529"
               text-color="#ffffffa6" active-text-color="#ffffff" router>
        <el-menu-item index="/"><el-icon><Box /></el-icon><span>模型列表</span></el-menu-item>
        <el-menu-item index="/single"><el-icon><Picture /></el-icon><span>单样本测试</span></el-menu-item>
        <el-menu-item index="/batch"><el-icon><Grid /></el-icon><span>批量测试</span></el-menu-item>
        <el-menu-item index="/compare"><el-icon><DataAnalysis /></el-icon><span>版本对比</span></el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;justify-content:space-between;padding:0 24px;">
        <span style="font-size:15px;font-weight:500;">AI 综合能力平台 — 测试子系统</span>
        <span style="color:#8c8c8c;font-size:13px;">北京爱知之星科技股份有限公司</span>
      </el-header>
      <el-main style="background:#f5f5f5;padding:24px;"><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
</style>
