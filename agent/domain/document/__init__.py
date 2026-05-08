"""Document domain — truncation and token counting."""

from .truncator import truncate_documents, CharacterCounter, TokenCounter

__all__ = ["truncate_documents", "CharacterCounter", "TokenCounter"]
