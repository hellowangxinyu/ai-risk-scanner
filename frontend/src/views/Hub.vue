<template>
  <div>
    <el-tabs v-model="tab">
      <!-- 平台监控 -->
      <el-tab-pane label="平台监控" name="dashboard">
        <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:18px">
          <el-card v-for="c in cards" :key="c.label" shadow="never" style="min-width:130px">
            <div style="text-align:center">
              <div style="font-size:26px;font-weight:700">{{ c.value }}</div>
              <div style="color:#909399;font-size:12px">{{ c.label }}</div>
            </div>
          </el-card>
        </div>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><b>最近扫描批次</b></template>
              <el-table :data="dash.recent_batches" size="small" border>
                <el-table-column prop="id" label="#" width="50" />
                <el-table-column prop="scan_date" label="时间" width="150" />
                <el-table-column prop="status" label="状态" width="80" />
                <el-table-column prop="total" label="客户" width="70" />
                <el-table-column prop="risk_count" label="风险" width="70" />
              </el-table>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><b>运行日志</b></template>
              <div style="margin-bottom:8px">
                <el-radio-group v-model="logLevel" size="small" @change="loadLogs(1)">
                  <el-radio-button value="">全部</el-radio-button>
                  <el-radio-button value="INFO">INFO</el-radio-button>
                  <el-radio-button value="WARNING">WARNING</el-radio-button>
                  <el-radio-button value="ERROR">ERROR</el-radio-button>
                </el-radio-group>
              </div>
              <el-table :data="logs" size="small" border max-height="360">
                <el-table-column prop="created_at" label="时间" width="150" />
                <el-table-column prop="level" label="级别" width="80">
                  <template #default="{ row }">
                    <el-tag size="small" :type="row.level === 'ERROR' ? 'danger' : row.level === 'WARNING' ? 'warning' : 'info'" effect="plain">{{ row.level }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column prop="event" label="事件" width="130" show-overflow-tooltip />
                <el-table-column prop="detail" label="详情" show-overflow-tooltip />
              </el-table>
              <el-pagination style="margin-top:8px;justify-content:flex-end" background small layout="total, prev, pager" :total="logTotal" v-model:current-page="logPage" :page-size="30" @current-change="loadLogs()" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- 数据源 -->
      <el-tab-pane label="数据源接入" name="sources">
        <div style="margin-bottom:12px">
          <el-button type="primary" @click="openSource(null)">新增数据源</el-button>
          <span style="margin-left:12px;color:#909399;font-size:12px">对接外部数据库（SQLite/MySQL/PostgreSQL），把台账数据一键导入为客户</span>
        </div>
        <el-table :data="sources" border stripe>
          <el-table-column prop="name" label="名称" min-width="140" />
          <el-table-column prop="dstype" label="类型" width="110" />
          <el-table-column prop="last_status" label="连接状态" min-width="160" show-overflow-tooltip />
          <el-table-column prop="last_sync_at" label="最近同步" width="160" />
          <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button link type="success" @click="testSource(row)">测试连接</el-button>
              <el-button link type="primary" @click="openSource(row)">编辑</el-button>
              <el-button link type="warning" @click="manageSets(row)">数据集</el-button>
              <el-popconfirm title="删除数据源及其数据集？" @confirm="delSource(row)">
                <template #reference><el-button link type="danger">删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <!-- 数据源编辑 -->
        <el-dialog v-model="sourceVisible" :title="sourceForm.id ? '编辑数据源' : '新增数据源'" width="520px">
          <el-form label-width="100px">
            <el-form-item label="名称"><el-input v-model="sourceForm.name" /></el-form-item>
            <el-form-item label="类型">
              <el-select v-model="sourceForm.dstype" style="width:180px">
                <el-option value="sqlite" label="SQLite（本地文件）" />
                <el-option value="mysql" label="MySQL" />
                <el-option value="postgresql" label="PostgreSQL" />
              </el-select>
            </el-form-item>
            <template v-if="sourceForm.dstype === 'sqlite'">
              <el-form-item label="数据库路径"><el-input v-model="sourceForm.config.path" placeholder="/path/to/data.db" /></el-form-item>
            </template>
            <template v-else>
              <el-form-item label="主机"><el-input v-model="sourceForm.config.host" placeholder="127.0.0.1" /></el-form-item>
              <el-form-item label="端口"><el-input-number v-model="sourceForm.config.port" :min="1" /></el-form-item>
              <el-form-item label="数据库"><el-input v-model="sourceForm.config.database" /></el-form-item>
              <el-form-item label="用户名"><el-input v-model="sourceForm.config.user" /></el-form-item>
              <el-form-item label="密码"><el-input v-model="sourceForm.config.password" type="password" show-password /></el-form-item>
            </template>
            <el-form-item label="备注"><el-input v-model="sourceForm.note" /></el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="sourceVisible = false">取消</el-button>
            <el-button type="primary" :loading="savingSource" @click="saveSource">保存</el-button>
          </template>
        </el-dialog>

        <!-- 数据集管理 -->
        <el-dialog v-model="setsVisible" :title="`数据集管理 - ${currentSource && currentSource.name}`" width="720px">
          <div style="margin-bottom:10px">
            <el-button type="primary" size="small" @click="openSet(null)">新增数据集</el-button>
            <span style="margin-left:10px;color:#909399;font-size:12px">写 SELECT 查询，把列映射到客户字段后一键导入</span>
          </div>
          <el-table :data="sets" border size="small">
            <el-table-column prop="name" label="名称" min-width="130" />
            <el-table-column prop="query" label="查询" min-width="200" show-overflow-tooltip />
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="previewSet(row)">预览</el-button>
                <el-button link type="success" @click="importCustomers(row)">导入客户</el-button>
                <el-popconfirm title="删除该数据集？" @confirm="delSet(row)">
                  <template #reference><el-button link type="danger">删除</el-button></template>
                </el-popconfirm>
              </template>
            </el-table-column>
          </el-table>
        </el-dialog>

        <!-- 数据集编辑 -->
        <el-dialog v-model="setVisible" :title="setForm.id ? '编辑数据集' : '新增数据集'" width="640px">
          <el-form label-width="110px">
            <el-form-item label="名称"><el-input v-model="setForm.name" /></el-form-item>
            <el-form-item label="查询 SQL">
              <el-input v-model="setForm.query" type="textarea" :rows="3" placeholder="SELECT name, ctype, credit_code FROM customers" />
            </el-form-item>
            <el-form-item label="列映射">
              <div style="display:flex;flex-direction:column;gap:6px">
                <div v-for="f in ['name', 'ctype', 'credit_code', 'contact', 'note', 'is_credit']" :key="f" style="display:flex;align-items:center;gap:8px">
                  <span style="width:100px;color:#606266;font-size:13px">{{ f === 'name' ? '名称(必填)' : f === 'is_credit' ? '是否授信' : f === 'credit_code' ? '信用代码' : f === 'contact' ? '联系人' : f === 'ctype' ? '类型' : '备注' }}</span>
                  <el-input v-model="setForm.mapping[f]" placeholder="查询结果中的列名，留空忽略" style="width:220px" />
                </div>
              </div>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="setVisible = false">取消</el-button>
            <el-button type="primary" :loading="savingSet" @click="saveSet">保存</el-button>
          </template>
        </el-dialog>

        <!-- 预览 -->
        <el-dialog v-model="previewVisible" title="数据预览" width="720px">
          <el-table :data="preview.rows" border size="small" max-height="380">
            <el-table-column v-for="c in preview.columns" :key="c" :prop="c" :label="c" show-overflow-tooltip />
          </el-table>
          <div v-if="preview.truncated" style="color:#909399;font-size:12px;margin-top:6px">仅显示前 {{ preview.rows.length }} 行</div>
        </el-dialog>
      </el-tab-pane>

      <!-- 规则引擎 -->
      <el-tab-pane label="规则引擎" name="rules">
        <div style="margin-bottom:12px">
          <el-button type="primary" @click="openRule(null)">新增规则</el-button>
          <span style="margin-left:12px;color:#909399;font-size:12px">不用 AI，按字段规则直接判风险（扫描时自动追加命中项），适合确定性规则如"备注含'冻结'判高危"</span>
        </div>
        <el-table :data="rules" border stripe>
          <el-table-column prop="name" label="规则名" min-width="140" />
          <el-table-column label="条件" min-width="200">
            <template #default="{ row }">{{ row.field }} {{ row.op }} "{{ row.value }}"</template>
          </el-table-column>
          <el-table-column label="等级" width="80">
            <template #default="{ row }">
              <el-tag :color="LEVEL_COLORS[row.level]" style="color:#fff;border:none">{{ row.level }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="risk_type" label="风险类型" width="100" />
          <el-table-column label="启用" width="80">
            <template #default="{ row }">
              <el-switch :model-value="!!row.enabled" @change="(v) => toggleRule(row, v)" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openRule(row)">编辑</el-button>
              <el-popconfirm title="删除该规则？" @confirm="delRule(row)">
                <template #reference><el-button link type="danger">删除</el-button></template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>

        <el-dialog v-model="ruleVisible" :title="ruleForm.id ? '编辑规则' : '新增规则'" width="540px">
          <el-form label-width="90px">
            <el-form-item label="规则名"><el-input v-model="ruleForm.name" /></el-form-item>
            <el-form-item label="作用对象"><el-input value="客户" disabled /></el-form-item>
            <el-form-item label="字段">
              <el-select v-model="ruleForm.field" style="width:200px">
                <el-option v-for="f in ['name', 'ctype', 'credit_code', 'contact', 'note', 'is_credit']" :key="f" :value="f" :label="f" />
              </el-select>
            </el-form-item>
            <el-form-item label="操作符">
              <el-select v-model="ruleForm.op" style="width:200px">
                <el-option v-for="o in OPS" :key="o.value" :value="o.value" :label="o.label" />
              </el-select>
            </el-form-item>
            <el-form-item v-if="!['empty', 'not_empty'].includes(ruleForm.op)" label="值"><el-input v-model="ruleForm.value" /></el-form-item>
            <el-form-item label="风险等级">
              <el-radio-group v-model="ruleForm.level">
                <el-radio-button value="高">高</el-radio-button>
                <el-radio-button value="中">中</el-radio-button>
                <el-radio-button value="低">低</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="风险类型">
              <el-select v-model="ruleForm.risk_type" style="width:180px">
                <el-option v-for="t in RISK_TYPES" :key="t" :value="t" :label="t" />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="ruleVisible = false">取消</el-button>
            <el-button :loading="testingRule" @click="testRule">试算</el-button>
            <el-button type="primary" :loading="savingRule" @click="saveRule">保存</el-button>
          </template>
        </el-dialog>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, LEVEL_COLORS, RISK_TYPES } from '../api'

const tab = ref('dashboard')
const dash = ref({ recent_batches: [], logs_by_level: {} })
const cards = computed(() => [
  { label: '客户', value: dash.value.customers || 0 },
  { label: '扫描批次', value: dash.value.batches || 0 },
  { label: '风险记录', value: dash.value.risk_records || 0 },
  { label: '风险报告', value: dash.value.reports || 0 },
  { label: '数据源', value: dash.value.sources || 0 },
  { label: '规则', value: dash.value.rules || 0 },
])
const logs = ref([])
const logTotal = ref(0)
const logPage = ref(1)
const logLevel = ref('')

const sources = ref([])
const sourceVisible = ref(false)
const sourceForm = ref({})
const savingSource = ref(false)
const setsVisible = ref(false)
const currentSource = ref(null)
const sets = ref([])
const setVisible = ref(false)
const setForm = ref({ mapping: {} })
const savingSet = ref(false)
const previewVisible = ref(false)
const preview = ref({ columns: [], rows: [] })

const rules = ref([])
const ruleVisible = ref(false)
const ruleForm = ref({})
const savingRule = ref(false)
const testingRule = ref(false)

const OPS = [
  { value: 'contains', label: '包含' }, { value: 'not_contains', label: '不包含' },
  { value: 'eq', label: '等于' }, { value: 'ne', label: '不等于' },
  { value: 'gt', label: '大于' }, { value: 'lt', label: '小于' },
  { value: 'empty', label: '为空' }, { value: 'not_empty', label: '不为空' },
]

async function loadDash() {
  try { dash.value = await api.get('/api/hub/dashboard') } catch (e) { ElMessage.error(e.message) }
}
async function loadLogs(p) {
  if (p) logPage.value = p
  try {
    const r = await api.get(`/api/hub/logs?page=${logPage.value}&page_size=30&level=${logLevel.value}`)
    logs.value = r.items; logTotal.value = r.total
  } catch (e) { ElMessage.error(e.message) }
}
async function loadSources() {
  try { sources.value = (await api.get('/api/hub/sources')).items } catch (e) { ElMessage.error(e.message) }
}
function openSource(row) {
  sourceForm.value = row
    ? { ...row, config: JSON.parse(row.config || '{}') }
    : { id: 0, name: '', dstype: 'sqlite', config: {}, note: '' }
  if (!sourceForm.value.config) sourceForm.value.config = {}
  sourceVisible.value = true
}
async function saveSource() {
  savingSource.value = true
  try {
    if (sourceForm.value.id) await api.put(`/api/hub/sources/${sourceForm.value.id}`, sourceForm.value)
    else await api.post('/api/hub/sources', sourceForm.value)
    ElMessage.success('已保存'); sourceVisible.value = false; loadSources()
  } catch (e) { ElMessage.error(e.message) } finally { savingSource.value = false }
}
async function testSource(row) {
  try {
    const r = await api.post(`/api/hub/sources/${row.id}/test`)
    r.ok ? ElMessage.success(r.message) : ElMessage.error(r.message)
    loadSources()
  } catch (e) { ElMessage.error(e.message) }
}
async function delSource(row) {
  try { await api.del(`/api/hub/sources/${row.id}`); ElMessage.success('已删除'); loadSources() } catch (e) { ElMessage.error(e.message) }
}
async function manageSets(row) {
  currentSource.value = row
  try { sets.value = (await api.get(`/api/hub/sets?source_id=${row.id}`)).items } catch (e) { ElMessage.error(e.message) }
  setsVisible.value = true
}
function openSet(row) {
  setForm.value = row
    ? { ...row, mapping: JSON.parse(row.mapping || '{}') }
    : { id: 0, source_id: currentSource.value.id, name: '', query: 'SELECT name FROM customers', mapping: {}, kind: '客户名单', note: '' }
  setVisible.value = true
}
async function saveSet() {
  savingSet.value = true
  try {
    if (setForm.value.id) { ElMessage.warning('编辑请删除后重建'); return }
    await api.post('/api/hub/sets', setForm.value)
    ElMessage.success('已保存'); setVisible.value = false; manageSets(currentSource.value)
  } catch (e) { ElMessage.error(e.message) } finally { savingSet.value = false }
}
async function previewSet(row) {
  try {
    preview.value = await api.post(`/api/hub/sets/${row.id}/preview`)
    previewVisible.value = true
  } catch (e) { ElMessage.error(e.message) }
}
async function importCustomers(row) {
  try {
    const r = await api.post(`/api/hub/sets/${row.id}/import-customers`)
    ElMessage.success(`导入完成：新建 ${r.created} / 跳过 ${r.skipped} / 失败 ${r.failed.length}`)
    loadSources(); loadDash()
  } catch (e) { ElMessage.error(e.message) }
}
async function delSet(row) {
  try { await api.del(`/api/hub/sets/${row.id}`); manageSets(currentSource.value) } catch (e) { ElMessage.error(e.message) }
}
async function loadRules() {
  try { rules.value = (await api.get('/api/hub/rules')).items } catch (e) { ElMessage.error(e.message) }
}
function openRule(row) {
  ruleForm.value = row ? { ...row } : { id: 0, name: '', target: '客户', field: 'note', op: 'contains', value: '', level: '中', risk_type: '其他', enabled: true, note: '' }
  ruleVisible.value = true
}
async function saveRule() {
  savingRule.value = true
  try {
    if (ruleForm.value.id) await api.put(`/api/hub/rules/${ruleForm.value.id}`, ruleForm.value)
    else await api.post('/api/hub/rules', ruleForm.value)
    ElMessage.success('已保存'); ruleVisible.value = false; loadRules(); loadDash()
  } catch (e) { ElMessage.error(e.message) } finally { savingRule.value = false }
}
async function testRule() {
  testingRule.value = true
  try {
    const r = await api.post('/api/hub/rules/test', ruleForm.value)
    r.hit ? ElMessage.warning(`命中客户「${r.customer}」→ ${r.level}·${r.risk_type}`) : ElMessage.success(`未命中客户「${r.customer}」`)
  } catch (e) { ElMessage.error(e.message) } finally { testingRule.value = false }
}
async function toggleRule(row, v) {
  try { await api.put(`/api/hub/rules/${row.id}`, { ...row, enabled: v }); loadRules() } catch (e) { ElMessage.error(e.message) }
}
async function delRule(row) {
  try { await api.del(`/api/hub/rules/${row.id}`); loadRules() } catch (e) { ElMessage.error(e.message) }
}

onMounted(() => { loadDash(); loadLogs(1); loadSources(); loadRules() })
</script>
