<template>
  <el-container style="height: 100vh">
    <el-aside width="200px" class="aside">
      <div class="logo">🛡 AI 财务风控</div>
      <el-menu :default-active="active" router background-color="#1f2d3d" text-color="#cfd8e3" active-text-color="#409eff">
        <el-menu-item index="/customers"><el-icon><User /></el-icon>客户管理</el-menu-item>
        <el-menu-item index="/scan"><el-icon><Search /></el-icon>风险扫描</el-menu-item>
        <el-menu-item index="/risks"><el-icon><Warning /></el-icon>风险台账</el-menu-item>
        <el-menu-item index="/settings"><el-icon><Setting /></el-icon>系统配置</el-menu-item>
      </el-menu>
    </el-aside>
    <el-container>
      <el-header class="header">
        <span class="page-title">{{ $route.meta.title }}</span>
        <el-button link type="primary" @click="logout">退出登录</el-button>
      </el-header>
      <div v-if="auth.defaultPassword" style="padding: 0 20px">
        <el-alert type="warning" :closable="false" show-icon
          title="当前使用默认口令 admin123，请在服务器部署时通过环境变量 APP_PASSWORD 修改" />
      </div>
      <el-main><router-view /></el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, auth } from '../api'

const route = useRoute()
const router = useRouter()
const active = computed(() => route.path)

async function logout() {
  try { await api.post('/api/logout') } catch { /* 忽略 */ }
  auth.ok = false
  router.push('/login')
}
</script>

<style scoped>
.aside { background: #1f2d3d; }
.aside .el-menu { border-right: none; }
.logo { color: #fff; font-weight: 600; font-size: 16px; padding: 20px 16px; }
.header {
  display: flex; align-items: center; justify-content: space-between;
  border-bottom: 1px solid var(--el-border-color-light);
}
.page-title { font-size: 17px; font-weight: 600; }
</style>
