<template>
  <el-container style="height: 100vh;">
    <el-aside width="200px" style="background:#304156;">
      <div style="height:60px;display:flex;align-items:center;justify-content:center;">
        <span style="color:#fff;font-size:16px;font-weight:bold;">🤖 授权管理</span>
      </div>
      <NavMenu />
    </el-aside>
    <el-container>
      <el-header style="background:#fff;border-bottom:1px solid #ebeef5;display:flex;align-items:center;justify-content:space-between;padding:0 20px;">
        <span style="font-size:16px;font-weight:500;">AI 综合能力平台 — 授权子系统</span>
        <AdminTokenSettings />
      </el-header>
      <el-main style="background:#f0f2f5;padding:20px;">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import AdminTokenSettings from './components/AdminTokenSettings.vue'
import NavMenu from './components/NavMenu.vue'
</script>

<style>
* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}
body {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
}
</style>
