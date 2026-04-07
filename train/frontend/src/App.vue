<template>
  <el-container style="height: 100vh;">
    <!-- Sidebar -->
    <el-aside width="220px" style="background:#001529;">
      <div style="padding:24px 16px 16px;color:#fff;font-size:16px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
        AI 训练管理平台
      </div>
      <div style="color:#8c8c8c;font-size:11px;padding:0 16px 16px;">agilestar.cn</div>
      <el-menu
        :default-active="activeMenu"
        background-color="#001529"
        text-color="#ffffffa6"
        active-text-color="#ffffff"
        router
      >
        <el-menu-item index="/">
          <el-icon><Odometer /></el-icon>
          <span>仪表盘</span>
        </el-menu-item>
        <el-menu-item index="/annotations">
          <el-icon><Edit /></el-icon>
          <span>样本标注</span>
        </el-menu-item>
        <el-menu-item index="/datasets">
          <el-icon><FolderOpen /></el-icon>
          <span>数据集管理</span>
        </el-menu-item>
        <el-menu-item index="/capabilities">
          <el-icon><Setting /></el-icon>
          <span>能力配置</span>
        </el-menu-item>
        <el-menu-item index="/jobs">
          <el-icon><VideoPlay /></el-icon>
          <span>训练控制</span>
        </el-menu-item>
        <el-menu-item index="/models">
          <el-icon><Box /></el-icon>
          <span>模型管理</span>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <!-- Main -->
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #f0f0f0;display:flex;align-items:center;justify-content:space-between;padding:0 24px;">
        <span style="font-size:16px;font-weight:500;">AI 综合能力平台 — 训练子系统</span>
        <div style="display:flex;align-items:center;gap:16px;">
          <AdminTokenSettings />
          <span style="color:#8c8c8c;font-size:13px;">北京爱知之星科技股份有限公司</span>
        </div>
      </el-header>
      <el-main style="background:#f5f5f5;padding:24px;">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import AdminTokenSettings from './components/AdminTokenSettings.vue'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
</style>
