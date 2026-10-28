import React from 'react'
import ReactDOM from 'react-dom/client'
import Portal from './Portal.tsx'
import Admin from './App.tsx'
import './index.css'

const path = window.location.pathname
const root = ReactDOM.createRoot(document.getElementById('root')!)
root.render(
  <React.StrictMode>
    {path.startsWith('/admin') || path === '/entrar-admin' || path === '/dashboard' || path.startsWith('/books') || path.startsWith('/students') || path.startsWith('/classes') || path.startsWith('/loans')
      ? <Admin />
      : <Portal />}
  </React.StrictMode>,
)
