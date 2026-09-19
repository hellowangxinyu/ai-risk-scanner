<template>
  <div>
    <div class="toolbar">
      <el-input v-model="query" placeholder="搜索名称/联系人/信用代码" clearable style="width: 260px" @keyup.enter="load(1)" @clear="load(1)" />
      <el-button type="primary" @click="load(1)">搜索</el-button>
      <el-button type="success" @click="openEdit(null)">新增客户</el-button>
      <el-dropdown @command="importCommand" style="margin-left:12px">
        <el-button type="warning">批量导入<el-icon style="margin-left:4px"><ArrowDown /></el-icon></el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="excel">Excel 文件导入</el-dropdown-item>
            <el-dropdown-item command="text">粘贴文本导入</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button link type="primary" @click="downloadTemplate">下载 Excel 模板</el-button>
      <span style="margin-left:auto;color:var(--el-color-danger);font-weight:600">到期客户：{{ dueCount }} 家</span>
    </div>

    <el-table :data="items" v-loading="loading" border stripe>
      <el-table-column prop="name" label="客户名称" min-width="180" show-overflow-tooltip />
      <el-table-column prop="ctype" label="类型" width="70">
        <template #default="{ row }">
          <el-tag :type="row.ctype === '个人' ? 'info' : 'primary'" effect="plain">{{ row.ctype }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="credit_code" label="统一社会信用代码" width="190" show-overflow-tooltip />
      <el-table-column prop="contact" label="联系人" width="110" show-overflow-tooltip />
      <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
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
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-popconfirm title="确认删除该客户？" @confirm="remove(row)">
            <template #reference><el-button link type="danger">删除</el-button></template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>
    <el-pagination style="margin-top:14px;justify-content:flex-end" background layout="total, prev, pager, next, sizes"
      :total="total" v-model:current-page="page" v-model:page-size="pageSize"
      :page-sizes="[20, 50, 100]" @current-change="load()" @size-change="load(1)" />

    <!-- 新增/编辑 -->
    <el-dialog v-model="editVisible" :title="form.id ? '编辑客户' : '新增客户'" width="480px">
      <el-form label-width="110px">
        <el-form-item label="客户名称" required><el-input v-model="form.name" maxlength="200" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.ctype">
            <el-radio value="公司">公司</el-radio>
            <el-radio value="个人">个人</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="统一社会信用代码"><el-input v-model="form.credit_code" /></el-form-item>
        <el-form-item label="联系人"><el-input v-model="form.contact" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.note" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <!-- 导入 -->
    <el-dialog v-model="importVisible" :title="importMode === 'excel' ? 'Excel 批量导入' : '粘贴文本批量导入'" width="560px">
      <template v-if="importMode === 'excel'">
        <el-upload :auto-upload="false" :limit="1" :on-change="(f) => (importFile = f.raw)" drag>
          <el-icon style="font-size:32px;color:#909399"><UploadFilled /></el-icon>
          <div>选择 Excel 文件（列：名称/类型/统一社会信用代码/联系人/备注）</div>
        </el-upload>
      </template>
      <template v-else>
        <el-input v-model="importText" type="textarea" :rows="8" placeholder="每行一个客户名称，个人客户请通过 Excel 方式导入以指定类型" />
      </template>
      <div style="margin-top:10px">
        <el-button type="primary" :loading="importing" @click="doImport">开始导入</el-button>
      </div>
      <div v-if="report" style="margin-top:14px">
        <el-alert type="success" :closable="false" :title="`导入完成：成功 ${report.success} 家 / 跳过重复 ${report.skipped.length} 家 / 失败 ${report.failed.length} 行`" />
        <div v-if="report.skipped.length" style="margin-top:8px">
          <b>跳过：</b>
          <div v-for="(s, i) in report.skipped" :key="'s' + i" style="color:#909399">{{ s.name }}（{{ s.reason }}）</div>
        </div>
        <div v-if="report.failed.length" style="margin-top:8px">
          <b style="color:var(--el-color-danger)">失败行：</b>
          <div v-for="(f, i) in report.failed" :key="'f' + i" style="color:var(--el-color-danger)">第 {{ f.row }} 行 {{ f.name }}：{{ f.reason }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api, LEVEL_COLORS } from '../api'

const items = ref([])
const total = ref(0)
const dueCount = ref(0)
const query = ref('')
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)

const editVisible = ref(false)
const saving = ref(false)
const form = ref({})

const importVisible = ref(false)
const importMode = ref('excel')
const importFile = ref(null)
const importText = ref('')
const importing = ref(false)
const report = ref(null)

async function load(p) {
  if (p) page.value = p
  loading.value = true
  try {
    const r = await api.get(`/api/customers?query=${encodeURIComponent(query.value)}&page=${page.value}&page_size=${pageSize.value}`)
    items.value = r.items
    total.value = r.total
    dueCount.value = r.due_count
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

function openEdit(row) {
  form.value = row
    ? { ...row }
    : { id: 0, name: '', ctype: '公司', credit_code: '', contact: '', note: '' }
  editVisible.value = true
}

async function save() {
  if (!form.value.name.trim()) return ElMessage.warning('客户名称不能为空')
  saving.value = true
  try {
    if (form.value.id) {
      await api.put(`/api/customers/${form.value.id}`, form.value)
    } else {
      await api.post('/api/customers', form.value)
    }
    ElMessage.success('保存成功')
    editVisible.value = false
    load()
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    saving.value = false
  }
}

async function remove(row) {
  try {
    await api.del(`/api/customers/${row.id}`)
    ElMessage.success('已删除')
    load()
  } catch (e) {
    ElMessage.error(e.message)
  }
}

function importCommand(cmd) {
  importMode.value = cmd
  importFile.value = null
  importText.value = ''
  report.value = null
  importVisible.value = true
}

function downloadTemplate() {
  window.open('/api/customers/template')
}

async function doImport() {
  importing.value = true
  report.value = null
  try {
    if (importMode.value === 'excel') {
      if (!importFile.value) return ElMessage.warning('请先选择 Excel 文件')
      const fd = new FormData()
      fd.append('file', importFile.value)
      report.value = await api.postForm('/api/customers/import', fd)
    } else {
      if (!importText.value.trim()) return ElMessage.warning('请粘贴客户名称')
      const fd = new FormData()
      fd.append('text', importText.value)
      report.value = await api.postForm('/api/customers/import-text', fd)
    }
    load(1)
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    importing.value = false
  }
}

onMounted(() => load(1))
</script>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
</style>
