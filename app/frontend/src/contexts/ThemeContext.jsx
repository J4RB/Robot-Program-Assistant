import React, { createContext, useContext, useState, useEffect } from 'react';

/**
 * Context for managing application theme (light/dark mode)
 * Preferences are persisted to localStorage
 */
const ThemeContext = createContext();

export function ThemeProvider({ children }) {
    const [isDark, setIsDark] = useState(() => {
        // Check localStorage first, then system preference
        const saved = localStorage.getItem('theme-mode');
        if (saved) {
            return saved === 'dark';
        }
        // Check system preference
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
    });

    // Update localStorage and DOM when theme changes
    useEffect(() => {
        localStorage.setItem('theme-mode', isDark ? 'dark' : 'light');
        const root = document.documentElement;
        if (isDark) {
            root.classList.add('dark-mode');
        } else {
            root.classList.remove('dark-mode');
        }
    }, [isDark]);

    const toggleTheme = () => {
        setIsDark(prev => !prev);
    };

    const value = {
        isDark,
        toggleTheme,
    };

    return (
        <ThemeContext.Provider value={value}>
            {children}
        </ThemeContext.Provider>
    );
}

export function useTheme() {
    const context = useContext(ThemeContext);
    if (!context) {
        throw new Error('useTheme must be used within a ThemeProvider');
    }
    return context;
}
