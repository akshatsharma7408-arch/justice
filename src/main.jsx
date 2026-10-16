import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './App.css'
import App from './App.jsx'
import { verifyGeminiConnection } from './config/gemini'

// Automatically verify Gemini connection and active model on application boot
verifyGeminiConnection();

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
