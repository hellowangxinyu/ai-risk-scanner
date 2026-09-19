<template>
  <div style="max-width: 860px">
    <el-card shadow="never" style="margin-bottom:14px">
      <template #header><b>基础</b></template>
      <el-form label-width="150px">
        <el-form-item label="客户默认所属机构">
          <el-input v-model="form.default_org" style="width: 240px" placeholder="本公司" />
          <span style="margin-left:10px;color:#909399;font-size:12px">新增/批量导入客户未指定机构时使用；同机构下客户名称唯一</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom:14px">
      <template #header><b>AI 接口（OpenAI 兼容，默认 DeepSeek）</b></template>
      <el-form label-width="130px">
        <el-form-item label="Base URL"><el-input v-model="form.ai_base_url" placeholder="https://api.deepseek.com/v1" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="form.ai_api_key" type="password" show-password placeholder="sk-..." /></el-form-item>
        <el-form-item label="模型名称">
          <el-select v-model="form.ai_model" filterable allow-create default-first-option placeholder="deepseek-flash" style="width: 240px">
            <el-option v-for="m in modelOptions" :key="m" :value="m" :label="m" />
          </el-select>
          <el-button style="margin-left: 10px" :loading="loadingModels" @click="fetchModels">获取模型列表</el-button>
          <el-link type="primary" href="https://api-docs.deepseek.com/zh-cn/quick_start/pricing" target="_blank" style="margin-left: 10px">官方价格</el-link>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="testingAI" @click="testAI">测试 AI 连接</el-button>
          <el-button :loading="loadingBalance" @click="fetchBalance">查询账户余额</el-button>
          <span v-if="aiResult" :style="{ color: aiResult.ok ? 'var(--el-color-success)' : 'var(--el-color-danger)', marginLeft: '10px' }">
            {{ aiResult.message }}（{{ aiResult.latency_ms }}ms）
          </span>
        </el-form-item>
        <el-form-item v-if="balance">
          <el-alert :type="balance.is_available ? 'success' : 'warning'" :closable="false" style="width: 100%">
            <div v-for="(b, i) in balance.balances" :key="i">
              {{ b.currency }}　总额 ¥{{ b.total_balance }}（赠金 ¥{{ b.granted_balance }} / 充值 ¥{{ b.topped_up_balance }}）
            </div>
            <div v-if="!balance.is_available" style="color: var(--el-color-warning)">账户余额不足，请及时充值</div>
          </el-alert>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom:14px">
      <template #header><b>联网搜索（可选）</b></template>
      <el-form label-width="130px">
        <el-form-item label="启用联网搜索">
          <el-switch v-model="form.search_enabled" active-value="1" inactive-value="0" />
        </el-form-item>
        <el-form-item label="搜索提供方">
          <el-radio-group v-model="form.search_provider">
            <el-radio value="deepseek">DeepSeek 原生搜索（推荐）</el-radio>
            <el-radio value="bocha">博查搜索</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.search_provider === 'deepseek'">
          <span style="color:#909399;font-size:12px">复用上方 AI API Key，无需额外账号；每次搜索由 DeepSeek 在完整模型轮次中执行（消耗模型 Token，无单次搜索费）</span>
        </el-form-item>
        <el-form-item v-if="form.search_provider === 'bocha'" label="博查 API Key">
          <el-input v-model="form.search_api_key" type="password" show-password placeholder="sk-..." />
        </el-form-item>
        <el-form-item>
          <el-button :loading="testingSearch" @click="testSearch">测试搜索连接</el-button>
          <span v-if="searchResult" :style="{ color: searchResult.ok ? 'var(--el-color-success)' : 'var(--el-color-danger)', marginLeft: '10px' }">{{ searchResult.message }}</span>
        </el-form-item>
        <el-form-item>
          <span style="color:#909399;font-size:12px">每客户检索 1 次；搜索失败自动降级为纯模型知识并在来源中注明</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom:14px">
      <template #header><b>扫描周期（按风险等级分级）</b></template>
      <el-form label-width="130px">
        <el-form-item>
          <span style="color:#909399;font-size:12px;line-height:1.6">到期 = 上次扫描时间 + 间隔 ≤ 今天。<b>授信客户固定按高风险间隔扫描</b>；非授信客户按最近一次扫描结果的风险等级定间隔（从未扫描/无风险按低档）。自动扫描与手动扫描都只扫到期客户，未到期客户不会重复扫描、不产生费用</span>
        </el-form-item>
        <el-form-item label="高风险客户（授信）"><el-input-number v-model="form.cycle_high" :min="1" :max="365" /> 天/次</el-form-item>
        <el-form-item label="中风险客户（非授信）"><el-input-number v-model="form.cycle_mid" :min="1" :max="365" /> 天/次</el-form-item>
        <el-form-item label="低/无风险（非授信）"><el-input-number v-model="form.cycle_low" :min="1" :max="365" /> 天/次</el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom:14px">
      <template #header><b>每日自动扫描到期客户</b></template>
      <el-form label-width="130px">
        <el-form-item label="启用自动扫描">
          <el-switch v-model="form.auto_scan_enabled" active-value="1" inactive-value="0" />
          <span style="margin-left:10px;color:#909399;font-size:12px">每天到点检查到期名单，只扫当天到期的客户；当天没人到期则不产生扫描和费用</span>
        </el-form-item>
        <el-form-item label="扫描时刻">
          <el-time-select v-model="form.auto_scan_time" start="00:00" step="00:30" end="08:30" style="width:130px" />
          <span style="margin-left:10px;color:#909399;font-size:12px">建议 00:30-08:30（DeepSeek 空闲折扣时段，默认 02:00）；触发时若有批次运行中则本次自动跳过；错过时刻（如宕机）会在启动后补跑</span>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom:14px">
      <template #header><b>成本单价（用于"估算费用"，价格变动时请在此更新）</b></template>
      <el-form label-width="130px">
        <el-form-item label="输入单价"><el-input-number v-model="form.price_in" :min="0" :step="0.5" :precision="2" /> ¥/百万 Tokens</el-form-item>
        <el-form-item label="输出单价"><el-input-number v-model="form.price_out" :min="0" :step="0.5" :precision="2" /> ¥/百万 Tokens</el-form-item>
        <el-form-item label="搜索单价"><el-input-number v-model="form.price_search" :min="0" :step="0.006" :precision="4" /> ¥/次</el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" style="margin-bottom:14px">
      <template #header><b>累计用量（估算）</b></template>
      <div style="display:flex;gap:30px;flex-wrap:wrap">
        <span>批次总数：{{ usage.batches }}</span>
        <span>输入 Tokens：{{ fmtNum(usage.tokens_in) }}</span>
        <span>输出 Tokens：{{ fmtNum(usage.tokens_out) }}</span>
        <span>联网搜索：{{ usage.searches }} 次</span>
        <span style="font-weight:600">估算总费用：{{ fmtMoney(usage.est_cost) }}</span>
      </div>
    </el-card>

    <el-button type="primary" size="large" :loading="saving" @click="save">保存全部配置</el-button>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, fmtMoney, fmtNum } from '../api'

const form = ref({
  default_org: '本公司',
  ai_base_url: '', ai_api_key: '', ai_model: '',
  search_enabled: '0', search_provider: 'deepseek', search_api_key: '',
  cycle_high: 3, cycle_mid: 7, cycle_low: 30,
  auto_scan_enabled: '0', auto_scan_time: '02:00',
  price_in: 2, price_out: 8, price_search: 0.036,
})
const usage = ref({ batches: 0, tokens_in: 0, tokens_out: 0, searches: 0, est_cost: 0 })
const testingAI = ref(false)
const testingSearch = ref(false)
const saving = ref(false)
const aiResult = ref(null)
const searchResult = ref(null)
const modelOptions = ref([])
const loadingModels = ref(false)
const balance = ref(null)
const loadingBalance = ref(false)

async function load() {
  try {
    const r = await api.get('/api/settings')
    const s = r.settings
    form.value = {
      default_org: s.default_org || '本公司',
      ai_base_url: s.ai_base_url, ai_api_key: s.ai_api_key, ai_model: s.ai_model,
      search_enabled: s.search_enabled, search_provider: s.search_provider || 'deepseek', search_api_key: s.search_api_key,
      cycle_high: Number(s.cycle_high), cycle_mid: Number(s.cycle_mid), cycle_low: Number(s.cycle_low),
      auto_scan_enabled: s.auto_scan_enabled, auto_scan_time: s.auto_scan_time,
      price_in: Number(s.price_in), price_out: Number(s.price_out), price_search: Number(s.price_search),
    }
    usage.value = r.usage
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function save() {
  saving.value = true
  try {
    await api.post('/api/settings', { values: form.value })
    ElMessage.success('配置已保存')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function testAI() {
  testingAI.value = true
  aiResult.value = null
  try {
    await api.post('/api/settings', { values: form.value })
    aiResult.value = await api.post('/api/settings/test-ai')
  } catch (e) {
    aiResult.value = { ok: false, message: e.message, latency_ms: 0 }
  } finally {
    testingAI.value = false
  }
}

async function testSearch() {
  testingSearch.value = true
  searchResult.value = null
  try {
    await api.post('/api/settings', { values: form.value })
    searchResult.value = await api.post('/api/settings/test-search')
  } catch (e) {
    searchResult.value = { ok: false, message: e.message }
  } finally {
    testingSearch.value = false
  }
}

async function fetchModels() {
  loadingModels.value = true
  try {
    await api.post('/api/settings', { values: form.value })
    const r = await api.post('/api/settings/models')
    if (r.ok) {
      modelOptions.value = r.models
      ElMessage.success(`获取到 ${r.models.length} 个模型`)
    } else {
      ElMessage.error(r.message)
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loadingModels.value = false
  }
}

async function fetchBalance() {
  loadingBalance.value = true
  balance.value = null
  try {
    await api.post('/api/settings', { values: form.value })
    const r = await api.post('/api/settings/balance')
    if (r.ok) {
      balance.value = r
    } else {
      ElMessage.error(r.message)
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loadingBalance.value = false
  }
}

onMounted(load)
</script>
