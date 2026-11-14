"""LLM-ul doar explică decizii deja luate (rolul 3)."""

from app.llm.client import explain, warm_up

__all__ = ["explain", "warm_up"]
