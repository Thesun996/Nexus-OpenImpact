import { createContext, useCallback, useContext, useEffect, useMemo, useReducer, useRef } from 'react'
import { apiClient } from '../api/client.js'
import inspectFixture from '../demo/fixtures/inspect.json'
import validateFixture from '../demo/fixtures/validate.json'
import analyzeFixture from '../demo/fixtures/analyze.json'
import { createWorkflowActions } from './actions.js'
import { createInitialState, DEMO_FINGERPRINT, workflowReducer } from './workflow.js'

const WorkflowContext = createContext(null)

async function loadDemoFile(signal) {
  const response = await fetch(`${import.meta.env.BASE_URL}samples/signature_change.zip`, { signal })
  if (!response.ok) throw new Error('sample_unavailable')
  const bytes = await response.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', bytes)
  const fingerprint = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, '0')).join('')
  if (fingerprint !== DEMO_FINGERPRINT) throw new Error('sample_mismatch')
  return new File([bytes], 'signature_change.zip', { type: 'application/zip' })
}

export function WorkflowProvider({ children }) {
  const [state, reactDispatch] = useReducer(workflowReducer, undefined, createInitialState)
  const latest = useRef(state)
  // Update the event/request snapshot immediately, before React's next render.
  // This also prevents a second click or an old response observing stale inputs.
  const dispatch = useCallback((action) => {
    latest.current = workflowReducer(latest.current, action)
    reactDispatch(action)
  }, [])
  const actions = useMemo(() => createWorkflowActions({
    getState: () => latest.current, dispatch, client: apiClient, loadDemoFile,
    demo: { inspect: inspectFixture, validation: validateFixture, report: analyzeFixture },
  }), [dispatch])

  useEffect(() => {
    void actions.checkHealth()
    return () => actions.dispose()
  }, [actions])

  return <WorkflowContext.Provider value={{ state, actions }}>{children}</WorkflowContext.Provider>
}

export function useWorkflow() {
  const workflow = useContext(WorkflowContext)
  if (!workflow) throw new Error('useWorkflow requires WorkflowProvider')
  return workflow
}
