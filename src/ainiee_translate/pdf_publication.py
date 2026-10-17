"""The template view is already compiled by pdf-to-epub."""
from .book_model import validate_book


def compile_publication(book):
    validate_book(book, require_translation=True)
    return book
