function removeUrscriptObject(value) {
    if (Array.isArray(value)) {
        return value.map(removeUrscriptObject);
    }
    if (value && typeof value === 'object') {
        const next = {};
        Object.entries(value).forEach(([key, nested]) => {
            if (key.toLowerCase() !== 'urscript') {
                next[key] = removeUrscriptObject(nested);
            }
        });
        return next;
    }
    return value;
}

function stripUrscriptFromText(rawText) {
    if (!rawText) return '';

    // Removes all occurrences of: "urscript": { "script": "..." }
    const urscriptObject = /"urscript"\s*:\s*\{\s*"script"\s*:\s*"(?:\\.|[^"\\])*"\s*\}/g;

    let text = rawText.replace(new RegExp(`,\\s*${urscriptObject.source}`, 'g'), '');
    text = text.replace(new RegExp(`${urscriptObject.source}\\s*,`, 'g'), '');
    text = text.replace(urscriptObject, '');

    return text;
}

export function sanitizeProgramContext(rawText) {
    if (!rawText || !rawText.trim()) return '';

    try {
        const parsed = JSON.parse(rawText);
        const withoutUrscript = removeUrscriptObject(parsed);
        return JSON.stringify(withoutUrscript, null, 2);
    } catch {
        return stripUrscriptFromText(rawText);
    }
}

export function buildContextLabel(fileName, startLine, endLine) {
    if (typeof startLine === 'number' && typeof endLine === 'number') {
        return `${fileName}:${startLine}-${endLine}`;
    }
    return fileName;
}

export function buildProgramContextPayload(contexts) {
    if (!Array.isArray(contexts) || contexts.length === 0) return null;
    if (contexts.length === 1) return contexts[0].text;

    return contexts
        .map((ctx, index) => `### Context ${index + 1}: ${ctx.label}\n${ctx.text}`)
        .join('\n\n');
}
