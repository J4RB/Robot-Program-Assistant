import React, { createContext, useContext, useState, useCallback } from 'react';

/**
 * Context for managing editor state across all tabs
 * Persists the loaded program and chat history when switching tabs
 */
const EditorContext = createContext();

export function EditorProvider({ children }) {
  const [programId, setProgramId] = useState(null);
  const [programName, setProgramName] = useState(null);
  const [programData, setprogramData] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [code, setCode] = useState('');
  const [selectedCodeSelection, setSelectedCodeSelection] = useState(null);
  const [pendingProgramContexts, setPendingProgramContexts] = useState([]);
  const [editorLanguage, setEditorLanguage] = useState('json');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [searchSearched, setSearchSearched] = useState(false);

  const loadProgram = useCallback((newProgramId, newProgramName = null) => {
    setProgramId(newProgramId);
    setProgramName(newProgramName);
  }, []);

  const clearProgram = useCallback(() => {
    setProgramId(null);
    setProgramName(null);
    setprogramData(null);
    setChatMessages([]);
    setCode('');
    setSelectedCodeSelection(null);
    setPendingProgramContexts([]);
  }, []);

  const addChatMessage = useCallback((message) => {
    setChatMessages(prev => [...prev, message]);
  }, []);

  const clearChat = useCallback(() => {
    setChatMessages([]);
  }, []);

  const addPendingProgramContext = useCallback((context) => {
    setPendingProgramContexts((prev) => {
      const exists = prev.some((ctx) => (
        ctx.fileName === context.fileName
        && ctx.source === context.source
        && ctx.startLine === context.startLine
        && ctx.endLine === context.endLine
        && ctx.text === context.text
      ));

      if (exists) {
        return prev;
      }

      const id = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
      return [...prev, { ...context, id }];
    });
  }, []);

  const removePendingProgramContext = useCallback((contextId) => {
    setPendingProgramContexts((prev) => prev.filter((ctx) => ctx.id !== contextId));
  }, []);

  const clearPendingProgramContexts = useCallback(() => {
    setPendingProgramContexts([]);
  }, []);

  const clearSearchState = useCallback(() => {
    setSearchQuery('');
    setSearchResults([]);
    setSearchSearched(false);
  }, []);

  const value = {
    // Program data
    programId,
    programName,
    programData,
    setprogramData,
    loadProgram,
    clearProgram,

    // Editor state
    code,
    setCode,
    selectedCodeSelection,
    setSelectedCodeSelection,
    editorLanguage,
    setEditorLanguage,

    // Chat state
    chatMessages,
    addChatMessage,
    clearChat,
    pendingProgramContexts,
    addPendingProgramContext,
    removePendingProgramContext,
    clearPendingProgramContexts,

    // Program search state
    searchQuery,
    setSearchQuery,
    searchResults,
    setSearchResults,
    searchSearched,
    setSearchSearched,
    clearSearchState,
  };

  return (
    <EditorContext.Provider value={value}>
      {children}
    </EditorContext.Provider>
  );
}

export function useEditor() {
  const context = useContext(EditorContext);
  if (!context) {
    throw new Error('useEditor must be used within EditorProvider');
  }
  return context;
}
