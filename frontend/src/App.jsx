import { useEffect, useState } from 'react'
import { WorkflowProvider } from './state/WorkflowContext.jsx'
import AppShell from './components/AppShell.jsx'
import UploadPage from './pages/UploadPage.jsx'
import FunctionSelectPage from './pages/FunctionSelectPage.jsx'
import ChangePage from './pages/ChangePage.jsx'
import ReportPage from './pages/ReportPage.jsx'
import PlannedPage from './pages/PlannedPage.jsx'

const pages = { upload: UploadPage, functions: FunctionSelectPage, change: ChangePage, report: ReportPage, planned: PlannedPage }
function currentPage() {
  const page = window.location.hash.replace(/^#\/?/, '') || 'upload'
  return Object.hasOwn(pages, page) ? page : 'planned'
}

export default function App() {
  const [page, setPage] = useState(currentPage)
  useEffect(() => {
    const changed = () => setPage(currentPage())
    window.addEventListener('hashchange', changed)
    return () => window.removeEventListener('hashchange', changed)
  }, [])
  function navigate(nextPage) {
    window.location.hash = nextPage
    setPage(currentPage())
    window.scrollTo({ top: 0 })
  }
  const Page = pages[page]
  return <WorkflowProvider><AppShell page={page} navigate={navigate}><Page navigate={navigate} /></AppShell></WorkflowProvider>
}
