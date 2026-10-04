import { ApiError, toWorkflowError } from '../api/client.js'
import { buildChangePayload, getSelectedSymbol, isSupportedDemoChange } from './workflow.js'

// One active business request per session. Cancellation saves client work;
// identity + revision checks also protect against a transport ignoring abort.
export function createWorkflowActions({ getState, dispatch, client, loadDemoFile, demo }) {
  let active = null
  let healthRequest = null

  function cancelBusiness() {
    active?.controller.abort()
    active = null
  }

  function changeState(action) {
    cancelBusiness()
    dispatch(action)
  }

  function localFailure(stage, code, message) {
    dispatch({ type: 'REQUEST_FAILED', stage, error: { stage, code, message }, revision: getState().revision })
    return false
  }

  function isCurrent(request) {
    return active === request && !request.controller.signal.aborted && getState().revision === request.revision
  }

  async function run(stage, invoke, receive) {
    if (active) return false
    const request = { controller: new AbortController(), revision: getState().revision }
    active = request
    dispatch({ type: 'REQUEST_START', stage, revision: request.revision })
    try {
      const payload = await invoke(request.controller.signal)
      if (!isCurrent(request)) return false
      receive(payload, request.revision)
      return true
    } catch (error) {
      if (!isCurrent(request) || error?.name === 'AbortError') return false
      const uiError = toWorkflowError(error, stage)
      if (uiError.code === 'fingerprint_mismatch') {
        dispatch({ type: 'FINGERPRINT_MISMATCH', error: uiError, revision: request.revision })
      } else {
        dispatch({ type: 'REQUEST_FAILED', stage, error: uiError, revision: request.revision,
          validation: error?.payload?.validation?.valid === false ? error.payload : undefined })
      }
      return false
    } finally {
      if (active === request) active = null
    }
  }

  function invalidResponse() {
    throw new ApiError({ code: 'invalid_response', message: '后端响应缺少当前操作所需的数据，请检查服务版本。' })
  }

  function checkFingerprint(payload, expected) {
    if (payload.project_fingerprint !== expected) {
      throw new ApiError({ status: 409, code: 'fingerprint_mismatch', message: '返回的项目指纹与当前 ZIP 不一致，请重新读取项目。' })
    }
  }

  const actions = {
    selectFile: (file) => changeState({ type: 'FILE_SELECTED', file }),
    selectSymbol: (id) => changeState({ type: 'SYMBOL_SELECTED', id }),
    updateChange: (change) => changeState({ type: 'CHANGE_UPDATED', change }),
    reset: () => changeState({ type: 'RESET' }),
    async checkHealth() {
      if (healthRequest) return false
      const request = { controller: new AbortController() }
      healthRequest = request
      dispatch({ type: 'HEALTH_REQUESTED' })
      try {
        const health = await client.health({ signal: request.controller.signal })
        if (healthRequest !== request || request.controller.signal.aborted) return false
        if (health.status !== 'ok' || typeof health.version !== 'string') invalidResponse()
        dispatch({ type: 'HEALTH_RECEIVED', health })
        return true
      } catch (error) {
        if (healthRequest !== request || request.controller.signal.aborted) return false
        dispatch({ type: 'HEALTH_FAILED', error: toWorkflowError(error, 'health') })
        return false
      } finally {
        if (healthRequest === request) healthRequest = null
      }
    },
    async inspectProject() {
      if (active) return false
      const current = getState()
      if (current.mode !== 'project' || !current.file) return localFailure('inspect', 'file_required', '请先选择要分析的原始项目 ZIP。')
      return run('inspect', (signal) => client.inspect(current.file, { signal }), (inspect, revision) => {
        if (!Array.isArray(inspect.symbols) || !Array.isArray(inspect.modules)
          || !/^[a-f0-9]{64}$/.test(inspect.project_fingerprint)) invalidResponse()
        dispatch({ type: 'INSPECT_RECEIVED', inspect, revision })
      })
    },
    async loadDemo() {
      return run('inspect', loadDemoFile, (file, revision) => {
        dispatch({ type: 'DEMO_RECEIVED', file, inspect: structuredClone(demo.inspect), revision })
      })
    },
    async validateChange() {
      if (active) return false
      const current = getState()
      if (!getSelectedSymbol(current) || !current.file || !current.projectFingerprint) return localFailure('validate', 'inspection_required', '请先读取当前 ZIP 并选择目标函数。')
      if (current.mode === 'demo') {
        if (!isSupportedDemoChange(current)) return localFailure('validate', 'demo_configuration_unavailable', '演示仅提供 utils.format_date 新增 timezone 普通必填参数的保存响应。其他配置请使用实际项目模式。')
        dispatch({ type: 'VALIDATION_RECEIVED', validation: structuredClone(demo.validation), revision: current.revision })
        return true
      }
      const change = buildChangePayload(current)
      return run('validate', (signal) => client.validate(current.file, change, current.projectFingerprint, { signal }), (validation, revision) => {
        checkFingerprint(validation, current.projectFingerprint)
        if (validation.validation?.valid !== true || validation.change_spec?.target_symbol_id !== current.selectedSymbolId) invalidResponse()
        dispatch({ type: 'VALIDATION_RECEIVED', validation, revision })
      })
    },
    async analyzeProject() {
      if (active) return false
      const current = getState()
      if (current.validation?.validation?.valid !== true || !current.file || !current.projectFingerprint) return localFailure('analyze', 'validation_required', '请先校验当前目标与变更配置。')
      if (current.mode === 'demo') {
        if (!isSupportedDemoChange(current)) return localFailure('analyze', 'validation_required', '请先校验固定演示配置。')
        dispatch({ type: 'REPORT_RECEIVED', report: structuredClone(demo.report), revision: current.revision })
        return true
      }
      const change = buildChangePayload(current)
      return run('analyze', (signal) => client.analyze(current.file, change, current.projectFingerprint, { signal }), (report, revision) => {
        if (report.change?.target_symbol_id !== current.selectedSymbolId || report.validation?.valid !== true
          || !report.summary || !Array.isArray(report.direct_impacts) || !Array.isArray(report.indirect_impacts)) invalidResponse()
        dispatch({ type: 'REPORT_RECEIVED', report, revision })
      })
    },
    dispose() {
      cancelBusiness()
      healthRequest?.controller.abort()
      healthRequest = null
    },
  }
  return actions
}
