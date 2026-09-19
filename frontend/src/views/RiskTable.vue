<template>
  <div>
    <el-alert type="warning" :closable="false" show-icon style="margin-bottom:14px"
      title="免责提示：风险信息由 AI 检索归纳（博查联网搜索 + 大模型分析），仅供内部参考，不构成权威工商/司法数据；重要决策请以企查查/天眼查等官方渠道为准。" />

    <div class="toolbar">
      <el-radio-group v-model="view" @change="load(1)">
        <el-radio-button value="latest_batch">最新批次</el-radio-button>
        <el-radio-button value="customer_latest">每客户最新状态</el-radio-button>
        <el-radio-button value="lifecycle">风险项生命周期</el-radio-button>
      </el-radio-group>
      <el-select v-model="batchId" placeholder="切换历史批次" clearable style="width: 230px" @change="onBatchChange">
        <el-option v-for="b in batches" :key="b.id" :value="b.id" :label="`#${b.id} ${b.scan_date}（${b.status}，风险 ${b.risk_count}）`" />
      </el-select>
      <el-select v-model="level" placeholder="风险等级" clearable style="width: 120px" @change="load(1)">
        <el-option v-for="l in ['高', '中', '低']" :key="l" :value="l" :label="l" />
      </el-select>
      <el-select v-model="riskType" placeholder="风险类型" clearable style="width: 130px" @change="load(1)">
        <el-option v-for="t in RISK_TYPES" :key="t" :value="t" :label="t" />
      </el-select>
      <el-input v-model="q" placeholder="搜索客户/标题/描述" clearable style="width: 200px" @keyup.enter="load(1)" @clear="load(1)" />
      <el-button type="primary" @click="load(1)">查询</el-button>
      <el-divider direction="vertical" />
      <el-date-picker v-model="exportDate" type="date" value-format="YYYY-MM-DD" placeholder="扫描日期" style="width: 140px" />
      <el-button type="success" @click="exportByDate">按日期导出</el-button>
      <el-button type="success" plain @click="exportAll">导出全部历史</el-button>
      <el-button link type="primary" @click="exportExcel">导出当前筛选</el-button>
    </div>

    <el-table v-if="view !== 'lifecycle'" :data="items" v-loading="loading" border stripe>
      <el-table-column prop="customer_name" label="客户名称" min-width="170" show-overflow-tooltip />
      <el-table-column label="风险类型" width="100">
        <template #default="{ row }"><el-tag effect="plain">{{ row.risk_type }}</el-tag></template>
      </el-table-column>
      <el-table-column label="风险等级" width="90">
        <template #default="{ row }">
          <el-tag :color="LEVEL_COLORS[row.level]" style="color:#fff;border:none">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="风险标题" min-width="160" show-overflow-tooltip />
      <el-table-column prop="description" label="风险描述" min-width="280" show-overflow-tooltip />
      <el-table-column prop="risk_date" label="风险日期" width="100" />
      <el-table-column prop="source" label="信息来源" min-width="150" show-overflow-tooltip />
      <el-table-column prop="scan_date" label="扫描日期" width="160" />
    </el-table>
    <el-table v-else :data="items" v-loading="loading" border stripe>
      <el-table-column prop="customer_name" label="客户名称" min-width="170" show-overflow-tooltip />
      <el-table-column label="风险类型" width="100">
        <template #default="{ row }"><el-tag effect="plain">{{ row.risk_type }}</el-tag></template>
      </el-table-column>
      <el-table-column label="当前等级" width="90">
        <template #default="{ row }">
          <el-tag :color="LEVEL_COLORS[row.level]" style="color:#fff;border:none">{{ row.level }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="风险标题" min-width="160" show-overflow-tooltip />
      <el-table-column prop="description" label="风险描述" min-width="240" show-overflow-tooltip />
      <el-table-column prop="first_seen" label="首次发现" width="160" />
      <el-table-column prop="last_seen" label="最近确认" width="160" />
      <el-table-column prop="batch_count" label="出现批次数" width="95" align="center" />
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.status === '活跃' ? 'danger' : 'info'" effect="plain">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:14px;justify-content:flex-end" background layout="total, prev, pager, next"
      :total="total" v-model:current-page="page" :page-size="pageSize" @current-change="load()" />

    <el-empty v-if="!loading && !items.length" :description="emptyText" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import { api, LEVEL_COLORS, RISK_TYPES } from '../api'

const route = useRoute()
const view = ref('latest_batch')
const batchId = ref(Number(route.query.batch_id) || 0)
const level = ref('')
const riskType = ref('')
const q = ref('')
const exportDate = ref('')
const page = ref(1)
const pageSize = ref(20)
const items = ref([])
const total = ref(0)
const batches = ref([])
const loading = ref(false)

const emptyText = computed(() =>
  view.value === 'lifecycle'
    ? '暂无风险项'
    : view.value === 'customer_latest'
      ? '暂无风险记录（最近批次扫出干净的客户不会出现在此视图）'
      : '当前批次没有风险记录'
)

async function load(p) {
  if (p) page.value = p
  loading.value = true
  try {
    const params = new URLSearchParams({
      view: view.value,
      batch_id: batchId.value || 0,
      level: level.value,
      risk_type: riskType.value,
      q: q.value,
      page: page.value,
      page_size: pageSize.value,
    })
    const r = await api.get(`/api/risks?${params}`)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function onBatchChange(v) {
  if (v) view.value = 'latest_batch'
  load(1)
}

function exportExcel() {
  const params = new URLSearchParams({
    view: view.value,
    batch_id: batchId.value || 0,
    level: level.value,
    risk_type: riskType.value,
    q: q.value,
  })
  window.open(`/api/risks/export?${params}`)
}

function exportByDate() {
  if (!exportDate.value) return ElMessage.warning('请先选择扫描日期')
  window.open(`/api/risks/export?date=${exportDate.value}`)
}

function exportAll() {
  window.open('/api/risks/export?full=1')
}

onMounted(async () => {
  try {
    const r = await api.get('/api/scan/batches?limit=100')
    batches.value = r.items
    exportDate.value = (r.items[0] && r.items[0].scan_date) ? r.items[0].scan_date.slice(0, 10) : ''
  } catch { /* 忽略 */ }
  load(1)
})
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
</style>
