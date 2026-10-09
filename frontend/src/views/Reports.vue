<template>
  <div>
    <div class="toolbar">
      <b>每日风险报告（扫描完成自动生成）</b>
      <span style="margin-left:auto;color:#909399;font-size:12px">推送渠道（企业微信/钉钉/邮件）在系统配置中开启后自动外发</span>
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column prop="id" label="#" width="60" />
      <el-table-column prop="title" label="报告" min-width="200" show-overflow-tooltip />
      <el-table-column label="统计" min-width="200">
        <template #default="{ row }">
          {{ row.risk_customers }}/{{ row.total_customers }} 家有风险 ·
          高 <b style="color:var(--el-color-danger)">{{ row.high_count }}</b> /
          中 <b style="color:var(--el-color-warning)">{{ row.mid_count }}</b> /
          低 {{ row.low_count }} ·
          新增 <b style="color:var(--el-color-danger)">{{ row.new_risk_lines }}</b>
        </template>
      </el-table-column>
      <el-table-column prop="report_date" label="生成时间" width="165" />
      <el-table-column label="推送状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.push_status === '已推送' ? 'success' : 'info'" effect="plain">{{ row.push_status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="90" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="view(row)">查看</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:14px;justify-content:flex-end" background layout="total, prev, pager, next"
      :total="total" v-model:current-page="page" :page-size="pageSize" @current-change="load()" />

    <el-dialog v-model="detailVisible" :title="detail.title" width="760px" top="6vh">
      <el-alert :closable="false" :title="detail.summary" type="warning" show-icon style="margin-bottom:14px" />
      <template v-if="detail.payload && detail.payload.grouped">
        <div v-for="g in detail.payload.grouped" :key="g.customer_name" style="margin-bottom:12px">
          <b>{{ g.customer_name }}</b>
          <el-table :data="g.risks" border size="small" style="margin-top:6px">
            <el-table-column label="等级" width="80">
              <template #default="{ row }">
                <el-tag :color="LEVEL_COLORS[row.level]" style="color:#fff;border:none">{{ row.level }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="risk_type" label="类型" width="90" />
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="description" label="描述" min-width="220" show-overflow-tooltip />
            <el-table-column prop="risk_date" label="风险日期" width="100" />
          </el-table>
        </div>
      </template>
      <template v-if="detail.payload && detail.payload.new_risks && detail.payload.new_risks.length">
        <el-divider content-position="left">新增风险</el-divider>
        <div v-for="(r, i) in detail.payload.new_risks" :key="i" style="color:var(--el-color-danger);font-size:13px">
          • {{ r.customer_name }}｜{{ r.risk_type }}｜{{ r.title }}
        </div>
      </template>
      <template v-if="detail.payload && detail.payload.failed_customers && detail.payload.failed_customers.length">
        <el-divider content-position="left">扫描失败客户</el-divider>
        <div v-for="f in detail.payload.failed_customers" :key="f.customer_id" style="color:var(--el-color-warning);font-size:13px">
          • {{ f.customer_name }}
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, LEVEL_COLORS } from '../api'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const detailVisible = ref(false)
const detail = ref({})

async function load(p) {
  if (p) page.value = p
  loading.value = true
  try {
    const r = await api.get(`/api/reports?page=${page.value}&page_size=${pageSize.value}`)
    items.value = r.items
    total.value = r.total
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function view(row) {
  try {
    detail.value = await api.get(`/api/reports/${row.id}`)
    detailVisible.value = true
  } catch (e) {
    ElMessage.error(e.message)
  }
}

onMounted(() => load(1))
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
</style>
