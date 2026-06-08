import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import SearchResult from '../components/SearchResult';
import { useEditor } from '../contexts/EditorContext';
import './ProgramSearch.css';

function sortResultsByScore(items) {
    return [...items].sort((left, right) => (right.score ?? 0) - (left.score ?? 0));
}

function ProgramSearch() {
    const navigate = useNavigate();
    const {
        loadProgram,
        searchQuery,
        setSearchQuery,
        searchResults,
        setSearchResults,
        searchSearched,
        setSearchSearched,
    } = useEditor();
    const [query, setQuery] = useState(searchQuery);
    const [results, setResults] = useState(() => sortResultsByScore(searchResults));
    const [loading, setLoading] = useState(false);
    const [searched, setSearched] = useState(searchSearched);

    const API_BASE = 'http://localhost:8000';

    const handleSearch = async (e) => {
        e.preventDefault();
        if (!query.trim()) return;

        setLoading(true);
        setSearched(true);
        setSearchSearched(true);

        try {
            // Pure semantic search - no RAG pipeline
            const response = await axios.post(`${API_BASE}/api/search`, {
                query: query,
                limit: 10
            });

            // Map backend search response to SearchResult component shape
            const formattedResults = response.data.results.map((source, index) => {
                const metadata = source.metadata || {};
                const nestedMetadata = metadata.metadata || {};
                const pickValue = (...keys) => {
                    const containers = [metadata, nestedMetadata, source];
                    for (const key of keys) {
                        for (const container of containers) {
                            const value = container?.[key];
                            if (value !== undefined && value !== null && String(value).trim() !== '') {
                                return value;
                            }
                        }
                    }
                    return undefined;
                };

                const displayName = pickValue('program_name', 'programName', 'program_id', 'programId', 'source') || `Program ${index + 1}`;
                const gripperType = pickValue('gripper_type', 'gripperType');
                const objectType = pickValue('object_type', 'objectType');
                const components = pickValue('components');
                const actions = pickValue('actions');

                const normalizedGrippers = Array.isArray(gripperType)
                    ? gripperType
                    : (typeof gripperType === 'string' && gripperType.trim()
                        ? gripperType.split('|').map((item) => item.trim()).filter(Boolean)
                        : []);

                const normalizedObjectTypes = Array.isArray(objectType)
                    ? objectType
                    : (typeof objectType === 'string' && objectType.trim()
                        ? objectType.split('|').map((item) => item.trim()).filter(Boolean)
                        : []);

                return {
                    id: index,
                    source: displayName,
                    text_preview: source.text || '',
                    rawText: pickValue('chunk_text') || source.text || '',
                    score: source.score ?? 0,
                    program_id: pickValue('program_id', 'programId'),
                    metadata,
                    details: {
                        robotType: pickValue('robot_type', 'robotType') || 'N/A',
                        applicationType: pickValue('application_type', 'applicationType') || 'N/A',
                        grippers: normalizedGrippers,
                        objectTypes: normalizedObjectTypes,
                        components: Array.isArray(components)
                            ? components.join(', ')
                            : (components || 'N/A'),
                        actionsCount: Array.isArray(actions) ? actions.length : null,
                    },
                };
            });

            const rankedResults = sortResultsByScore(formattedResults);
            setResults(rankedResults);
            setSearchResults(rankedResults);
        } catch (error) {
            console.error('Search failed:', error);
            alert('Failed to search programs. Make sure the RAG backend is running on port 8000.');
        } finally {
            setLoading(false);
        }
    };

    const normalizeProgramId = (rawId) => {
        if (!rawId || typeof rawId !== 'string') return null;
        const trimmed = rawId.trim();

        // Convert display-style IDs like "Program8" to canonical backend ID "program8"
        const programMatch = trimmed.match(/^program\s*([0-9]+)$/i);
        if (programMatch) {
            return `program${programMatch[1]}`;
        }

        return trimmed.toLowerCase();
    };

    const handleEditProgram = (result) => {
        const candidateId = result.program_id || result.metadata?.program_id;
        const programId = normalizeProgramId(candidateId);
        if (!programId) {
            alert('Unable to determine the selected program id from search result.');
            return;
        }
        // Load the program into context
        const programName = result.source || result.metadata?.program_name || programId;
        loadProgram(programId, programName);
        // Navigate to the editor tab
        navigate('/edit');
    };

    return (
        <div className="landing-page">
            {/* Header */}
            <section className="landing-header">
                <h1>Robot Program Search</h1>
                <p>Search the library of robot programs using semantic search.</p>
            </section>

            {/* Search Section */}
            <section className="search-section">
                <form onSubmit={handleSearch} className="search-form">
                    <input
                        type="text"
                        placeholder="E.g., 'pick and place programs' or 'show assembly examples'"
                        value={query}
                        onChange={(e) => {
                            const newValue = e.target.value;
                            setQuery(newValue);
                            setSearchQuery(newValue);
                        }}
                        className="search-input"
                    />
                    <button type="submit" className="btn-primary" disabled={loading}>
                        {loading ? (
                            <>
                                <span className="loading"></span> Searching...
                            </>
                        ) : (
                            'Search'
                        )}
                    </button>
                </form>
            </section>

            {/* Results Section */}
            {searched && (
                <section className="results-section">
                    <div className="results-header">
                        <h2>
                            {loading ? 'Searching...' : `Found ${results.length} program${results.length !== 1 ? 's' : ''}`}
                        </h2>
                    </div>

                    {results.length === 0 && !loading && (
                        <div className="no-results">
                            <p>No programs found. Try a different search query.</p>
                        </div>
                    )}

                    <ol className="results-list">
                        {results.map((result, index) => (
                            <li key={`${result.program_id || result.source}-${index}`} className="results-list-item">
                                <SearchResult
                                    result={result}
                                    rank={index + 1}
                                    isBestMatch={index === 0}
                                    onEdit={(r) => handleEditProgram(r)}
                                />
                            </li>
                        ))}
                    </ol>
                </section>
            )}
        </div>
    );
}

export default ProgramSearch;
