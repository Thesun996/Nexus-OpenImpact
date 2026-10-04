import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './tokens.css'
import '../styles.css'
import './react.css'

createRoot(document.getElementById('root')).render(<StrictMode><App /></StrictMode>)
