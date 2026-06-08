import React from 'react';
import { BrowserRouter, Routes, Route, Link } from 'react-router-dom';
import ProgramSearch from './pages/ProgramSearch';
import Editor from './pages/Editor';
import Simulation from './pages/Simulation';
import { EditorProvider } from './contexts/EditorContext';
import { ThemeProvider, useTheme } from './contexts/ThemeContext';
import './App.css';

function AppContent() {
  const { isDark, toggleTheme } = useTheme();

  return (
    <div className="app">
      <nav className="navbar">
        <div className="navbar-container">
          <Link to="/" className="navbar-logo">
            Robot Program Editor
          </Link>
          <div className="nav-links">
            <Link to="/">Search</Link>
            <Link to="/edit">Edit</Link>
            <Link to="/simulate">Simulate</Link>
          </div>
          <button
            className="theme-toggle"
            onClick={toggleTheme}
            title={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
            aria-label="Toggle theme"
          >
            {isDark ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            )}
          </button>
        </div>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<ProgramSearch />} />
          <Route path="/edit" element={<Editor />} />
          <Route path="/simulate" element={<Simulation />} />
        </Routes>
      </main>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <EditorProvider>
          <AppContent />
        </EditorProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}

export default App;
