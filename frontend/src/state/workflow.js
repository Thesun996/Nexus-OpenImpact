import { createChangeDraft, updateChangeDraft, buildDraftPayload } from './changeDraft.js'

export const DEMO_FINGERPRINT = 'db0a82348a94853526f7d79a2f58926994596a3ab1b7c639e6474673d32be1b3'

export function createInitialState(revision = 0) {
  return {
    mode: 'project', file: null, inspect: null, projectFingerprint: null,
    selectedSymbolId: null,
    change: createChangeDraft(),
    validation: null, validatedChange: null, report: null,
    loading: { inspect: false, validate: false, analyze: false }, error: null, revision,
    health: { status: 'idle', version: null, message: null },
  }
}

export function fileError(file) {
  if (!file) return null
  if (!file.name.toLowerCase().endsWith('.zip')) return { stage: 'inspect', code: 'zip_required', message: '请选择 Python 项目 ZIP 文件。' }
  if (file.size > 5 * 1024 * 1024) return { stage: 'inspect', code: 'upload_too_large', message: 'ZIP 不能超过当前后端的 5 MiB 上传限制。' }
  return null
}

export function workflowReducer(state, action) {
  // Async results belong to one project/configuration revision only.
  if (action.revision !== undefined && action.revision !== state.revision) return state
  switch (action.type) {
    case 'FILE_SELECTED': {
      const error = fileError(action.file)
      return { ...createInitialState(state.revision + 1), file: error ? null : action.file, error, health: state.health }
    }
    case 'DEMO_RECEIVED':
      return {
        ...createInitialState(state.revision + 1), mode: 'demo', file: action.file,
        inspect: action.inspect, projectFingerprint: action.inspect.project_fingerprint,
        selectedSymbolId: 'utils.format_date',
        change: updateChangeDraft(createChangeDraft(), { parameterName: 'timezone' }),
        health: state.health,
      }
    case 'INSPECT_RECEIVED':
      return { ...state, inspect: action.inspect, projectFingerprint: action.inspect.project_fingerprint, selectedSymbolId: null, validation: null, validatedChange: null, report: null, loading: { ...state.loading, inspect: false }, error: null }
    case 'SYMBOL_SELECTED':
      return {
        ...state, selectedSymbolId: state.inspect?.symbols?.some((s) => s.symbol_id === action.id) ? action.id : null,
        change: createChangeDraft(state.change.changeType),
        validation: null, validatedChange: null, report: null, error: null, loading: createInitialState().loading, revision: state.revision + 1,
      }
    case 'CHANGE_TYPE_SELECTED':
      return { ...state, change: createChangeDraft(action.changeType), validation: null, validatedChange: null, report: null, error: null, loading: createInitialState().loading, revision: state.revision + 1 }
    case 'CHANGE_UPDATED':
      return { ...state, change: updateChangeDraft(state.change, action.change), validation: null, validatedChange: null, report: null, error: null, loading: createInitialState().loading, revision: state.revision + 1 }
    case 'REQUEST_START': {
      const cleared = action.stage === 'inspect'
        ? { inspect: null, projectFingerprint: null, selectedSymbolId: null, change: createInitialState().change, validation: null, validatedChange: null, report: null }
        : action.stage === 'validate' ? { validation: null, validatedChange: null, report: null } : { report: null }
      return { ...state, ...cleared, loading: { ...state.loading, [action.stage]: true }, error: null }
    }
    case 'REQUEST_FAILED':
      return { ...state, ...(action.validation ? { validation: action.validation } : {}), loading: { ...state.loading, [action.stage]: false }, error: action.error }
    case 'FINGERPRINT_MISMATCH':
      return { ...createInitialState(state.revision + 1), file: state.file, health: state.health, error: action.error }
    case 'VALIDATION_RECEIVED':
      return { ...state, validation: action.validation, validatedChange: action.validatedChange || null, report: null, loading: { ...state.loading, validate: false }, error: null }
    case 'REPORT_RECEIVED':
      return { ...state, report: action.report, loading: { ...state.loading, analyze: false }, error: null }
    case 'RESET':
      return { ...createInitialState(state.revision + 1), health: state.health }
    case 'HEALTH_REQUESTED':
      return { ...state, health: { status: 'checking', version: null, message: null } }
    case 'HEALTH_RECEIVED':
      return { ...state, health: { status: 'ok', version: action.health.version, message: null } }
    case 'HEALTH_FAILED':
      return { ...state, health: { status: 'error', version: null, message: action.error.message } }
    default:
      return state
  }
}

export function getSelectedSymbol(state) {
  return state.inspect?.symbols?.find((s) => s.symbol_id === state.selectedSymbolId) || null
}

export function buildChangePayload(state) {
  return buildDraftPayload(state.selectedSymbolId, state.change)
}

export function isSupportedDemoChange(state) {
  return state.mode === 'demo' && state.projectFingerprint === DEMO_FINGERPRINT
    && state.selectedSymbolId === 'utils.format_date'
    && state.change.changeType === 'add_required_parameter'
    && state.change.operation.parameterName === 'timezone'
    && state.change.operation.kind === 'positional_or_keyword' && !state.change.operation.insertBefore
}

// Display the structured signature only; insertion/validation stays in Core.
export function formatSignature(definition) {
  if (!definition) return '—'
  const params = definition.parameters || []
  const parts = []
  let hasStar = false
  params.forEach((param, index) => {
    if (param.kind === 'keyword_only' && !hasStar) { parts.push('*'); hasStar = true }
    const prefix = param.kind === 'var_positional' ? '*' : param.kind === 'var_keyword' ? '**' : ''
    if (param.kind === 'var_positional') hasStar = true
    let part = `${prefix}${param.name}`
    if (param.annotation_source) part += `: ${param.annotation_source}`
    if (param.has_default) part += `=${param.default_source ?? '…'}`
    parts.push(part)
    if (param.kind === 'positional_only' && params[index + 1]?.kind !== 'positional_only') parts.push('/')
  })
  return `${definition.name}(${parts.join(', ')})`
}
