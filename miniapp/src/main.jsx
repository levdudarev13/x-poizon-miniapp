import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/global.css'
import App from './App.jsx'
import { initVkMiniAppBridge } from './utils/vkBridgeInit.js'

function renderApp() {
  createRoot(document.getElementById('root')).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

void initVkMiniAppBridge().finally(renderApp)
