import React from 'react'
import ReactDOM from 'react-dom/client'
import Portal from './Portal.tsx'
import Admin from './App.tsx'
import './index.css'

const path = window.location.pathname
const isAdmin = path.startsWith('/admin') || ['/entrar-admin', '/dashboard', '/books', '/students', '/classes', '/loans'].some(prefix => path === prefix || path.startsWith(`${prefix}/`))
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>{isAdmin ? <Admin /> : <Portal />}</React.StrictMode>,
)
