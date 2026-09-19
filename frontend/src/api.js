import { reactive } from 'vue'

export const auth = reactive({ checked: false, ok: false, defaultPassword: false })

async function request(method, url, body = null, isForm = false) {
  const opts = { method, headers: {} }
  if (body !== null && body !== undefined) {
    if (isForm) {
      opts.body = body
    } else {
      opts.headers['Content-Type'] = 'application/json'
      opts.body = JSON.stringify(body)
    }
  }
  const r = await fetch(url, opts)
  if (r.status === 401 && url !== '/api/login') {
    auth.ok = false
    if (!location.hash.startsWith('#/login')) location.hash = '#/login'
    throw new Error('未登录或登录已过期')
  }
  let data = {}
  try { data = await r.json() } catch { /* 空响应 */ }
  if (!r.ok) {
    const err = new Error(data.detail || `请求失败(${r.status})`)
    err.status = r.status
    throw err
  }
  return data
}

export const api = {
  get: (u) => request('GET', u),
  post: (u, b) => request('POST', u, b ?? {}),
  put: (u, b) => request('PUT', u, b ?? {}),
  del: (u) => request('DELETE', u),
  postForm: (u, fd) => request('POST', u, fd, true),
}

export const RISK_TYPES = ['工商', '诉讼', '财产冻结', '股东变更', '股权质押', '经营', '财务', '其他']
export const LEVEL_COLORS = { 高: '#f56c6c', 中: '#e6a23c', 低: '#d4b106' }

export function fmtMoney(v) {
  const n = Number(v) || 0
  return n >= 1 ? `¥${n.toFixed(2)}` : `¥${n.toFixed(4)}`
}

export function fmtNum(v) {
  return (Number(v) || 0).toLocaleString('zh-CN')
}
