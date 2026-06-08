import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels';
import axios from 'axios';
import TreeView from '../components/TreeView';
import RagChat from '../components/RagChat';
import { useEditor } from '../contexts/EditorContext';
import { useTheme } from '../contexts/ThemeContext';
import { sanitizeProgramContext, buildContextLabel } from '../utils/programContext';
import './Editor.css';

function findActionLineNumber(lines, guid) {
  const guidNeedle = `"guid": "${guid}"`;

  const guidLineIndex = lines.findIndex((line) => line.includes(guidNeedle));
  if (guidLineIndex === -1) {
    return 0;
  }

  for (let index = guidLineIndex; index >= Math.max(0, guidLineIndex - 160); index -= 1) {
    const currentLine = lines[index].trim();
    if (currentLine !== '{') {
      continue;
    }

    const nextLine = lines[index + 1]?.trim() || '';
    if (nextLine.startsWith('"children"')) {
      return index + 1;
    }
  }

  return guidLineIndex + 1;
}

function getActionNameFromProgramNode(node) {
  const contributedNode = node?.contributedNode;
  const parameters = contributedNode?.parameters;

  if (typeof parameters?.moveType === 'string' && parameters.moveType.trim()) {
    return parameters.moveType.trim();
  }

  if (typeof parameters?.action === 'string' && parameters.action.trim()) {
    return parameters.action.trim();
  }

  if (typeof contributedNode?.type === 'string' && contributedNode.type.trim()) {
    return contributedNode.type.trim();
  }

  return '';
}

function collectActionNodes(nodes, lines, children = []) {
  if (!Array.isArray(nodes)) {
    return children;
  }

  nodes.forEach((node) => {
    if (!node || typeof node !== 'object') {
      return;
    }

    const actionName = getActionNameFromProgramNode(node);
    const guid = typeof node.guid === 'string' ? node.guid.trim() : '';

    if (actionName && guid) {
      children.push({
        name: actionName,
        type: 'action',
        guid,
        index: children.length,
        lineNumber: findActionLineNumber(lines, guid),
      });
    }

    if (Array.isArray(node.children) && node.children.length > 0) {
      collectActionNodes(node.children, lines, children);
    }
  });

  return children;
}

function buildTreeFromCode(code, rootName) {
  if (!code || typeof code !== 'string') {
    return null;
  }

  try {
    const parsed = JSON.parse(code);
    const lines = code.split(/\r?\n/);
    const rootChildren = parsed?.program?.programContent?.children;
    const codeContainer = Array.isArray(rootChildren)
      ? rootChildren.find((node) => node?.contributedNode?.type === 'ur-code')
      : null;
    const actionChildren = collectActionNodes(codeContainer?.children || [], lines, []);

    if (!actionChildren.length) {
      return null;
    }

    return {
      name: rootName,
      type: 'program',
      children: actionChildren,
    };
  } catch {
    return null;
  }
}

function EditorPage() {
  const navigate = useNavigate();
  const { isDark } = useTheme();
  const {
    programId,
    programName,
    programData,
    setprogramData,
    code,
    setCode,
    editorLanguage,
    setEditorLanguage,
    setSelectedCodeSelection,
    addPendingProgramContext,
    clearPendingProgramContexts,
    clearChat,
  } = useEditor();
  const selectionDisposableRef = useRef(null);
  const actionDisposablesRef = useRef([]);
  const contextFileNameRef = useRef('program.urpx');
  const editorRef = useRef(null);

  // State variables
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatMenuOpen, setChatMenuOpen] = useState(false);
  const [clearingChatMemory, setClearingChatMemory] = useState(false);
  const {
    displayTreeStructure,
    treeError,
  } = useMemo(() => {
    const rootName = programData?.metadata?.name || programData?.name || programName || programId || 'Program';
    const parsedTree = buildTreeFromCode(code, rootName);

    return {
      displayTreeStructure: parsedTree,
      treeError: parsedTree ? '' : 'Unable to build the Program Tree from the current editor JSON.',
    };
  }, [code, programData, programName, programId]);

  const getFileIcon = (language) => {
    if (language === 'json') return '{ }';
    if (language === 'xml') return '< >';
    return '⌨️';
  };

  const getFileExtension = (language) => {
    if (language === 'json') return '.json';
    if (language === 'xml') return '.urpx';
    return '';
  };

  const API_BASE = 'http://localhost:8000';

  const handleClearChatMemory = useCallback(async () => {
    setClearingChatMemory(true);
    setChatMenuOpen(false);

    try {
      const response = await fetch(`${API_BASE}/api/chat/clear-memory`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`Failed to clear memory: ${response.status}`);
      }
    } catch (error) {
      console.error('Failed to clear backend memory:', error);
      alert('Failed to clear backend chat memory. Local history was still reset.');
    } finally {
      clearChat();
      clearPendingProgramContexts();
      setClearingChatMemory(false);
    }
  }, [API_BASE, clearChat, clearPendingProgramContexts]);

  useEffect(() => {
    contextFileNameRef.current = `${programData?.name || programData?.metadata?.name || programName || programId || 'program'}.urpx`;
  }, [programData, programName, programId]);

  const addContextToChat = useCallback((rawContext, source, startLine, endLine) => {
    const sanitized = sanitizeProgramContext(rawContext || '');
    if (!sanitized.trim()) {
      alert('No valid program context found.');
      return;
    }

    const fileName = contextFileNameRef.current;
    addPendingProgramContext({
      text: sanitized,
      source,
      chars: sanitized.length,
      fileName,
      label: buildContextLabel(fileName, startLine, endLine),
      startLine,
      endLine,
    });
  }, [addPendingProgramContext]);

  const getFullLineRangeText = useCallback((model, startLine, endLine) => {
    const selectedLines = [];
    for (let line = startLine; line <= endLine; line++) {
      selectedLines.push(model.getLineContent(line));
    }
    return selectedLines.join('\n');
  }, []);

  // Cleanup old per-program layout keys from localStorage on component mount
  useEffect(() => {
    const cleanupOldLayouts = () => {
      const keysToRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        // Remove old per-program layout keys like "robot-editor-layout-Program1"
        if (key && key.startsWith('robot-editor-layout-')) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key));
    };
    cleanupOldLayouts();
  }, []);

  const loadProgram = useCallback(async () => {
    setLoading(true);
    try {
      // Load program JSON
      const response = await axios.get(
        `${API_BASE}/api/programs/${programId}/json`
      );
      setprogramData(response.data);

      // Set code as the main program content
      let programContent = '';

      if (response.data.main_content) {
        programContent = response.data.main_content;
      } else if (response.data.content && typeof response.data.content === 'object') {
        // Get first file content from object
        const contents = Object.values(response.data.content);
        programContent = contents.length > 0 ? contents[0] : JSON.stringify(response.data.content, null, 2);
      } else if (response.data.data) {
        programContent = JSON.stringify(response.data.data, null, 2);
      } else if (response.data.error) {
        programContent = `Error: ${response.data.error}`;
      } else {
        programContent = JSON.stringify(response.data, null, 2);
      }

      setCode(programContent);
      setSelectedCodeSelection(null);
      clearPendingProgramContexts();

      // Detect language based on format or file extension
      let language = 'json';
      if (response.data.content && typeof response.data.content === 'object') {
        const fileNames = Object.keys(response.data.content);
        if (fileNames.length > 0) {
          const mainFile = fileNames[0];
          if (mainFile.endsWith('.urp')) language = 'xml';
        }
      }
      setEditorLanguage(language);
    } catch (error) {
      console.error('Failed to load program:', error);
      alert('Failed to load program. Make sure the API is running.');
    } finally {
      setLoading(false);
    }
  }, [programId, setprogramData, setCode, setSelectedCodeSelection, setEditorLanguage, clearPendingProgramContexts]);
  const handleEditorMount = useCallback((editorInstance) => {
    editorRef.current = editorInstance;

    const syncSelectionToContext = () => {
      const model = editorInstance.getModel();
      const selection = editorInstance.getSelection();

      if (!model || !selection || selection.isEmpty()) {
        setSelectedCodeSelection(null);
        return;
      }

      const startLine = selection.startLineNumber;
      const endLine = selection.endLineNumber;
      const selectedText = getFullLineRangeText(model, startLine, endLine);
      if (!selectedText) {
        setSelectedCodeSelection(null);
        return;
      }

      setSelectedCodeSelection({
        text: selectedText,
        startLine,
        endLine,
      });
    };

    syncSelectionToContext();

    if (selectionDisposableRef.current) {
      selectionDisposableRef.current.dispose();
    }
    selectionDisposableRef.current = editorInstance.onDidChangeCursorSelection(syncSelectionToContext);

    const addFileAction = editorInstance.addAction({
      id: 'add-file-to-chat',
      label: 'Add file to chat',
      contextMenuGroupId: 'navigation',
      contextMenuOrder: 1.5,
      precondition: '!editorHasSelection',
      run: () => {
        const model = editorInstance.getModel();
        if (!model) return;
        addContextToChat(model.getValue(), 'full');
      },
    });

    const addSelectionAction = editorInstance.addAction({
      id: 'add-selection-to-chat',
      label: 'Add selection to chat',
      contextMenuGroupId: 'navigation',
      contextMenuOrder: 1.6,
      precondition: 'editorHasSelection',
      run: () => {
        const model = editorInstance.getModel();
        const selection = editorInstance.getSelection();
        if (!model || !selection || selection.isEmpty()) return;

        const startLine = selection.startLineNumber;
        const endLine = selection.endLineNumber;
        addContextToChat(
          getFullLineRangeText(model, startLine, endLine),
          'selection',
          startLine,
          endLine
        );
      },
    });

    actionDisposablesRef.current.forEach((disposable) => disposable.dispose());
    actionDisposablesRef.current = [addFileAction, addSelectionAction];
  }, [setSelectedCodeSelection, addContextToChat, getFullLineRangeText]);

  const handleTreeNodeClick = useCallback((clickedNode) => {
    if (!clickedNode || clickedNode.type === 'program') {
      return;
    }

    const editorInstance = editorRef.current;
    const model = editorInstance?.getModel();
    if (!editorInstance || !model) {
      return;
    }

    if (typeof clickedNode.lineNumber === 'number' && clickedNode.lineNumber > 0) {
      editorInstance.revealLineInCenter(clickedNode.lineNumber);
      editorInstance.setPosition({
        lineNumber: clickedNode.lineNumber,
        column: 1,
      });
      editorInstance.focus();
    }
  }, []);

  useEffect(() => {
    return () => {
      editorRef.current = null;
      if (selectionDisposableRef.current) {
        selectionDisposableRef.current.dispose();
      }
      actionDisposablesRef.current.forEach((disposable) => disposable.dispose());
      actionDisposablesRef.current = [];
    };
  }, []);

  // Load program when programId changes
  useEffect(() => {
    if (programId) {
      loadProgram();
    }
  }, [programId, loadProgram]);

  const handleExport = async () => {
    if (!programId || !programData) {
      alert('No program loaded');
      return;
    }

    setExporting(true);
    try {
      // Fetch the original .urpx file
      const response = await axios.get(
        `${API_BASE}/api/programs/${programId}/download`,
        { responseType: 'blob' }
      );

      // Create a blob and download it
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute(
        'download',
        `${programData.metadata?.name || programData?.name || programName || programId}.urpx`
      );
      document.body.appendChild(link);
      link.click();
      link.parentNode.removeChild(link);
      window.URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Export failed:', error);
      console.error('Response status:', error.response?.status);
      console.error('Response data:', error.response?.data);
      const errorMessage = error.response?.data?.detail || error.message || 'Unknown error';
      alert(`Failed to export program: ${errorMessage}`);
    } finally {
      setExporting(false);
    }
  };

  // Show empty state if no program is loaded
  if (!programId && !programData) {
    return (
      <div className="editor-empty-state">
        <div className="empty-state-content">
          <h2>No Program Loaded</h2>
          <p>Select a program to edit from the "Search" tab.</p>
          <div className="empty-state-buttons">
            <button
              className="btn"
              onClick={() => navigate('/')}
            >
              Go to Search
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="editor-loading">
        <div className="loading"></div>
        <p>Loading program...</p>
      </div>
    );
  }

  return (
    <div className="editor-page">
      {/* Resizable Panels Layout */}
      <div className="editor-layout">
        <PanelGroup
          direction="horizontal"
          autoSaveId="robot-editor-global-layout"
        >
          {/* Left Panel: Program Structure - Default 20% */}
          <Panel
            className="editor-panel left-panel"
            defaultSize={20}
            minSize={10}
            maxSize={40}
          >
            <div className="panel-header">
              <h3>Program Tree</h3>
            </div>
            <div className="panel-content">
              {displayTreeStructure ? (
                <TreeView node={displayTreeStructure} onNodeClick={handleTreeNodeClick} />
              ) : (
                <p className="tree-error-message">{treeError}</p>
              )}
            </div>
          </Panel>

          <PanelResizeHandle className="resize-handle" />

          {/* Center Panel: Code Editor - Default 55% */}
          <Panel
            className="editor-panel center-panel"
            defaultSize={55}
            minSize={30}
            maxSize={70}
          >
            {/* Tab Bar */}
            <div className="editor-tab-bar">
              <div className="editor-tab active">
                <span className="tab-icon">{getFileIcon(editorLanguage)}</span>
                <span className="tab-title">{programData?.metadata?.name || programData?.name || programName || programId}{getFileExtension(editorLanguage)}</span>
              </div>
              <div className="tab-spacer"></div>
              {/* Dropdown Menu Button */}
              <div className="editor-menu">
                <button
                  className="menu-button"
                  onClick={() => setMenuOpen(!menuOpen)}
                  title="More options"
                >
                  ⋯
                </button>
                {menuOpen && (
                  <div className="menu-dropdown">
                    <button
                      className="menu-item"
                      onClick={() => {
                        handleExport();
                        setMenuOpen(false);
                      }}
                      disabled={exporting}
                    >
                      {exporting ? 'Exporting...' : 'Export Program'}
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="editor-container">
              <Editor
                height="100%"
                defaultLanguage={editorLanguage}
                language={editorLanguage}
                value={code}
                onChange={(value) => setCode(value || '')}
                onMount={handleEditorMount}
                theme={isDark ? 'vs-dark' : 'light'}
                options={{
                  minimap: { enabled: false },
                  fontSize: 13,
                  tabSize: 2,
                  wordWrap: 'on',
                  automaticLayout: true,
                }}
              />
            </div>
          </Panel>

          <PanelResizeHandle className="resize-handle" />

          {/* Right Panel: Chat - Default 25% */}
          <Panel
            className="editor-panel right-panel"
            defaultSize={25}
            minSize={15}
            maxSize={50}
          >
            <div className="panel-header">
              <h3>Chat</h3>
              <div className="panel-header-actions editor-menu">
                <button
                  className="menu-button"
                  onClick={() => setChatMenuOpen(!chatMenuOpen)}
                  title="More options"
                  aria-label="Chat options"
                  disabled={clearingChatMemory}
                >
                  ⋯
                </button>
                {chatMenuOpen && (
                  <div className="menu-dropdown">
                    <button
                      className="menu-item"
                      onClick={handleClearChatMemory}
                      disabled={clearingChatMemory}
                    >
                      {clearingChatMemory ? 'Clearing...' : 'Clear Chat History'}
                    </button>
                  </div>
                )}
              </div>
            </div>
            <div className="panel-content">
              <RagChat programId={programId} />
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}

export default EditorPage;
