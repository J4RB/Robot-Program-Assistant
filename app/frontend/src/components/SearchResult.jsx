import './SearchResult.css';

function formatArrayValue(value) {
  return Array.isArray(value) && value.length > 0 ? value.join(', ') : 'N/A';
}

function SearchResult({ result, rank, isBestMatch, onEdit }) {
  const details = result.details || {};
  const robotValue = details.robotType || 'N/A';
  const applicationValue = details.applicationType || 'N/A';
  const gripperValue = formatArrayValue(details.grippers);
  const objectTypeValue = formatArrayValue(details.objectTypes);
  const componentsValue = details.components || 'N/A';
  const actionsValue = typeof details.actionsCount === 'number' ? details.actionsCount : 'N/A';
  const descriptionText = result.rawText || result.text_preview || 'No raw text available';

  const summaryItems = [
    { label: 'Robot', value: robotValue },
    { label: 'Application', value: applicationValue },
    { label: 'Gripper', value: gripperValue },
    { label: 'Object Type', value: objectTypeValue },
    { label: 'Components', value: componentsValue },
    { label: 'Actions', value: actionsValue },
  ];

  return (
    <div className="search-result-card card">
      <div className="result-header">
        <div className="result-heading-block">
          <div className="result-title-row">
            <span className="result-rank">#{rank}</span>
            <h3 className="result-title">{result.source}</h3>
            {isBestMatch && <span className="best-match-badge">Best Match</span>}
          </div>
        </div>
        <div className="result-header-actions">
          <div className="info-popover">
            <button type="button" className="info-button" aria-label="Show program description">
              <svg viewBox="0 0 24 24" focusable="false">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2Zm0 4a1.25 1.25 0 1 1 0 2.5A1.25 1.25 0 0 1 12 6Zm2 12h-4v-1.5h1V11h-1V9.5h3V16.5h1V18Z" />
              </svg>
            </button>
            <div className="info-tooltip" role="tooltip">
              {descriptionText}
            </div>
          </div>
        </div>
      </div>

      <div className="result-summary-row">
        <div className="result-summary" aria-label="Program summary">
          {summaryItems.map((item) => (
            <span className="summary-chip" key={item.label}>
              <span className="summary-chip-label">{item.label}:</span>
              <span className="summary-chip-value">{item.value}</span>
            </span>
          ))}
        </div>
        <button
          className="btn-primary result-edit-btn"
          onClick={() => onEdit(result)}
        >
          Select Program
        </button>
      </div>
    </div>
  );
}

export default SearchResult;
