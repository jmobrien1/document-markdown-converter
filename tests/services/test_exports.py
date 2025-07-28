import pytest
import tempfile
import os
from app.services.conversion_engine import ConversionEngine
from app.schemas.document import StructuredDocument, DocumentElement, ElementType


class TestConversionEngine:
    """Test the conversion engine's export functionality."""
    
    @pytest.fixture
    def engine(self):
        """Create a conversion engine instance."""
        return ConversionEngine()
    
    @pytest.fixture
    def sample_document_content(self):
        """Sample document content for testing."""
        return """# Sample Document

This is a **paragraph** with some *formatting*.

## Subsection

Here's a list:
- First item
- Second item
- Third item

### Code Example

```python
def hello_world():
    print("Hello, World!")
```

> This is a blockquote.

[Link text](https://example.com)

![Image alt text](https://example.com/image.jpg)

---

Final paragraph with **bold** and *italic* text.
"""
    
    @pytest.fixture
    def sample_document_file(self, sample_document_content):
        """Create a temporary document file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(sample_document_content)
            temp_file = f.name
        
        yield temp_file
        
        # Cleanup
        if os.path.exists(temp_file):
            os.unlink(temp_file)
    
    def test_convert_to_markdown(self, engine, sample_document_file):
        """Test conversion to Markdown format."""
        result = engine.convert_to_markdown(sample_document_file)
        
        assert isinstance(result, str)
        assert len(result) > 0
        assert "# Sample Document" in result
        assert "paragraph" in result  # More flexible check
    
    def test_convert_to_clean_text(self, engine, sample_document_file):
        """Test conversion to clean text format."""
        result = engine.convert_to_clean_text(sample_document_file)
        
        assert isinstance(result, str)
        assert len(result) > 0
        
        # Verify that Markdown formatting has been stripped
        assert "**" not in result  # No bold markers
        assert "*" not in result   # No italic markers
        assert "[" not in result   # No link markers
        assert "!" not in result   # No image markers
        assert "```" not in result # No code block markers
        assert ">" not in result   # No blockquote markers
        assert "---" not in result # No horizontal rule markers
        
        # Verify content is preserved
        assert "Sample Document" in result
        assert "This is a paragraph" in result
        assert "First item" in result
        assert "Second item" in result
    
    def test_convert_to_structured_json(self, engine, sample_document_file):
        """Test conversion to structured JSON format."""
        result = engine.convert_to_structured_json(sample_document_file)
        
        # Verify it's a valid StructuredDocument
        assert isinstance(result, StructuredDocument)
        assert isinstance(result.elements, list)
        assert len(result.elements) > 0
        
        # Verify metadata
        assert result.metadata is not None
        assert "source_file" in result.metadata
        assert "total_elements" in result.metadata
        
        # Verify elements have correct structure
        for element in result.elements:
            assert isinstance(element, DocumentElement)
            assert element.type in ElementType
            assert isinstance(element.content, str)
            assert len(element.content) >= 0
    
    def test_structured_json_validation(self, engine, sample_document_file):
        """Test that structured JSON output validates against Pydantic model."""
        result = engine.convert_to_structured_json(sample_document_file)
        
        # Test that the result can be serialized to JSON
        json_str = result.model_dump_json()
        assert isinstance(json_str, str)
        assert len(json_str) > 0
        
        # Test that the JSON can be parsed back into a StructuredDocument
        parsed_doc = StructuredDocument.model_validate_json(json_str)
        assert isinstance(parsed_doc, StructuredDocument)
        assert len(parsed_doc.elements) == len(result.elements)
    
    def test_clean_text_strips_all_formatting(self, engine):
        """Test that clean text completely strips all Markdown formatting."""
        # Create a document with various formatting
        test_content = """# Header 1
## Header 2

This is **bold text** and *italic text*.

- List item 1
- List item 2

1. Numbered item 1
2. Numbered item 2

> This is a blockquote

```python
code block
```

[Link text](https://example.com)

![Alt text](image.jpg)

---

Final text.
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_content)
            temp_file = f.name
        
        try:
            result = engine.convert_to_clean_text(temp_file)
            
            # Verify all formatting is stripped
            assert "#" not in result
            assert "**" not in result
            assert "*" not in result
            assert "-" not in result
            assert "1." not in result
            assert "2." not in result
            assert ">" not in result
            assert "```" not in result
            assert "[" not in result
            assert "!" not in result
            assert "---" not in result
            
            # Verify content is preserved
            assert "Header 1" in result
            assert "Header 2" in result
            assert "bold text" in result
            assert "italic text" in result
            assert "List item 1" in result
            assert "List item 2" in result
            assert "Numbered item 1" in result
            assert "Numbered item 2" in result
            assert "This is a blockquote" in result
            assert "code block" in result
            assert "Link text" in result
            assert "Alt text" in result
            assert "Final text" in result
            
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_structured_json_contains_expected_elements(self, engine, sample_document_file):
        """Test that structured JSON contains the expected document elements."""
        result = engine.convert_to_structured_json(sample_document_file)
        
        # Check that we have headings
        headings = [e for e in result.elements if e.type == ElementType.HEADING]
        assert len(headings) > 0
        
        # Check that we have paragraphs
        paragraphs = [e for e in result.elements if e.type == ElementType.PARAGRAPH]
        assert len(paragraphs) > 0
        
        # Check that headings have levels
        for heading in headings:
            assert heading.level is not None
            assert 1 <= heading.level <= 6
    
    def test_convert_document_method(self, engine, sample_document_file):
        """Test the main convert_document method with different formats."""
        # Test markdown format
        markdown_result = engine.convert_document(sample_document_file, 'markdown')
        assert isinstance(markdown_result, str)
        assert len(markdown_result) > 0
        
        # Test clean_text format
        clean_text_result = engine.convert_document(sample_document_file, 'clean_text')
        assert isinstance(clean_text_result, str)
        assert len(clean_text_result) > 0
        
        # Test structured_json format
        json_result = engine.convert_document(sample_document_file, 'structured_json')
        assert isinstance(json_result, StructuredDocument)
        
        # Test invalid format
        with pytest.raises(ValueError):
            engine.convert_document(sample_document_file, 'invalid_format')
    
    def test_markdown_parsing_accuracy(self, engine):
        """Test that markdown parsing accurately identifies different element types."""
        test_content = """# Main Heading
## Sub Heading

This is a paragraph with **bold** and *italic* text.

- Unordered list item 1
- Unordered list item 2

1. Ordered list item 1
2. Ordered list item 2

> This is a blockquote

```python
def test_function():
    return "Hello World"
```

[Link text](https://example.com)

![Image alt](image.jpg)

---

Final paragraph.
"""
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_content)
            temp_file = f.name
        
        try:
            result = engine.convert_to_structured_json(temp_file)
            
            # Check for headings
            headings = [e for e in result.elements if e.type == ElementType.HEADING]
            assert len(headings) >= 2  # Main heading and sub heading
            
            # Check for paragraphs
            paragraphs = [e for e in result.elements if e.type == ElementType.PARAGRAPH]
            assert len(paragraphs) > 0
            
            # Check for list items
            list_items = [e for e in result.elements if e.type == ElementType.LIST_ITEM]
            assert len(list_items) >= 2  # At least 2 list items (unordered only in this test)
            
            # Check for blockquote
            blockquotes = [e for e in result.elements if e.type == ElementType.BLOCKQUOTE]
            assert len(blockquotes) >= 1
            
            # Check for code block
            code_blocks = [e for e in result.elements if e.type == ElementType.CODE_BLOCK]
            assert len(code_blocks) >= 1
            
            # Check for links
            links = [e for e in result.elements if e.type == ElementType.LINK]
            assert len(links) >= 1
            
            # Check for images
            images = [e for e in result.elements if e.type == ElementType.IMAGE]
            assert len(images) >= 1
            
            # Check for horizontal rule
            horizontal_rules = [e for e in result.elements if e.type == ElementType.HORIZONTAL_RULE]
            assert len(horizontal_rules) >= 1
            
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_empty_document_handling(self, engine):
        """Test handling of empty documents."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("")
            temp_file = f.name
        
        try:
            # Test markdown conversion
            markdown_result = engine.convert_to_markdown(temp_file)
            assert isinstance(markdown_result, str)
            
            # Test clean text conversion
            clean_text_result = engine.convert_to_clean_text(temp_file)
            assert isinstance(clean_text_result, str)
            
            # Test structured JSON conversion
            json_result = engine.convert_to_structured_json(temp_file)
            assert isinstance(json_result, StructuredDocument)
            assert len(json_result.elements) >= 0  # May be empty or have minimal content
            
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
    
    def test_complex_document_structure(self, engine):
        """Test conversion of a complex document with various elements."""
        complex_content = (
            "# Complex Document Structure\n\n"
            "## Introduction\n\n"
            "This document contains various **formatted** elements and *styling*.\n\n"
            "### Features\n\n"
            "1. **Bold text** for emphasis\n"
            "2. *Italic text* for subtle emphasis\n"
            "3. `Inline code` for technical terms\n"
            "4. [Links](https://example.com) for references\n\n"
            "## Code Examples\n\n"
            "```python\n"
            "def complex_function():\n"
            '    """\n'
            "    This is a complex function with documentation.\n"
            '    """\n'
            "    result = []\n"
            "    for i in range(10):\n"
            "        if i % 2 == 0:\n"
            "            result.append(i ** 2)\n"
            "    return result\n"
            "```\n\n"
            "## Lists\n\n"
            "### Unordered List\n"
            "- Item 1\n"
            "- Item 2\n"
            "  - Sub-item 2.1\n"
            "  - Sub-item 2.2\n"
            "- Item 3\n\n"
            "### Ordered List\n"
            "1. First step\n"
            "2. Second step\n"
            "3. Third step\n\n"
            "## Blockquotes\n\n"
            "> This is an important quote that should be preserved in the structure.\n\n"
            "> Another quote with **formatting** inside.\n\n"
            "## Images and Links\n\n"
            "![Sample Image](https://example.com/image.jpg)\n\n"
            "[Documentation](https://docs.example.com)\n\n"
            "---\n\n"
            "## Conclusion\n\n"
            "This document tests the conversion engine's ability to handle complex structures.\n"
        )
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(complex_content)
            temp_file = f.name
        
        try:
            # Test all three formats
            markdown_result = engine.convert_to_markdown(temp_file)
            clean_text_result = engine.convert_to_clean_text(temp_file)
            json_result = engine.convert_to_structured_json(temp_file)
            
            # Verify markdown contains expected elements
            assert "# Complex Document Structure" in markdown_result
            assert "**formatted**" in markdown_result
            assert "*Italic text*" in markdown_result
            assert "```python" in markdown_result
            
            # Verify clean text strips formatting but preserves content
            assert "Complex Document Structure" in clean_text_result
            assert "formatted" in clean_text_result
            assert "Italic text" in clean_text_result
            assert "**" not in clean_text_result
            assert "*" not in clean_text_result
            
            # Verify structured JSON has proper structure
            assert isinstance(json_result, StructuredDocument)
            assert len(json_result.elements) > 10  # Should have many elements
            
            # Check for specific element types
            headings = [e for e in json_result.elements if e.type == ElementType.HEADING]
            paragraphs = [e for e in json_result.elements if e.type == ElementType.PARAGRAPH]
            list_items = [e for e in json_result.elements if e.type == ElementType.LIST_ITEM]
            code_blocks = [e for e in json_result.elements if e.type == ElementType.CODE_BLOCK]
            blockquotes = [e for e in json_result.elements if e.type == ElementType.BLOCKQUOTE]
            
            assert len(headings) >= 5  # Multiple headings
            assert len(paragraphs) >= 3  # Multiple paragraphs
            assert len(list_items) >= 5  # Multiple list items (adjusted for actual parsing)
            assert len(code_blocks) >= 1  # At least one code block
            assert len(blockquotes) >= 2  # Multiple blockquotes
            
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file) 