// Reading and questions have their own cancellation, without touching Workflow.
export function createRequestGate() {
  let active = null
  return {
    begin() { active?.controller.abort(); active = { controller: new AbortController() }; return active },
    current(request) { return active === request && !request.controller.signal.aborted },
    cancel() { active?.controller.abort(); active = null },
  }
}

export function checkedSuggestions(result, fingerprint, findingIndex) {
  if (!result || result.project_fingerprint !== fingerprint || result.finding_index !== (findingIndex ?? null)
    || !['deepseek', 'rule', 'fallback'].includes(result.provider) || !['available', 'unavailable'].includes(result.status)
    || typeof result.message !== 'string' || !Array.isArray(result.questions)
    || (result.status === 'unavailable' && result.questions.length !== 0)
    || (result.status === 'available' && (result.provider !== 'deepseek' || result.questions.length < 2 || result.questions.length > 3))
    || result.questions.some(item => !item || typeof item.question !== 'string' || !item.question.trim()
      || item.question.length > 160 || !Array.isArray(item.citations))) {
    throw new Error('推荐追问响应与当前报告不匹配，请重新分析。')
  }
  return result
}

export function sourceTree(files) {
  const root = { directories: Object.create(null), files: [] }
  for (const file of files) {
    const parts = file.path.split('/')
    let node = root
    for (const part of parts.slice(0, -1)) {
      node.directories[part] ||= { directories: Object.create(null), files: [] }
      node = node.directories[part]
    }
    node.files.push(file)
  }
  return root
}
