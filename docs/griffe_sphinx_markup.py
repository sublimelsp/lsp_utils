"""Griffe extension that converts the Sphinx markup used in docstrings to Markdown understood by mkdocstrings."""

from __future__ import annotations

from griffe import Extension
from typing import Any
import re

ROLE_PATTERN = re.compile(r':(?:attr|class|func|meth|obj):`~?([^`]+)`')
CODE_DIRECTIVE_PATTERN = re.compile(r'^(\s*)\.\. code(?:-block)?::\s*(\S*)\s*$')


def _role_to_crossref(match: re.Match[str]) -> str:
    text = match.group(1)
    target = text.removesuffix('()')
    return f'[`{text}`][{target}]'


def _code_directives_to_fences(docstring: str) -> str:
    lines = docstring.split('\n')
    result: list[str] = []
    i = 0
    while i < len(lines):
        match = CODE_DIRECTIVE_PATTERN.match(lines[i])
        if not match:
            result.append(lines[i])
            i += 1
            continue
        indent, language = match.groups()
        i += 1
        body: list[str] = []
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > len(indent)):
            body.append(lines[i])
            i += 1
        while body and not body[0].strip():
            body.pop(0)
        trailing_blank_lines = 0
        while body and not body[-1].strip():
            body.pop()
            trailing_blank_lines += 1
        body_indent = min((len(line) - len(line.lstrip()) for line in body if line.strip()), default=0)
        result.append(f'{indent}```{language}')
        result.extend(f'{indent}{line[body_indent:]}' if line.strip() else '' for line in body)
        result.append(f'{indent}```')
        result.extend([''] * trailing_blank_lines)
    return '\n'.join(result)


class SphinxMarkup(Extension):
    def on_instance(self, *, obj: Any, **kwargs: Any) -> None:  # ruff: ignore[unused-method-argument]
        if obj.docstring:
            value = _code_directives_to_fences(obj.docstring.value)
            obj.docstring.value = ROLE_PATTERN.sub(_role_to_crossref, value)
