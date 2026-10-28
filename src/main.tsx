import React from 'react'
import ReactDOM from 'react-dom/client'
import Portal from './Portal.tsx'
import Admin from './App.tsx'
import './index.css'

// Build each public-facing site independently with VITE_APP_SITE=student|admin.
const isAdminSite = import.meta.env.VITE_APP_SITE === 'admin'
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{isAdminSite ? <Admin /> : <Portal />}</React.StrictMode>,
)
