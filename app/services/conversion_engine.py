import re
import json
from typing import Dict, Any, List, Optional
from markitdown import MarkItDown
from app.schemas.document import StructuredDocument, DocumentElement, ElementType


class ConversionEngine:
    """Engine for converting documents to multiple formats."""
    
    def __init__(self):
        self.md_converter = MarkItDown()
    
    def convert_to_markdown(self, file_path: str) -> str:
        """Convert document to Markdown format."""
        result = self.md_converter.convert(file_path)
        return result.text_content
    
    def convert_to_clean_text(self, file_path: str) -> str:
        """Convert document to clean text format (no Markdown/HTML formatting)."""
        # First convert to markdown
        markdown_content = self.convert_to_markdown(file_path)
        
        # Strip all Markdown formatting
        clean_text = self._strip_markdown_formatting(markdown_content)
        
        return clean_text
    
    def convert_to_structured_json(self, file_path: str) -> StructuredDocument:
        """Convert document to structured JSON format."""
        # First convert to markdown
        markdown_content = self.convert_to_markdown(file_path)
        
        # Parse markdown into structured elements
        elements = self._parse_markdown_to_elements(markdown_content)
        
        # Create structured document
        structured_doc = StructuredDocument(
            elements=elements,
            metadata={
                "source_file": file_path,
                "total_elements": len(elements)
            }
        )
        
        return structured_doc
    
    def _strip_markdown_formatting(self, markdown_content: str) -> str:
        """Remove all Markdown formatting from text."""
        # Remove headers (# ## ### etc.)
        text = re.sub(r'^#{1,6}\s+', '', markdown_content, flags=re.MULTILINE)
        
        # Remove bold/italic formatting
        text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*(.*?)\*', r'\1', text)      # Italic
        text = re.sub(r'__(.*?)__', r'\1', text)      # Bold (alt)
        text = re.sub(r'_(.*?)_', r'\1', text)        # Italic (alt)
        
        # Remove code formatting
        text = re.sub(r'`(.*?)`', r'\1', text)        # Inline code
        text = re.sub(r'```.*?\n(.*?)```', r'\1', text, flags=re.DOTALL)  # Code blocks
        
        # Remove links but keep text
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        
        # Remove images (keep alt text if available)
        text = re.sub(r'!\[([^\]]*)\]\([^)]+\)', r'\1', text)
        
        # Remove blockquotes
        text = re.sub(r'^>\s+', '', text, flags=re.MULTILINE)
        
        # Remove horizontal rules
        text = re.sub(r'^[-*_]{3,}$', '', text, flags=re.MULTILINE)
        
        # Remove list markers
        text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)  # Unordered lists
        text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)   # Ordered lists
        
        # Clean up extra whitespace
        text = re.sub(r'\n\s*\n\s*\n', '\n\n', text)  # Multiple blank lines to double
        text = text.strip()
        
        # Remove any remaining "!" characters that might be from image syntax
        text = re.sub(r'!', '', text)
        
        return text
    
    def _parse_markdown_to_elements(self, markdown_content: str) -> List[DocumentElement]:
        """Parse Markdown content into structured elements."""
        elements = []
        lines = markdown_content.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            
            if not line:
                i += 1
                continue
            
            # Parse headings
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if heading_match:
                level = len(heading_match.group(1))
                content = heading_match.group(2).strip()
                elements.append(DocumentElement(
                    type=ElementType.HEADING,
                    content=content,
                    level=level
                ))
                i += 1
                continue
            
            # Parse paragraphs
            if not line.startswith(('#', '-', '*', '+', '>', '`', '|', '!')):
                # Check if this line contains only a link or image (standalone)
                if re.match(r'^[!]?\[([^\]]+)\]\(([^)]+)\)$', line.strip()):
                    # This is a standalone link or image, handle it separately
                    if line.startswith('!'):
                        # Image
                        image_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line.strip())
                        if image_match:
                            alt_text = image_match.group(1)
                            url = image_match.group(2)
                            elements.append(DocumentElement(
                                type=ElementType.IMAGE,
                                content=alt_text or 'Image',
                                attributes={'url': url}
                            ))
                    else:
                        # Link
                        link_match = re.match(r'\[([^\]]+)\]\(([^)]+)\)', line.strip())
                        if link_match:
                            text = link_match.group(1)
                            url = link_match.group(2)
                            elements.append(DocumentElement(
                                type=ElementType.LINK,
                                content=text,
                                attributes={'url': url}
                            ))
                    i += 1
                    continue
                
                # Collect consecutive lines that form a paragraph
                paragraph_lines = [line]
                j = i + 1
                while j < len(lines) and lines[j].strip() and not lines[j].strip().startswith(('#', '-', '*', '+', '>', '`', '|', '!')):
                    paragraph_lines.append(lines[j].strip())
                    j += 1
                
                paragraph_content = ' '.join(paragraph_lines)
                elements.append(DocumentElement(
                    type=ElementType.PARAGRAPH,
                    content=paragraph_content
                ))
                i = j
                continue
            
            # Parse list items
            list_match = re.match(r'^[\s]*([-*+]|\d+\.)\s+(.+)$', line)
            if list_match:
                content = list_match.group(2).strip()
                elements.append(DocumentElement(
                    type=ElementType.LIST_ITEM,
                    content=content
                ))
                i += 1
                continue
            
            # Parse ordered list items (numbered lists)
            ordered_list_match = re.match(r'^[\s]*(\d+)\.\s+(.+)$', line)
            if ordered_list_match:
                content = ordered_list_match.group(2).strip()
                elements.append(DocumentElement(
                    type=ElementType.LIST_ITEM,
                    content=content
                ))
                i += 1
                continue
            
            # Parse blockquotes
            if line.startswith('>'):
                content = line[1:].strip()
                elements.append(DocumentElement(
                    type=ElementType.BLOCKQUOTE,
                    content=content
                ))
                i += 1
                continue
            
            # Parse code blocks
            if line.startswith('```'):
                # Find the end of the code block
                j = i + 1
                while j < len(lines) and not lines[j].strip().startswith('```'):
                    j += 1
                
                code_content = '\n'.join(lines[i+1:j])
                elements.append(DocumentElement(
                    type=ElementType.CODE_BLOCK,
                    content=code_content
                ))
                i = j + 1
                continue
            
            # Parse horizontal rules
            if re.match(r'^[-*_]{3,}$', line):
                elements.append(DocumentElement(
                    type=ElementType.HORIZONTAL_RULE,
                    content=''
                ))
                i += 1
                continue
            
            # Parse tables (simplified - just detect table structure)
            if '|' in line and i + 1 < len(lines) and '|' in lines[i + 1]:
                # This is a table row
                cells = [cell.strip() for cell in line.split('|')[1:-1]]  # Remove empty first/last
                for cell in cells:
                    elements.append(DocumentElement(
                        type=ElementType.TABLE_CELL,
                        content=cell
                    ))
                i += 1
                continue
            
            # Parse images (check before links to avoid conflicts)
            image_match = re.search(r'!\[([^\]]*)\]\(([^)]+)\)', line)
            if image_match:
                alt_text = image_match.group(1)
                url = image_match.group(2)
                elements.append(DocumentElement(
                    type=ElementType.IMAGE,
                    content=alt_text or 'Image',
                    attributes={'url': url}
                ))
                i += 1
                continue
            
            # Parse links (check before default paragraph handling)
            link_match = re.search(r'\[([^\]]+)\]\(([^)]+)\)', line)
            if link_match:
                text = link_match.group(1)
                url = link_match.group(2)
                elements.append(DocumentElement(
                    type=ElementType.LINK,
                    content=text,
                    attributes={'url': url}
                ))
                i += 1
                continue
            
            # Default: treat as paragraph
            elements.append(DocumentElement(
                type=ElementType.PARAGRAPH,
                content=line
            ))
            i += 1
        
        return elements
    
    def convert_document(self, file_path: str, output_format: str = 'markdown') -> Any:
        """Convert document to specified format.
        
        Args:
            file_path: Path to the input document
            output_format: One of 'markdown', 'clean_text', or 'structured_json'
        
        Returns:
            Converted content in the specified format
        """
        if output_format == 'markdown':
            return self.convert_to_markdown(file_path)
        elif output_format == 'clean_text':
            return self.convert_to_clean_text(file_path)
        elif output_format == 'structured_json':
            return self.convert_to_structured_json(file_path)
        else:
            raise ValueError(f"Unsupported output format: {output_format}") 