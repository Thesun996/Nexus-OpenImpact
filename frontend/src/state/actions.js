import { ApiError, toWorkflowError } from '../api/client.js'
import { buildChangePayload, getSelectedTarget, isSupportedDemoChange } from './workflow.js'

import { matchesModuleIntent, moduleIdentity } from './moduleDraft.js'
import { matchesSymbolIntent, symbolIdentity } from './symbolDraft.js'

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

  // Compare declared intent only. Core remains the authority for signature validity.
  function matchesIntent(spec, change) {
    if (!spec || spec.target_symbol_id !== change.target_symbol_id || spec.change_type !== change.change_type) return false
    const operation = spec.operation
    if (operation && operation.change_type !== change.change_type) return false
    const name = (value) => typeof value === 'string' ? value.normalize('NFKC') : value
    if (change.change_type === 'add_required_parameter') {
      const added = operation?.added_parameter || spec.added_parameter
      return name(added?.name) === name(change.added_parameter.name) && added?.kind === change.added_parameter.kind
        && (!operation || (operation.insert_before || null) === (change.insert_before || null))
    }
    return operation?.change_type === change.change_type && name(operation.parameter_name) === name(change.parameter_name)
      && (change.change_type !== 'rename_parameter' || name(operation.new_parameter_name) === name(change.new_parameter_name))
  }

  function signatureIdentity(signature) {
    if (!signature || !Array.isArray(signature.parameters)) return null
    return JSON.stringify([signature.name, signature.is_async === true, signature.return_annotation_source ?? null,
      signature.parameters.map((parameter) => [parameter.name, parameter.kind, parameter.has_default === true,
        parameter.default_source ?? null, parameter.annotation_source ?? null])])
  }

  const actions = {
    selectFile: (file) => changeState({ type: 'FILE_SELECTED', file }),
    selectDomain: (domain) => changeState({ type: 'DOMAIN_SELECTED', domain }),
    selectModule: (id) => changeState({ type: 'MODULE_SELECTED', id }),
    selectSymbol: (id) => changeState({ type: 'SYMBOL_SELECTED', id }),
    selectVariableSymbol: (id) => changeState({ type: 'VARIABLE_SYMBOL_SELECTED', id }),
    selectChangeType: (changeType) => changeState({ type: 'CHANGE_TYPE_SELECTED', changeType }),
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
      if (!getSelectedTarget(current) || !current.file || !current.projectFingerprint) return localFailure('validate', 'inspection_required', '请先读取当前 ZIP 并选择分析目标。')
      if (current.mode === 'demo') {
        if (!isSupportedDemoChange(current)) return localFailure('validate', 'demo_configuration_unavailable', '演示仅提供 utils.format_date 新增 timezone 普通必填参数的保存响应。其他配置请使用实际项目模式。')
        dispatch({ type: 'VALIDATION_RECEIVED', validation: structuredClone(demo.validation), revision: current.revision,
          validatedChange: { revision: current.revision, payload: buildChangePayload(current) } })
        return true
      }
      if (current.changeDomain === 'module' && current.change.changeType === 'remove_module' && current.change.operation.confirmed !== true)
        return localFailure('validate', 'confirmation_required', '请确认仅分析拟定的模块删除，不修改项目文件。')
      if (current.changeDomain === 'symbol' && current.change.changeType === 'remove_module_symbol' && current.change.operation.confirmed !== true)
        return localFailure('validate', 'confirmation_required', '请确认仅分析拟定的符号删除，不修改项目文件。')
      const change = buildChangePayload(current)
      return run('validate', (signal) => client.validate(current.file, change, current.projectFingerprint, { signal }), (validation, revision) => {
        checkFingerprint(validation, current.projectFingerprint)
        if (current.changeDomain === 'symbol') {
          if (validation.validation?.valid !== true || !matchesSymbolIntent(validation.change_spec, change)
            || !symbolIdentity(validation.change_spec.before)
            || symbolIdentity(validation.change_spec.before) !== symbolIdentity(getSelectedTarget(current))) invalidResponse()
        } else if (current.changeDomain === 'module') {
          if (validation.validation?.valid !== true || validation.change_domain !== 'module'
            || !matchesModuleIntent(validation.change_spec, change)
            || !moduleIdentity(validation.change_spec.before)
            || moduleIdentity(validation.change_spec.before) !== moduleIdentity(getSelectedTarget(current))) invalidResponse()
        } else if (validation.validation?.valid !== true || !matchesIntent(validation.change_spec, change)
          || !signatureIdentity(validation.change_spec.before) || !signatureIdentity(validation.change_spec.after)) invalidResponse()
        dispatch({ type: 'VALIDATION_RECEIVED', validation, revision,
          validatedChange: { revision, payload: structuredClone(change) } })
      })
    },
    async analyzeProject() {
      if (active) return false
      const current = getState()
      if (current.validation?.validation?.valid !== true || !current.file || !current.projectFingerprint) return localFailure('analyze', 'validation_required', '请先校验当前目标与变更配置。')
      if (current.validatedChange?.revision !== current.revision
        || JSON.stringify(current.validatedChange.payload) !== JSON.stringify(buildChangePayload(current))) return localFailure('analyze', 'validation_required', '当前配置已变化，请重新校验变更。')
      if (current.mode === 'demo') {
        if (!isSupportedDemoChange(current)) return localFailure('analyze', 'validation_required', '请先校验固定演示配置。')
        dispatch({ type: 'REPORT_RECEIVED', report: structuredClone(demo.report), revision: current.revision })
        return true
      }
      const change = structuredClone(current.validatedChange.payload)
      return run('analyze', (signal) => client.analyze(current.file, change, current.projectFingerprint, { signal }), (report, revision) => {
        if (current.changeDomain === 'symbol') {
          checkFingerprint(report, current.projectFingerprint)
          if (report.change_domain !== 'symbol' || report.report_kind !== 'symbol_impact' || report.schema_version !== 1
            || !matchesSymbolIntent(report.change, change) || report.validation?.valid !== true
            || symbolIdentity(report.change.before) !== symbolIdentity(current.validation.change_spec.before)
            || JSON.stringify(report.change.after) !== JSON.stringify(current.validation.change_spec.after)
            || !report.summary || !Array.isArray(report.reference_impacts) || !Array.isArray(report.symbol_indirect_impacts)) invalidResponse()
        } else if (current.changeDomain === 'module') {
          checkFingerprint(report, current.projectFingerprint)
          if (report.change_domain !== 'module' || report.report_kind !== 'module_impact' || report.schema_version !== 1
            || !matchesModuleIntent(report.change, change) || report.validation?.valid !== true
            || moduleIdentity(report.change.before) !== moduleIdentity(current.validation.change_spec.before)
            || JSON.stringify(report.change.after) !== JSON.stringify(current.validation.change_spec.after)
            || !report.summary || !Array.isArray(report.import_impacts) || !Array.isArray(report.module_indirect_impacts)) invalidResponse()
        } else if (!matchesIntent(report.change, change) || report.validation?.valid !== true
          || signatureIdentity(report.change.before) !== signatureIdentity(current.validation.change_spec.before)
          || signatureIdentity(report.change.after) !== signatureIdentity(current.validation.change_spec.after)
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
