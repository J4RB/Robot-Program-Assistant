"""Load and process documentation PDFs."""
from pathlib import Path
from typing import List
from dataclasses import dataclass
import re
import fitz  # PyMuPDF
from app.utils.config_loader import get_config


@dataclass
class DocumentChunk:
    """Represents a chunk of documentation."""
    doc_name: str
    page_number: int
    chunk_index: int
    chunk_text: str
    source_file_path: str


class DocumentLoader:
    """Load and process PDF documentation files."""
    
    def __init__(self):
        config = get_config()
        doc_processing_config = config.get_processing_config('documentation')
        
        # Read from config (chunk_size and overlap are in tokens)
        self.chunk_size = doc_processing_config['chunk_size']
        self.chunk_overlap = doc_processing_config['overlap']
        self.min_chunk_tokens = doc_processing_config.get(
            'min_chunk_tokens',
            max(80, int(self.chunk_size * 0.45)),
        )
        
        # Resolve docs directory relative to workspace root
        workspace_root = config.get_workspace_root()
        self.docs_dir = workspace_root / doc_processing_config['dir']

    def _clean_extracted_text(self, text: str) -> str:
        """Normalize common PDF extraction artifacts before section detection."""
        if not text:
            return ""

        cleaned = text
        # Fix common line-break hyphenation artifacts: "universal- robots" -> "universal-robots"
        cleaned = re.sub(r'([A-Za-z0-9])-\s+([A-Za-z0-9])', r'\1-\2', cleaned)
        # Collapse excessive whitespace while preserving line boundaries for heading detection.
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    def _merge_small_adjacent_chunks(self, chunks: List[DocumentChunk]) -> List[DocumentChunk]:
        """Merge very small chunks with neighbors across section boundaries."""
        if not chunks:
            return []

        chars_per_token = 4
        min_chunk_chars = self.min_chunk_tokens * chars_per_token
        max_merge_target_chars = int(self.chunk_size * chars_per_token * 1.4)

        merged: List[DocumentChunk] = []
        i = 0

        while i < len(chunks):
            current = chunks[i]
            current_len = len(current.chunk_text.strip())

            if current_len < min_chunk_chars:
                if merged:
                    prev = merged[-1]
                    combined = f"{prev.chunk_text} {current.chunk_text}".strip()
                    if len(combined) <= max_merge_target_chars:
                        prev.chunk_text = combined
                    elif i + 1 < len(chunks):
                        nxt = chunks[i + 1]
                        nxt.chunk_text = f"{current.chunk_text} {nxt.chunk_text}".strip()
                    else:
                        prev.chunk_text = combined
                elif i + 1 < len(chunks):
                    nxt = chunks[i + 1]
                    nxt.chunk_text = f"{current.chunk_text} {nxt.chunk_text}".strip()
                else:
                    merged.append(current)
            else:
                merged.append(current)

            i += 1

        # Rebuild contiguous chunk indexes after merges.
        for idx, chunk in enumerate(merged):
            chunk.chunk_index = idx

        return merged
    
    def load_pdfs(self) -> List[DocumentChunk]:
        """Load and chunk all PDF files."""
        all_chunks = []
        docs_dir = self.docs_dir
        
        if not docs_dir.exists():
            print(f"[ERROR] Documentation directory not found: {docs_dir}")
            return all_chunks
        
        pdf_files = sorted(docs_dir.rglob("*.pdf"))
        print(f"[INFO] Found {len(pdf_files)} PDF files")
        
        for pdf_path in pdf_files:
            try:
                chunks = self._load_pdf(pdf_path)
                all_chunks.extend(chunks)
            except Exception as e:
                print(f"    [ERROR] Error loading {pdf_path.name}: {str(e)}")
                continue
        
        print(f"[SUCCESS] Total chunks extracted: {len(all_chunks)}")
        return all_chunks
    
    def _load_pdf(self, pdf_path: Path) -> List[DocumentChunk]:
        """Load and chunk a single PDF file."""
        chunks = []
        doc_name = pdf_path.stem
        chunk_index = 0
        
        try:
            pdf = fitz.open(pdf_path)
            
            full_text = ""
            page_markers = [] 
            
            for page_idx, page in enumerate(pdf):
                page_markers.append((len(full_text), page_idx + 1))
                page_text = page.get_text()
                
                # Preserve line breaks for heading detection, but clean excessive whitespace
                lines = [line.strip() for line in page_text.split('\n')]
                lines = [line for line in lines if line.strip()]
                page_text = '\n'.join(lines)
                page_text = self._clean_extracted_text(page_text)
                
                if full_text:
                    full_text += "\n"
                full_text += page_text
            
            # Detect sections in complete text (with stable offsets)
            sections = self._detect_sections(full_text)
            
            # Filter out table of contents sections
            sections = [s for s in sections if not self._is_toc_section(s["text"])]
            
            # Chunk each section, tracking which page it came from
            for section in sections:
                section_text = section["text"]
                section_start = section["start_offset"]
                starting_page = self._get_page_number(section_start, page_markers)
                
                # Apply size-based chunking within section
                section_chunks = self._chunk_section(
                    section_text,
                    doc_name,
                    starting_page,
                    chunk_index,
                    pdf_path.name
                )
                chunks.extend(section_chunks)
                chunk_index += len(section_chunks)

            chunks = self._merge_small_adjacent_chunks(chunks)
            
            pdf.close()
        
        except Exception as e:
            print(f"Error processing PDF {pdf_path.name}: {str(e)}")
            raise
        
        return chunks
    
    def _get_page_number(self, char_offset: int, page_markers: List[tuple]) -> int:
        """Determine which page contains a character offset."""
        for i, (offset, page_num) in enumerate(page_markers):
            if i + 1 < len(page_markers):
                next_offset = page_markers[i + 1][0]
                if offset <= char_offset < next_offset:
                    return page_num
            else:
                # Last page
                if char_offset >= offset:
                    return page_num
        return 1  # Default to page 1 if not found
    
    def _detect_sections(self, full_text: str) -> List[dict]:
        """Detect sections/headings in full document text."""
        lines_with_offsets = []
        offset = 0
        for raw_line in full_text.split('\n'):
            stripped = raw_line.strip()
            if stripped:
                # Keep the offset from the original document text.
                lines_with_offsets.append((stripped, offset))
            offset += len(raw_line) + 1

        if not lines_with_offsets:
            return [{"text": full_text, "start_offset": 0}]

        sections = []
        current_section_lines = []
        current_section_start = lines_with_offsets[0][1]

        for line, line_offset in lines_with_offsets:
            is_heading = self._is_heading(line)

            if is_heading and current_section_lines:
                sections.append(
                    {
                        "text": ' '.join(current_section_lines),
                        "start_offset": current_section_start,
                    }
                )
                current_section_lines = [line]
                current_section_start = line_offset
            else:
                current_section_lines.append(line)

        if current_section_lines:
            sections.append(
                {
                    "text": ' '.join(current_section_lines),
                    "start_offset": current_section_start,
                }
            )

        return sections
    
    def _is_heading(self, line: str) -> bool:
        """Determine if a line is a heading/section title."""
        if not line:
            return False

        candidate = line.strip()
        if not candidate:
            return False

        # URLs and path-like lines are content, not headings.
        if 'http://' in candidate.lower() or 'https://' in candidate.lower() or '/' in candidate:
            return False

        # Very long lines are usually body text.
        if len(candidate) > 120:
            return False
        
        # All uppercase (and more than 3 chars) - likely a heading
        if candidate.isupper() and 4 <= len(candidate) <= 80 and len(candidate.split()) <= 10:
            return True
        
        # Ends with colon - likely a label/section header
        if candidate.endswith(':') and len(candidate.split()) <= 10:
            return True
        
        # Starts with number and dot - likely numbered section
        if candidate[0].isdigit() and '.' in candidate[:3] and len(candidate) < 100:
            return True
        
        # Short lines with capitals - likely headings
        if len(candidate) < 80 and len(candidate.split()) <= 8 and sum(1 for c in candidate if c.isupper()) > len(candidate) * 0.3:
            return True
        
        return False
    
    def _is_toc_section(self, section_text: str) -> bool:
        """Determine if a section is table of contents."""
        if not section_text:
            return False
        
        toc_pattern_count = 0
        total_lines = 0
        
        for part in section_text.split('\n')[:30]:
            part = part.strip()
            if not part:
                continue
            
            total_lines += 1
            
            if part and part[0].isdigit():
                # Check if line has mostly numbers, dots, and short words
                if len(part) < 100:
                    numeric_chars = sum(1 for c in part if c.isdigit() or c == '.')
                    if numeric_chars > len(part) * 0.15:
                        toc_pattern_count += 1
        
        if total_lines > 0 and toc_pattern_count / total_lines > 0.5:
            return True
        
        if total_lines == 1 and section_text.strip()[0].isdigit() and len(section_text) < 100:
            return True
        
        return False
    
    def _chunk_section(
        self,
        section_text: str,
        doc_name: str,
        page_number: int,
        base_chunk_index: int,
        source_file_path: str
    ) -> List[DocumentChunk]:
        """Apply sentence-aware chunking to a section."""
        chunks = []
        chunk_index = base_chunk_index

        normalized_text = ' '.join(section_text.strip().split())
        if not normalized_text:
            return chunks

        chars_per_token = 4
        chunk_size_chars = self.chunk_size * chars_per_token
        overlap_chars = self.chunk_overlap * chars_per_token
        min_chunk_chars = self.min_chunk_tokens * chars_per_token

        # Sentence-first splitting reduces abrupt cutoffs in chunk text.
        sentence_parts = [
            part.strip() for part in re.split(r'(?<=[.!?])\s+|\n+', normalized_text) if part.strip()
        ]
        if not sentence_parts:
            sentence_parts = [normalized_text]

        # Split very long sentences into smaller word-boundary fragments.
        sentences = []
        for sentence in sentence_parts:
            if len(sentence) <= int(chunk_size_chars * 1.25):
                sentences.append(sentence)
                continue

            words = sentence.split()
            current_words = []
            current_len = 0
            for word in words:
                projected_len = current_len + (1 if current_words else 0) + len(word)
                if projected_len > chunk_size_chars and current_words:
                    sentences.append(' '.join(current_words))
                    current_words = [word]
                    current_len = len(word)
                else:
                    current_words.append(word)
                    current_len = projected_len
            if current_words:
                sentences.append(' '.join(current_words))

        chunk_texts = []
        i = 0
        while i < len(sentences):
            start_i = i
            current_sentences = []
            current_len = 0

            while i < len(sentences):
                sentence = sentences[i]
                projected_len = current_len + (1 if current_sentences else 0) + len(sentence)
                if projected_len > chunk_size_chars and current_sentences:
                    break
                current_sentences.append(sentence)
                current_len = projected_len
                i += 1

            if not current_sentences:
                current_sentences = [sentences[i]]
                i += 1

            chunk_text = ' '.join(current_sentences).strip()
            if chunk_text:
                chunk_texts.append(chunk_text)

            if i >= len(sentences):
                break

            overlap_len = 0
            overlap_count = 0
            for sentence in reversed(current_sentences):
                overlap_len += len(sentence) + 1
                overlap_count += 1
                if overlap_len >= overlap_chars:
                    break

            i = max(start_i + 1, i - overlap_count)

        # Merge tiny chunks into the previous chunk to avoid low-value fragments.
        merged_texts = []
        for text in chunk_texts:
            if merged_texts and len(text) < min_chunk_chars:
                merged_texts[-1] = f"{merged_texts[-1]} {text}".strip()
            else:
                merged_texts.append(text)

        for text in merged_texts:
            if text and len(text) > 10:
                chunks.append(
                    DocumentChunk(
                        doc_name=doc_name,
                        page_number=page_number,
                        chunk_index=chunk_index,
                        chunk_text=text,
                        source_file_path=source_file_path,
                    )
                )
                chunk_index += 1

        return chunks
