// Reading and questions have their own cancellation, without touching Workflow.
export function createRequestGate() {
  let active = null
  return {
    begin() { active?.controller.abort(); active = { controller: new AbortController() }; return active },
    current(request) { return active === request && !request.controller.signal.aborted },
    cancel() { active?.controller.abort(); active = null },
  }
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
