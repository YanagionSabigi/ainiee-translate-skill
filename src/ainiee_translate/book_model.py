"""Types for the ephemeral renderer, not a second source-book contract."""
from typing import Any, TypeAlias
BookDocument: TypeAlias = dict[str, Any]


def validate_book(book, *, require_translation=False):
    if book.get('schema') != 'ainiee-render/1':
        raise ValueError('Publication requires epub-book/2 binding through rendering_view')
    if require_translation and not book.get('translation_complete'):
        raise ValueError('Incomplete translation')
