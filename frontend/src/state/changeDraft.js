// UI intent and display helpers only. Core Validate owns Python signature legality.
export const CHANGE_TYPES = Object.freeze([
  { value: 'add_required_parameter', label: '新增必填参数', description: '添加一个调用时必须提供的新参数。' },
  { value: 'remove_parameter', label: '删除参数', description: '移除一个现有普通参数，保留其余签名。' },
  { value: 'rename_parameter', label: '重命名参数', description: '只更改名称，检查仍使用旧名称的调用。' },
  { value: 'make_parameter_required', label: '可选参数改为必填', description: '移除已有默认值，参数名称与位置保持。' },
].map(Object.freeze))

const FIELDS = Object.freeze({
  add_required_parameter: ['parameterName', 'kind', 'insertBefore'],
  remove_parameter: ['parameterName'],
  rename_parameter: ['parameterName', 'newParameterName'],
  make_parameter_required: ['parameterName'],
})
const KINDS = ['positional_only', 'positional_or_keyword', 'var_positional', 'keyword_only', 'var_keyword']
const ORDINARY_KINDS = ['positional_only', 'positional_or_keyword', 'keyword_only']
const trimmed = value => typeof value === 'string' ? value.trim() : ''

function assertType(type) {
  if (!Object.hasOwn(FIELDS, type)) throw new RangeError('不支持的变更类型。')
}

export function createChangeDraft(type = 'add_required_parameter') {
  assertType(type)
  const operation = type === 'add_required_parameter'
    ? { parameterName: '', kind: 'positional_or_keyword', insertBefore: '' }
    : type === 'rename_parameter' ? { parameterName: '', newParameterName: '' } : { parameterName: '' }
  return { changeType: type, operation }
}

export function updateChangeDraft(change, patch) {
  const draft = createChangeDraft(change.changeType)
  for (const field of FIELDS[change.changeType]) {
    // Preserve typed whitespace until submission; exclude fields from other types.
    if (Object.hasOwn(change.operation || {}, field)) draft.operation[field] = change.operation[field]
    if (Object.hasOwn(patch || {}, field)) draft.operation[field] = patch[field]
  }
  return draft
}

export function getParameterChoices(definition, type) {
  assertType(type)
  return (definition?.parameters || []).map(parameter => {
    let reason = ''
    if (!KINDS.includes(parameter.kind)) reason = '参数类型信息不足，请重新读取项目。'
    else if (type === 'remove_parameter' && !ORDINARY_KINDS.includes(parameter.kind)) {
      reason = parameter.kind === 'var_positional' ? '当前版本暂不支持删除可变位置参数（*args）。' : '当前版本暂不支持删除可变关键字参数（**kwargs）。'
    } else if (type === 'rename_parameter' && parameter.kind === 'positional_only') {
      reason = '当前版本暂不支持重命名仅位置参数；函数体引用不在当前分析范围。'
    } else if (type === 'rename_parameter' && !['positional_or_keyword', 'keyword_only'].includes(parameter.kind)) {
      reason = '当前版本暂不支持重命名 *args 或 **kwargs。'
    } else if (type === 'make_parameter_required' && !ORDINARY_KINDS.includes(parameter.kind)) {
      reason = '当前版本暂不支持对 *args 或 **kwargs 移除默认值。'
    } else if (type === 'make_parameter_required' && parameter.has_default !== true) {
      reason = parameter.has_default === false ? '当前没有默认值，已经是必填参数。' : '默认值信息不足，请重新读取项目。'
    }
    return { parameter, enabled: !reason, reason }
  })
}

export function buildDraftPayload(targetSymbolId, change) {
  assertType(change.changeType)
  const operation = change.operation || {}
  const payload = { change_type: change.changeType, target_symbol_id: targetSymbolId }
  if (change.changeType === 'add_required_parameter') {
    payload.added_parameter = { name: trimmed(operation.parameterName), kind: operation.kind }
    const insertBefore = trimmed(operation.insertBefore)
    if (insertBefore) payload.insert_before = insertBefore
  } else {
    payload.parameter_name = trimmed(operation.parameterName)
    if (change.changeType === 'rename_parameter') payload.new_parameter_name = trimmed(operation.newParameterName)
  }
  return payload
}

export function previewSignature(definition, change) {
  if (!definition || !Array.isArray(definition.parameters) || !Object.hasOwn(FIELDS, change?.changeType)) return null
  const parameters = definition.parameters.map(parameter => ({ ...parameter }))
  const operation = change.operation || {}
  const name = trimmed(operation.parameterName)
  if (!name) return null
  if (change.changeType === 'add_required_parameter') {
    if (!ORDINARY_KINDS.includes(operation.kind) || parameters.some(parameter => !KINDS.includes(parameter.kind))) return null
    const insertBefore = trimmed(operation.insertBefore)
    const group = KINDS.indexOf(operation.kind)
    let position = insertBefore ? parameters.findIndex(parameter => parameter.name === insertBefore) : parameters.findIndex(parameter => KINDS.indexOf(parameter.kind) > group)
    if (insertBefore && position === -1) return null
    if (position === -1) position = parameters.length
    parameters.splice(position, 0, { name, kind: operation.kind, has_default: false, default_source: null, annotation_source: null })
  } else {
    const selected = getParameterChoices(definition, change.changeType).find(choice => choice.parameter.name === name)
    if (!selected?.enabled) return null
    const position = parameters.findIndex(parameter => parameter.name === name)
    if (change.changeType === 'remove_parameter') parameters.splice(position, 1)
    else if (change.changeType === 'rename_parameter') {
      const newName = trimmed(operation.newParameterName)
      if (!newName) return null
      parameters[position].name = newName
    } else {
      parameters[position].has_default = false
      parameters[position].default_source = null
    }
  }
  // This can intentionally represent an illegal draft, e.g. f(a=1, b).
  // Never repair order or infer legality; the API validates the candidate.
  return { ...definition, parameters }
}

export function describeChange(changeSpec) {
  const operation = changeSpec?.operation
  const type = changeSpec?.change_type || operation?.change_type || (changeSpec?.added_parameter ? 'add_required_parameter' : null)
  const descriptor = CHANGE_TYPES.find(item => item.value === type)
  const empty = { label: descriptor?.label || '未知变更', detail: '变更信息未提供', highlightName: null, removedName: null }
  if (!descriptor || (operation?.change_type && operation.change_type !== type)) return { ...empty, label: '未知变更', detail: '变更信息不一致或类型未支持' }
  if (type === 'add_required_parameter') {
    const name = operation?.added_parameter?.name || changeSpec?.added_parameter?.name
    return name ? { label: descriptor.label, detail: `新增必填参数 ${name}`, highlightName: name, removedName: null } : empty
  }
  const name = operation?.parameter_name
  if (!name) return empty
  if (type === 'remove_parameter') return { label: descriptor.label, detail: `删除参数 ${name}`, highlightName: null, removedName: name }
  if (type === 'rename_parameter') {
    const newName = operation.new_parameter_name
    return newName ? { label: descriptor.label, detail: `${name} → ${newName}`, highlightName: newName, removedName: name } : empty
  }
  const beforeParameter = changeSpec.before?.parameters?.find(parameter => parameter.name === name)
  const before = beforeParameter?.has_default === true ? `${name}=${beforeParameter.default_source ?? '…'}` : name
  // The parameter itself remains: only its default disappears from After.
  return { label: descriptor.label, detail: `${before} → ${name}（可选 → 必填）`, highlightName: name, removedName: null }
}
