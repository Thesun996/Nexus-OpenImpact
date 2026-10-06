import { useEffect, useState } from 'react'
import { pageDirection } from './motion/pageTransition.js'
import WorkflowPages from './motion/WorkflowPages.jsx'
import { WorkflowProvider } from './state/WorkflowContext.jsx'
import AppShell from './components/AppShell.jsx'
import UploadPage from './pages/UploadPage.jsx'
import FunctionSelectPage from './pages/FunctionSelectPage.jsx'
import ChangePage from './pages/ChangePage.jsx'
import ReportPage from './pages/ReportPage.jsx'
import PlannedPage from './pages/PlannedPage.jsx'
import EntryGate from './components/entry/EntryGate.jsx'

const pages = { upload: UploadPage, functions: FunctionSelectPage, change: ChangePage, report: ReportPage, planned: PlannedPage }
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
  return <EntryGate onEnter={() => navigate('upload')}><WorkflowProvider><AppShell page={page} navigate={navigate}><WorkflowPages {...route}><Page navigate={navigate} /></WorkflowPages></AppShell></WorkflowProvider></EntryGate>
}
