from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from enum import Enum


class ElementType(str, Enum):
    """Valid document element types."""
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    CODE_BLOCK = "code_block"
    BLOCKQUOTE = "blockquote"
    HORIZONTAL_RULE = "horizontal_rule"
    IMAGE = "image"
    LINK = "link"


class DocumentElement(BaseModel):
    """Represents a single element in a structured document."""
    type: ElementType = Field(..., description="The type of document element")
    content: str = Field(..., description="The text content of the element")
    level: Optional[int] = Field(None, ge=1, le=6, description="Heading level (1-6) for headings")
    attributes: Optional[dict] = Field(None, description="Additional attributes (e.g., URL for links, alt text for images)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "type": "heading",
                "content": "Introduction",
                "level": 1
            }
        }


class StructuredDocument(BaseModel):
    """Represents a complete structured document."""
    elements: List[DocumentElement] = Field(..., description="List of document elements in order")
    metadata: Optional[dict] = Field(None, description="Document metadata (title, author, etc.)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "elements": [
                    {"type": "heading", "content": "Document Title", "level": 1},
                    {"type": "paragraph", "content": "This is a paragraph of text."},
                    {"type": "list_item", "content": "First list item"},
                    {"type": "list_item", "content": "Second list item"}
                ],
                "metadata": {
                    "title": "Sample Document",
                    "author": "John Doe"
                }
            }
        } 