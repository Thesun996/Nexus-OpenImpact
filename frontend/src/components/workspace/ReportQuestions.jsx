import { useEffect, useMemo, useRef, useState } from 'react'
import { apiClient } from '../../api/client.js'
import { useSourceWorkspace } from './SourceWorkspace.jsx'
import { checkedSuggestions, createRequestGate } from './requestGate.js'
import ExplanationText from '../report/ExplanationText.jsx'

export default function ReportQuestions({ report, findingIndex }) {
  const workspace = useSourceWorkspace()
  const snapshot = workspace?.snapshot
  const scope = useMemo(() => ({}), [report, findingIndex, snapshot?.revision, snapshot?.source])
  const latest = useRef(scope); latest.current = scope
  const [conversation, setConversation] = useState({ scope, turns: [] })
  const [recommendations, setRecommendations] = useState({ scope, result: null })
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState(null)
  const gate = useRef(createRequestGate())
  const pending = useRef(false)
  const turns = conversation.scope === scope ? conversation.turns : []
  const suggestions = recommendations.scope === scope ? recommendations.result : null
  const enabled = snapshot?.mode === 'project' && snapshot.source && snapshot.fingerprint && snapshot.change && snapshot.report === report
  useEffect(() => {
    gate.current.cancel(); pending.current = false; setConversation({ scope, turns: [] }); setRecommendations({ scope, result: null }); setDraft(''); setBusy(''); setError(null)
    return () => gate.current.cancel()
  }, [scope])

  async function runRequest(kind, question = '') {
    if (!enabled || pending.current || (kind === 'answer' && !question.trim())) return
    pending.current = true
    const request = gate.current.begin(), requestedScope = scope
    setBusy(kind); setError(null)
    if (kind === 'suggestions') setRecommendations({ scope, result: null })
    try {
      if (kind === 'suggestions') {
        const result = await apiClient.questionSuggestions(snapshot.source, snapshot.change, snapshot.fingerprint, {
          findingIndex, analysisRoot: snapshot.analysisRoot, signal: request.controller.signal })
        if (!gate.current.current(request) || latest.current !== requestedScope) return
        setRecommendations({ scope, result: checkedSuggestions(result, snapshot.fingerprint, findingIndex) })
        return
      }
      const history = turns.slice(-3).flatMap(turn => [{ role: 'user', content: turn.question.slice(0, 800) }, { role: 'assistant', content: turn.answer.slice(0, 800) }])
      const result = await apiClient.question(snapshot.source, snapshot.change, snapshot.fingerprint, { question: question.trim(), findingIndex,
        history, analysisRoot: snapshot.analysisRoot, signal: request.controller.signal })
      if (!gate.current.current(request) || latest.current !== requestedScope) return
      if (result.project_fingerprint !== snapshot.fingerprint || result.finding_index !== (findingIndex ?? null)
        || typeof result.answer !== 'string' || !Array.isArray(result.citations) || !['rule', 'deepseek', 'fallback'].includes(result.provider))
        throw new Error('追问响应与当前报告不匹配，请重新分析。')
      setConversation({ scope, turns: [...turns.slice(-9), { ...result, question: question.trim() }] }); setDraft('')
    } catch (failure) {
      if (gate.current.current(request) && latest.current === requestedScope && failure.name !== 'AbortError') setError(failure.message)
    } finally {
      if (gate.current.current(request) && latest.current === requestedScope) { pending.current = false; setBusy('') }
    }
  }
  return <section className="oi-report-questions" aria-label="围绕本次分析继续提问">
    <header><div><h2>继续了解这次变更</h2><p>{findingIndex != null ? '围绕当前选中的影响记录提问；切换记录后开始新的对话。' : '当前没有确定影响记录，可以询问报告的分析范围。'}</p></div><span>源码证据优先</span></header>
    <div className="oi-question-suggestions" aria-busy={busy === 'suggestions'}>
      <button className="oi-generate-questions" type="button" disabled={!enabled || !!busy} onClick={() => void runRequest('suggestions')}>{suggestions?.status === 'available' ? '重新生成推荐追问' : '生成推荐追问'}</button>
      <p className="oi-question-generation-note">让模型根据当前变更和源码证据提出检查问题；每次主动生成请求一次模型，也可以直接输入问题。</p>
      {suggestions && <p role="status">{suggestions.status === 'available' ? '模型推荐追问 · ' : ''}{suggestions.message}</p>}
      {suggestions?.questions.map(item => <button type="button" key={item.question} disabled={!enabled || !!busy} onClick={() => void runRequest('answer', item.question)}>{item.question}</button>)}
    </div>
    {!enabled && <p>请在实际项目模式完成分析后提问。演示记录不发送真实模型请求。</p>}
    {report.coverage?.status === 'partial' && <p className="state-message">覆盖不完整，回答仅依据本次已解析的证据。</p>}
    <div className="oi-question-conversation" aria-live="polite" aria-busy={busy === 'answer'}>{turns.map((turn, index) => <article key={index}>
      <h3>{turn.question}</h3><span className="oi-question-provider">{turn.provider === 'deepseek' ? '模型辅助回答' : turn.provider === 'fallback' ? '规则回答 · 模型暂不可用' : '规则回答'}{turn.status === 'limited' ? ' · 证据或回答范围有限' : ''}</span>
      <ExplanationText text={turn.answer} />
      {!!turn.citations.length && <div className="oi-question-citations"><span>查看依据</span>{turn.citations.map(citation => <button type="button" className="oi-source-link" key={citation.id} onClick={() => workspace.openFile(citation.file, citation.line)}>{citation.file}:{citation.line}</button>)}</div>}
    </article>)}</div>
    {busy && <p role="status">{busy === 'suggestions' ? '正在根据当前证据生成推荐追问…' : '正在核对当前项目证据并回答…'}</p>}{error && <p className="state-message error" role="alert">{error}</p>}
    <form onSubmit={event => { event.preventDefault(); void runRequest('answer', draft) }}><label htmlFor="oi-report-question">你的问题</label><textarea id="oi-report-question" value={draft} onChange={event => setDraft(event.target.value)} maxLength={1000} rows={3} disabled={!enabled || !!busy} placeholder="例如：为什么上游函数也需要检查？" /><div><small>仅解释当前变更报告，不执行源码或修改分析结论。启用模型时会发送相关证据片段和最近对话。</small><button className="primary-action" type="submit" disabled={!enabled || !!busy || !draft.trim()}>提交追问</button></div></form>
  </section>
}
