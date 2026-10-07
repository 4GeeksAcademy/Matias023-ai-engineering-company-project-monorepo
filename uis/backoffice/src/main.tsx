import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider } from './auth'
import { installErrorCapture } from './services/errorCapture'
import { trackInitialPage } from './services/pageTracker'
import './index.css'
import App from './App.tsx'

// Install global frontend error telemetry before any rendering.
installErrorCapture()
// Track the initial page load once the app is mounted.
trackInitialPage()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
