<template>
  <el-container style="height: 100vh;">
    <el-aside width="200px" style="background:#304156;">
      <div style="height:60px;display:flex;align-items:center;justify-content:center;">
        <span style="color:#fff;font-size:16px;font-weight:bold;">🔧 编译管理</span>
      </div>
      <NavMenu />
    </el-aside>
    <el-container>
      <el-main style="background:#f0f2f5;padding:20px;">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
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
