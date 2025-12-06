import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@/styles/globals.css';

function App() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <h1 className="text-4xl font-display p-8 text-primary">Amelia Dashboard</h1>
    </div>
  );
}

const rootElement = document.getElementById('root');
if (!rootElement) throw new Error('Root element not found');

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>
);
