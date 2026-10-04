import { useWorkflow } from '../state/WorkflowContext.jsx'

const steps = [
  { page: 'upload', label: '上传项目' },
  { page: 'functions', label: '选择函数' },
  { page: 'change', label: '配置变更' },
  { page: 'report', label: '查看报告' },
]

export default function WorkflowSteps({ page }) {
  const { state } = useWorkflow()
  const isDemo = state.mode === 'demo'
  const complete = [
    Boolean(state.inspect && (isDemo || state.file)),
    Boolean(state.selectedSymbolId),
    state.validation?.validation?.valid === true,
    Boolean(state.report),
  ]

  return (
    <section className="oi-stepper" aria-label="分析步骤">
      <ol className="oi-progress-steps">
        {steps.map((step, index) => {
          const current = page === step.page
          const done = complete[index]
          const status = current ? '当前步骤' : done ? (isDemo ? '演示已就绪' : '已完成') : '未开始'
          return (
            <li
              key={step.page}
              className={current ? 'current' : done ? 'done' : undefined}
              aria-current={current ? 'step' : undefined}
            >
              <span aria-hidden="true">{done && !current ? '✓' : index + 1}</span>
              <b>{step.label}</b>
              <small>{status}</small>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
