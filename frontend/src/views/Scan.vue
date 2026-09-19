<template>
  <div>
    <el-alert type="info" :closable="false" show-icon style="margin-bottom:14px"
      title="到期判定规则：从未扫描直接到期；其余按上次风险等级定间隔（高风险3天/中风险7天/低·无风险30天，可在系统配置修改）" />

    <el-card shadow="never" style="margin-bottom:14px">
      <template #header>
        <div style="display:flex;align-items:center;gap:12px">
          <b>选择客户</b>
          <el-button size="small" type="primary" plain @click="selectDue">勾选全部到期客户（{{ dueIds.length }}）</el-button>
          <el-button size="small" @click="$refs.table.clearSelection()">清空</el-button>
          <el-button size="small" type="danger" :disabled="!selected.length || polling" @click="startScan">
            开始扫描（已选 {{ selected.length }} 家）
          </el-button>
        </div>
      </template>
      <el-table ref="table" :data="customers" v-loading="loading" border max-height="420"
        @selection-change="(rows) => (selected = rows)">
        <el-table-column type="selection" width="45" :selectable="(row) => !polling" />
        <el-table-column prop="name" label="客户名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="ctype" label="类型" width="70" />
        <el-table-column label="上次扫描" width="160">
          <template #default="{ row }">{{ row.last_scan_at || '从未扫描' }}</template>
        </el-table-column>
        <el-table-column label="上次等级" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.last_risk_level" :color="LEVEL_COLORS[row.last_risk_level]" style="color:#fff;border:none">{{ row.last_risk_level }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="扫描状态" width="90">
          <template #default="{ row }">
            <el-tag v-if="row.due" type="danger" effect="plain">到期</el-tag>
            <el-tag v-else type="success" effect="plain">未到期</el-tag>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card v-if="running" shadow="never" style="margin-bottom:14px">
      <template #header><b>扫描进行中 — 批次 #{{ runBatch.id }}</b></template>
      <el-progress :percentage="progress.total ? Math.round((progress.done / progress.total) * 100) : 0" :stroke-width="18" status="active" />
      <div style="margin-top:12px;display:flex;gap:26px;flex-wrap:wrap">
        <span>进度：{{ progress.done }} / {{ progress.total }}</span>
        <span>当前：<b>{{ progress.current || '-' }}</b></span>
        <span style="color:var(--el-color-danger)">有风险：{{ progress.risk_count }}</span>
        <span>失败：{{ progress.failed }}</span>
        <span>Tokens：{{ fmtNum(progress.tokens_in + progress.tokens_out) }}</span>
        <span>估算费用：{{ fmtMoney(progress.est_cost) }}</span>
      </div>
    </el-card>

    <el-card shadow="never">
      <template #header><b>扫描批次历史（按日存储，风险记录按批次隔离）</b></template>
      <el-table :data="batches" v-loading="batchesLoading" border size="small">
        <el-table-column prop="id" label="#" width="60" />
        <el-table-column prop="scan_date" label="扫描时间" width="165" />
        <el-table-column prop="trigger_type" label="触发" width="70" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="total" label="客户数" width="75" />
        <el-table-column label="有风险" width="75">
          <template #default="{ row }">
            <span :style="row.risk_count ? 'color:var(--el-color-danger);font-weight:600' : ''">{{ row.risk_count }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Tokens" width="110">
          <template #default="{ row }">{{ fmtNum(row.tokens_in + row.tokens_out) }}</template>
        </el-table-column>
        <el-table-column label="估算费用" width="100">
          <template #default="{ row }">{{ fmtMoney(row.est_cost) }}</template>
        </el-table-column>
        <el-table-column prop="note" label="备注" min-width="140" show-overflow-tooltip />
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewRisks(row)">查看台账</el-button>
            <el-button v-if="['中断', '失败'].includes(row.status)" link type="warning" @click="rescan(row)">重扫</el-button>
            <el-popconfirm v-if="row.status !== '运行中' && row.status !== '待运行'" title="删除批次将级联删除其风险记录，确认？" @confirm="delBatch(row)">
              <template #reference><el-button link type="danger">删除</el-button></template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import { api, LEVEL_COLORS, fmtMoney, fmtNum } from '../api'

const router = useRouter()
const customers = ref([])
const dueIds = ref([])
const selected = ref([])
const loading = ref(false)
const table = ref(null)

const running = ref(false)
const runBatch = ref({})
const progress = ref({ total: 0, done: 0, failed: 0, risk_count: 0, tokens_in: 0, tokens_out: 0, est_cost: 0, current: '' })
const batches = ref([])
const batchesLoading = ref(false)
let timer = null

const polling = computed(() => running.value)

function statusTag(s) {
  if (s === '完成') return 'success'
  if (s === '运行中' || s === '待运行') return 'primary'
  if (s === '中断') return 'warning'
  return 'danger'
}

async function loadCustomers() {
  loading.value = true
  try {
    const r = await api.get('/api/customers?page=1&page_size=200')
    customers.value = r.items
    const d = await api.get('/api/scan/due-preview')
    dueIds.value = d.due_ids
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function loadBatches() {
  batchesLoading.value = true
  try {
    const r = await api.get('/api/scan/batches?limit=50')
    batches.value = r.items
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    batchesLoading.value = false
  }
}

function selectDue() {
  table.value.clearSelection()
  customers.value.filter((c) => dueIds.value.includes(c.id)).forEach((c) => table.value.toggleRowSelection(c, true))
}

async function startScan() {
  const ids = selected.value.map((r) => r.id)
  if (!ids.length) return
  try {
    const r = await api.post('/api/scan/start', { customer_ids: ids })
    ElMessage.success(`批次 #${r.batch_id} 已开始`)
    beginPolling(r.batch_id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function beginPolling(batchId) {
  running.value = true
  runBatch.value = { id: batchId }
  stopTimer()
  poll(batchId)
  timer = setInterval(() => poll(batchId), 2000)
}

async function poll(batchId) {
  try {
    const r = await api.get(`/api/scan/current`)
    if (r.batch && r.batch.id === batchId) {
      progress.value = r.progress
      runBatch.value = r.batch
    } else {
      // 已结束：取最终状态并刷新
      stopTimer()
      running.value = false
      const bs = await api.get('/api/scan/batches?limit=50')
      batches.value = bs.items
      const b = bs.items.find((x) => x.id === batchId)
      if (b) {
        ElMessage({
          type: b.status === '完成' ? 'success' : 'error',
          message: `批次 #${batchId} ${b.status}：${b.total} 家客户，${b.risk_count} 条风险，估算费用 ${fmtMoney(b.est_cost)}`,
          duration: 6000,
        })
      }
      loadCustomers()
    }
  } catch { /* 轮询失败下次再试 */ }
}

function stopTimer() {
  if (timer) { clearInterval(timer); timer = null }
}

function viewRisks(row) {
  router.push({ name: 'risks', query: { batch_id: row.id } })
}

async function rescan(row) {
  try {
    const r = await api.post(`/api/scan/batches/${row.id}/rescan`)
    ElMessage.success(`已按原客户清单（${r.count} 家）发起新批次 #${r.batch_id}`)
    beginPolling(r.batch_id)
  } catch (e) {
    ElMessage.error(e.message)
  }
}

async function delBatch(row) {
  try {
    await api.del(`/api/scan/batches/${row.id}`)
    ElMessage.success('批次已删除')
    loadBatches()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  await Promise.all([loadCustomers(), loadBatches()])
  try {
    const r = await api.get('/api/scan/current')
    if (r.batch) {
      running.value = true
      runBatch.value = r.batch
      progress.value = r.progress
      stopTimer()
      timer = setInterval(() => poll(r.batch.id), 2000)
    }
  } catch { /* 忽略 */ }
})
onUnmounted(stopTimer)
</script>
