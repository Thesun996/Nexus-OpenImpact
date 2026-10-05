const API_ROOT = '/api/v1'

export class ApiError extends Error {
  constructor({ status = 0, code = 'request_failed', message, diagnostics = [], payload = null }) {
    super(message || '请求未成功，请检查输入后重试。')
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.diagnostics = diagnostics
    this.payload = payload
  }
}

function isObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function responseError(status, payload) {
  if (isObject(payload.error)) {
    return new ApiError({
      status,
      code: typeof payload.error.code === 'string' ? payload.error.code : 'request_failed',
      message: typeof payload.error.message === 'string' ? payload.error.message : undefined,
      diagnostics: payload.error.diagnostics ?? payload.diagnostics ?? [],
      payload,
    })
  }

  // Core validation failures deliberately have no `error` envelope.
  if (payload.validation?.valid === false) {
    const diagnostics = Array.isArray(payload.validation.diagnostics) ? payload.validation.diagnostics : []
    const first = diagnostics.find((item) => isObject(item) && typeof item.message === 'string')
    return new ApiError({
      status,
      code: typeof first?.code === 'string' ? first.code : 'change_validation_failed',
      message: first?.message || '变更配置未通过校验，请检查目标函数与参数。',
      diagnostics,
      payload,
    })
  }

  if (Array.isArray(payload.detail)) {
    // FastAPI also includes input values and validation context. Display only
    // field locations and messages; retain the JSON payload for callers.
    const diagnostics = payload.detail.filter(isObject).map((item) => ({
      code: typeof item.type === 'string' ? item.type : 'invalid_input',
      field: Array.isArray(item.loc) ? item.loc.filter((part) => typeof part === 'string' || typeof part === 'number').join('.') : null,
      message: typeof item.msg === 'string' ? item.msg : '请求字段不合法。',
    }))
    return new ApiError({ status, code: 'invalid_request', message: '请求字段缺失或格式错误，请检查上传文件和变更配置。', diagnostics, payload })
  }

  if (typeof payload.detail === 'string' && status < 500) {
    return new ApiError({ status, code: 'request_failed', message: payload.detail, payload })
  }

  return new ApiError({
    status,
    code: status >= 500 ? 'server_error' : 'request_failed',
    message: status >= 500 ? '后端处理失败，请稍后重试。' : `请求失败（HTTP ${status}），请检查输入。`,
    payload,
  })
}

function projectForm(file, change, fingerprint, analysisRoot = '.') {
  const form = new FormData()
  // Pass the caller's original File directly. Every project request reuploads it.
  form.append('file', file)
  if (analysisRoot !== '.') form.append('analysis_root', analysisRoot)
  if (change !== undefined) form.append('change', JSON.stringify(change))
  if (fingerprint !== undefined && fingerprint !== null && fingerprint !== '') {
    form.append('expected_fingerprint', fingerprint)
  }
  return form
}

export function createApiClient({ fetchImpl = fetch } = {}) {
  async function request(path, options) {
    let response
    try {
      response = await fetchImpl(`${API_ROOT}${path}`, { headers: { Accept: 'application/json' }, ...options })
    } catch (error) {
      if (error?.name === 'AbortError') throw error
      throw new ApiError({ code: 'backend_unreachable', message: '无法连接后端，请确认本地服务与 Vite 代理正在运行。' })
    }

    let payload
    try {
      payload = await response.json()
    } catch (error) {
      if (error?.name === 'AbortError') throw error
      // Never display the raw body: a proxy may return HTML or internal details.
      throw new ApiError({ status: response.status, code: 'invalid_response', message: '后端未返回有效的 JSON 响应，请检查服务和代理配置。' })
    }
    if (!isObject(payload)) {
      throw new ApiError({ status: response.status, code: 'invalid_response', message: '后端响应格式不符合接口契约。' })
    }
    if (!response.ok) throw responseError(response.status, payload)
    return payload
  }

  return {
    health({ signal } = {}) {
      return request('/health', { method: 'GET', signal })
    },
    inspect(file, { signal, analysisRoot = '.' } = {}) {
      return request('/projects/inspect', { method: 'POST', body: projectForm(file, undefined, undefined, analysisRoot), signal })
    },
    validate(file, change, fingerprint, { signal, analysisRoot = '.' } = {}) {
      return request('/changes/validate', { method: 'POST', body: projectForm(file, change, fingerprint, analysisRoot), signal })
    },
    analyze(file, change, fingerprint, { signal, analysisRoot = '.' } = {}) {
      return request('/projects/analyze', { method: 'POST', body: projectForm(file, change, fingerprint, analysisRoot), signal })
    },
  }
}

export function toWorkflowError(error, stage) {
  if (error instanceof ApiError) {
    return { stage, code: error.code, message: error.message, status: error.status, diagnostics: error.diagnostics }
  }
  return { stage, code: 'request_failed', message: '请求未成功，请重试。', status: 0, diagnostics: [] }
}

export const apiClient = createApiClient()
