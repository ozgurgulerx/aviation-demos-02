"""Regression tests for SQL read-only safety checks."""

from data_sources.unified_retriever import _is_safe_read_only_sql


def test_read_only_sql_allows_semicolon_in_string_literal():
    is_safe, reason = _is_safe_read_only_sql("SELECT ';' AS delim")
    assert is_safe is True
    assert reason == "SQL_OK"


def test_read_only_sql_allows_trailing_comment_after_semicolon():
    is_safe, reason = _is_safe_read_only_sql("SELECT 1; -- single statement")
    assert is_safe is True
    assert reason == "SQL_OK"


def test_read_only_sql_blocks_real_multi_statement():
    is_safe, reason = _is_safe_read_only_sql("SELECT 1; DROP TABLE flights")
    assert is_safe is False
    assert reason == "SQL_MULTI_STATEMENT"
