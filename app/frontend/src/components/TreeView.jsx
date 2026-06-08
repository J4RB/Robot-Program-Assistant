import React, { useState } from 'react';
import './TreeView.css';

function TreeView({ node, onNodeClick }) {
  const [expanded, setExpanded] = useState(true);

  if (!node) {
    return null;
  }

  const children = Array.isArray(node.children)
    ? node.children.filter((child) => child !== null && child !== undefined)
    : [];
  const hasChildren = children.length > 0;

  return (
    <div className="tree-node-wrapper">
      <div className="tree-node tree-root-node">
        {hasChildren && (
          <button
            type="button"
            className="tree-expand-btn"
            onClick={(event) => {
              event.stopPropagation();
              setExpanded((prev) => !prev);
            }}
            title={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? '▼' : '▶'}
          </button>
        )}

        <span className="tree-label">
          {node.name}
        </span>
      </div>

      {hasChildren && expanded && (
        <div className="tree-children">
          {children.map((child, index) => {
            const childIsLast = index === children.length - 1;
            const childPrefix = childIsLast ? '└──' : '├──';

            return (
              <div className="tree-node tree-child-node" key={index}>
                <button
                  type="button"
                  className="tree-label tree-node-label-button"
                  onClick={() => onNodeClick?.(child)}
                  title={`Go to ${child.name}`}
                >
                  <span className="tree-prefix">{childPrefix} </span>
                  {child.name}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default TreeView;
