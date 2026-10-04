import test from 'node:test'
import assert from 'node:assert/strict'
import { CHANGE_TYPES, buildDraftPayload, createChangeDraft, describeChange, getParameterChoices, previewSignature, updateChangeDraft } from '../src/state/changeDraft.js'
import { formatSignature } from '../src/state/workflow.js'

const parameter = (name, kind = 'positional_or_keyword', extra = {}) => ({ name, kind, has_default: false, default_source: null, annotation_source: null, ...extra })
const definition = parameters => ({ name: 'f', parameters, is_async: false, return_annotation_source: 'str', line: 3 })
const draft = (type, operation) => updateChangeDraft(createChangeDraft(type), operation)

test('four explicit choices share one fresh draft factory and reject unknown types', () => {
  assert.deepEqual(CHANGE_TYPES.map(type => type.value), ['add_required_parameter', 'remove_parameter', 'rename_parameter', 'make_parameter_required'])
  assert.deepEqual(createChangeDraft(), { changeType: 'add_required_parameter', operation: { parameterName: '', kind: 'positional_or_keyword', insertBefore: '' } })
  assert.deepEqual(createChangeDraft('rename_parameter').operation, { parameterName: '', newParameterName: '' })
  const first = createChangeDraft('remove_parameter')
  first.operation.parameterName = 'old'
  assert.equal(createChangeDraft('remove_parameter').operation.parameterName, '')
  assert.throws(() => createChangeDraft('make_parameter_optional'), RangeError)
})

test('operation updates keep typed content and discard fields belonging to another type', () => {
  const current = draft('remove_parameter', { parameterName: ' timeout ', newParameterName: 'delay', kind: 'keyword_only', insertBefore: 'a' })
  assert.deepEqual(current, { changeType: 'remove_parameter', operation: { parameterName: ' timeout ' } })
  assert.deepEqual(updateChangeDraft(current, { parameterName: 'mode', changeType: 'rename_parameter' }), { changeType: 'remove_parameter', operation: { parameterName: 'mode' } })
  assert.equal(current.operation.parameterName, ' timeout ')
})

test('remove selection retains unsupported variadics with visible reasons', () => {
  const source = definition([parameter('a', 'positional_only'), parameter('b'), parameter('args', 'var_positional'), parameter('mode', 'keyword_only'), parameter('kwargs', 'var_keyword')])
  const choices = getParameterChoices(source, 'remove_parameter')
  assert.deepEqual(choices.map(choice => choice.enabled), [true, true, false, true, false])
  assert.equal(choices[2].parameter, source.parameters[2])
  assert.match(choices[2].reason, /\*args/)
  assert.match(choices[4].reason, /\*\*kwargs/)
})

test('rename selection disables positional-only and variadic parameters without hiding them', () => {
  const choices = getParameterChoices(definition([parameter('a', 'positional_only'), parameter('b'), parameter('args', 'var_positional'), parameter('mode', 'keyword_only'), parameter('kwargs', 'var_keyword')]), 'rename_parameter')
  assert.deepEqual(choices.map(choice => choice.enabled), [false, true, false, true, false])
  assert.match(choices[0].reason, /仅位置参数/)
  assert.ok(choices.filter(choice => !choice.enabled).every(choice => choice.reason.length > 0))
})

test('make required uses has_default for None, False, zero, and empty string source', () => {
  const defaults = ['None', 'False', '0', '""']
  const source = definition(defaults.map((default_source, index) => parameter(`p${index}`, index === 0 ? 'positional_only' : index === 3 ? 'keyword_only' : 'positional_or_keyword', { has_default: true, default_source })))
  assert.ok(getParameterChoices(source, 'make_parameter_required').every(choice => choice.enabled))
  const extra = getParameterChoices(definition([parameter('required'), parameter('args', 'var_positional'), parameter('missing', 'keyword_only', { has_default: undefined }), parameter('wrongFlag', 'keyword_only', { has_default: 'true', default_source: '0' })]), 'make_parameter_required')
  assert.deepEqual(extra.map(choice => choice.enabled), [false, false, false, false])
  assert.match(extra[0].reason, /已经是必填/)
  assert.match(extra[2].reason, /信息不足/)
})

test('unknown parameter kinds are visible and disabled; empty function has no phantom options', () => {
  for (const { value } of CHANGE_TYPES) assert.deepEqual(getParameterChoices(definition([]), value), [])
  const [unknown] = getParameterChoices(definition([parameter('x', 'future_kind')]), 'remove_parameter')
  assert.equal(unknown.enabled, false)
  assert.match(unknown.reason, /信息不足/)
})

test('add payload explicitly names type and preserves kind and optional insertion', () => {
  assert.deepEqual(buildDraftPayload('m.f', draft('add_required_parameter', { parameterName: ' timezone ', kind: 'keyword_only', insertBefore: ' a ' })), {
    change_type: 'add_required_parameter', target_symbol_id: 'm.f', added_parameter: { name: 'timezone', kind: 'keyword_only' }, insert_before: 'a',
  })
  assert.deepEqual(buildDraftPayload('m.f', draft('add_required_parameter', { parameterName: 'zone', insertBefore: ' ' })), {
    change_type: 'add_required_parameter', target_symbol_id: 'm.f', added_parameter: { name: 'zone', kind: 'positional_or_keyword' },
  })
})

test('non-add payloads are exact and cannot leak stale added-parameter fields', () => {
  const input = { parameterName: ' timeout ', newParameterName: ' delay ', kind: 'keyword_only', insertBefore: 'a' }
  assert.deepEqual(buildDraftPayload('m.f', draft('remove_parameter', input)), { change_type: 'remove_parameter', target_symbol_id: 'm.f', parameter_name: 'timeout' })
  assert.deepEqual(buildDraftPayload('m.f', draft('rename_parameter', input)), { change_type: 'rename_parameter', target_symbol_id: 'm.f', parameter_name: 'timeout', new_parameter_name: 'delay' })
  assert.deepEqual(buildDraftPayload('m.f', draft('make_parameter_required', input)), { change_type: 'make_parameter_required', target_symbol_id: 'm.f', parameter_name: 'timeout' })
})

test('payload preserves Unicode and leaves Python identifier validity to Core', () => {
  assert.equal(buildDraftPayload('m.f', draft('rename_parameter', { parameterName: '原名', newParameterName: 'ｄｅｌａｙ' })).new_parameter_name, 'ｄｅｌａｙ')
  assert.equal(buildDraftPayload('m.f', draft('add_required_parameter', { parameterName: 'not-valid-name' })).added_parameter.name, 'not-valid-name')
  assert.throws(() => buildDraftPayload('m.f', { changeType: 'unknown', operation: {} }), RangeError)
})

test('add preview handles no-argument functions and respects kind groups', () => {
  assert.equal(formatSignature(previewSignature({ name: 'page', parameters: [] }, draft('add_required_parameter', { parameterName: 'zone' }))), 'page(zone)')
  const source = definition([parameter('a', 'positional_only'), parameter('b'), parameter('args', 'var_positional'), parameter('mode', 'keyword_only'), parameter('kwargs', 'var_keyword')])
  assert.equal(formatSignature(previewSignature(source, draft('add_required_parameter', { parameterName: 'new', kind: 'positional_only' }))), 'f(a, new, /, b, *args, mode, **kwargs)')
  assert.equal(formatSignature(previewSignature(source, draft('add_required_parameter', { parameterName: 'new', kind: 'positional_or_keyword' }))), 'f(a, /, b, new, *args, mode, **kwargs)')
  assert.equal(formatSignature(previewSignature(source, draft('add_required_parameter', { parameterName: 'new', kind: 'keyword_only' }))), 'f(a, /, b, *args, mode, new, **kwargs)')
})

test('explicit insert_before preview preserves declared order and does not auto-fix illegal signatures', () => {
  const source = definition([parameter('a', 'positional_only'), parameter('b')])
  const candidate = previewSignature(source, draft('add_required_parameter', { parameterName: 'new', kind: 'keyword_only', insertBefore: 'a' }))
  assert.deepEqual(candidate.parameters.map(item => item.name), ['new', 'a', 'b'])
  assert.equal(candidate.parameters[0].kind, 'keyword_only')
  assert.equal(previewSignature(source, draft('add_required_parameter', { parameterName: 'new', insertBefore: 'missing' })), null)
})

test('removal preview handles last positional-only, keyword-only, and last overall parameter', () => {
  assert.equal(formatSignature(previewSignature(definition([parameter('a', 'positional_only'), parameter('b')]), draft('remove_parameter', { parameterName: 'a' }))), 'f(b)')
  assert.equal(formatSignature(previewSignature(definition([parameter('a'), parameter('mode', 'keyword_only')]), draft('remove_parameter', { parameterName: 'mode' }))), 'f(a)')
  assert.equal(formatSignature(previewSignature(definition([parameter('a')]), draft('remove_parameter', { parameterName: 'a' }))), 'f()')
})

test('rename preview changes only selected name and preserves optional default, annotations, and metadata', () => {
  const source = definition([parameter('a'), parameter('timeout', 'keyword_only', { has_default: true, default_source: '30', annotation_source: 'int' })])
  const before = structuredClone(source)
  const candidate = previewSignature(source, draft('rename_parameter', { parameterName: 'timeout', newParameterName: 'delay' }))
  assert.equal(formatSignature(candidate), 'f(a, *, delay: int=30)')
  assert.equal(candidate.return_annotation_source, 'str')
  assert.deepEqual(candidate.parameters[1], { ...source.parameters[1], name: 'delay' })
  assert.deepEqual(source, before)
  assert.notEqual(candidate.parameters[0], source.parameters[0])
})

test('make-required preview removes only default without reordering or repairing Python grammar', () => {
  const source = definition([parameter('a', 'positional_only', { has_default: true, default_source: '1' }), parameter('b', 'positional_or_keyword', { has_default: true, default_source: 'None', annotation_source: 'str' })])
  const snapshot = structuredClone(source)
  const candidate = previewSignature(source, draft('make_parameter_required', { parameterName: 'b' }))
  assert.equal(formatSignature(candidate), 'f(a=1, /, b: str)')
  assert.deepEqual(candidate.parameters[1], { ...source.parameters[1], has_default: false, default_source: null })
  assert.deepEqual(candidate.parameters[0], source.parameters[0])
  assert.deepEqual(source, snapshot)
})

test('incomplete, unsupported, or missing-target drafts have unavailable preview', () => {
  const source = definition([parameter('a', 'positional_only'), parameter('args', 'var_positional')])
  assert.equal(previewSignature(null, createChangeDraft()), null)
  assert.equal(previewSignature(source, createChangeDraft()), null)
  assert.equal(previewSignature(source, draft('remove_parameter', { parameterName: 'missing' })), null)
  assert.equal(previewSignature(source, draft('rename_parameter', { parameterName: 'a', newParameterName: 'b' })), null)
  assert.equal(previewSignature(source, draft('make_parameter_required', { parameterName: 'a' })), null)
  assert.equal(previewSignature(source, draft('remove_parameter', { parameterName: 'args' })), null)
  assert.equal(previewSignature(source, draft('add_required_parameter', { parameterName: 'x', kind: 'var_positional' })), null)
})

test('real operation summaries distinguish four types and non-add null compatibility field', () => {
  const source = { name: 'f', parameters: [parameter('timeout', 'positional_or_keyword', { has_default: true, default_source: '30' })] }
  const cases = [
    [{ change_type: 'add_required_parameter', added_parameter: { name: 'timezone' } }, '新增必填参数 timezone', 'timezone', null],
    [{ change_type: 'remove_parameter', parameter_name: 'timeout' }, '删除参数 timeout', null, 'timeout'],
    [{ change_type: 'rename_parameter', parameter_name: 'timeout', new_parameter_name: 'delay' }, 'timeout → delay', 'delay', 'timeout'],
    [{ change_type: 'make_parameter_required', parameter_name: 'timeout' }, 'timeout=30 → timeout（可选 → 必填）', 'timeout', null],
  ]
  for (const [operation, detail, highlightName, removedName] of cases) {
    const summary = describeChange({ change_type: operation.change_type, operation, added_parameter: null, before: source })
    assert.equal(summary.detail, detail)
    assert.equal(summary.highlightName, highlightName)
    assert.equal(summary.removedName, removedName)
  }
})

test('make-required presentation retains the parameter and leaves canonical Before/After unchanged', () => {
  const before = definition([parameter('timeout', 'keyword_only', { has_default: true, default_source: 'None' })])
  const after = previewSignature(before, draft('make_parameter_required', { parameterName: 'timeout' }))
  const change = { change_type: 'make_parameter_required', operation: { change_type: 'make_parameter_required', parameter_name: 'timeout' }, before, after, added_parameter: null }
  const snapshot = structuredClone(change)
  const description = describeChange(change)
  assert.equal(description.removedName, null, 'the existing parameter name must not be presented as deleted')
  assert.equal(description.highlightName, 'timeout')
  assert.equal(description.detail, 'timeout=None → timeout（可选 → 必填）')
  assert.equal(formatSignature(change.before), 'f(*, timeout=None)')
  assert.equal(formatSignature(change.after), 'f(*, timeout)')
  assert.deepEqual(change, snapshot)
})

test('legacy add description still works without operation; missing non-add is never read as add', () => {
  assert.equal(describeChange({ added_parameter: { name: 'zone' } }).detail, '新增必填参数 zone')
  const missing = describeChange({ change_type: 'rename_parameter', added_parameter: null })
  assert.equal(missing.label, '重命名参数')
  assert.equal(missing.detail, '变更信息未提供')
  assert.equal(missing.highlightName, null)
  assert.equal(describeChange({ change_type: 'remove_parameter', operation: { change_type: 'rename_parameter', parameter_name: 'a', new_parameter_name: 'b' } }).label, '未知变更')
})
