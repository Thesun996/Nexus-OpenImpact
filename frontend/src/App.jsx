import { lazy, Suspense, useEffect, useState } from 'react'
import { pageDirection } from './motion/pageTransition.js'
import WorkflowPages from './motion/WorkflowPages.jsx'
import { WorkflowProvider } from './state/WorkflowContext.jsx'
import AppShell from './components/AppShell.jsx'
import UploadPage from './pages/UploadPage.jsx'
import FunctionSelectPage from './pages/FunctionSelectPage.jsx'
import ChangePage from './pages/ChangePage.jsx'
import EntryGate from './components/entry/EntryGate.jsx'

const ReportPage = lazy(() => import('./pages/ReportPage.jsx'))
const HistoryPage = lazy(() => import('./pages/HistoryPage.jsx'))
const ProjectLibraryPage = lazy(() => import('./pages/ProjectLibraryPage.jsx'))
const AnalysisTasksPage = lazy(() => import('./pages/AnalysisTasksPage.jsx'))
const PlannedPage = lazy(() => import('./pages/PlannedPage.jsx'))

const pages = { upload: UploadPage, functions: FunctionSelectPage, change: ChangePage, report: ReportPage, projects: ProjectLibraryPage, tasks: AnalysisTasksPage, history: HistoryPage, planned: PlannedPage }
function currentPage() {
  const page = window.location.hash.replace(/^#\/?/, '') || 'upload'
  return Object.hasOwn(pages, page) ? page : 'planned'
}

export default function App() {
  const [route, setRoute] = useState(() => ({ page: currentPage(), direction: 0, sequence: 0 }))
  const { page } = route
  function moveTo(next) {
    setRoute((previous) => previous.page === next ? previous : { page: next, direction: pageDirection(previous.page, next), sequence: previous.sequence + 1 })
  }
  useEffect(() => {
    const changed = () => moveTo(currentPage())
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  function navigate(nextPage) {
    window.location.hash = nextPage
    moveTo(currentPage())
  }
  const Page = pages[page]
  return <EntryGate onEnter={() => navigate('upload')}><WorkflowProvider><AppShell page={page} navigate={navigate}><WorkflowPages {...route}><Suspense fallback={<section className="detail-card empty-state-card" role="status"><h2>正在加载页面</h2></section>}><Page navigate={navigate} /></Suspense></WorkflowPages></AppShell></WorkflowProvider></EntryGate>
}
