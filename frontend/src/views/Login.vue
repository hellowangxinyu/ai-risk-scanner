<template>
  <div class="login-wrap">
    <el-card class="login-card">
      <h2 style="text-align:center;margin:8px 0 24px">AI 财务风控</h2>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="请输入访问口令" show-password size="large" @keyup.enter="submit" />
        </el-form-item>
        <el-button type="primary" size="large" style="width:100%" :loading="loading" native-type="submit">登 录</el-button>
      </el-form>
      <div v-if="error" style="color:var(--el-color-danger);margin-top:12px;text-align:center">{{ error }}</div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, auth } from '../api'

const router = useRouter()
const password = ref('')
const loading = ref(false)
const error = ref('')

async function submit() {
  if (!password.value) return
  loading.value = true
  error.value = ''
  try {
    const r = await api.post('/api/login', { password: password.value })
    auth.ok = true
    auth.defaultPassword = r.default_password
    router.push('/')
  } catch (e) {
    error.value = e.message === '口令错误' ? '口令错误，请重试' : e.message
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #1f2d3d 0%, #2b4a6f 100%);
}
.login-card { width: 380px; padding: 12px 8px; }
</style>
