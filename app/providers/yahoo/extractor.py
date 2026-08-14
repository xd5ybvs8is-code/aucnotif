import json

PAGEDATA_MARKERS = ("pageData", "PageData")
MAX_OBJECT_LEN = 1_000_000


class PageDataExtractionError(ValueError):
    pass


class PageDataExtractor:
    """Безопасно извлекает JavaScript-объект `pageData` из HTML.

    Вместо хрупкого regex `var pageData = ({.*?});` используется
    сбалансированный парсер скобок с учётом строковых литералов,
    а результат парсится как JSON и прогоняется через Pydantic.
    """

    def extract(self, html: str) -> dict:
        for candidate_start in self._iter_candidates(html):
            raw = self._extract_balanced_object(html, candidate_start)
            if raw is None:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                return obj
        raise PageDataExtractionError("pageData not found in HTML")

    def _iter_candidates(self, html: str):
        seen: set[int] = set()
        for marker in PAGEDATA_MARKERS:
            pos = 0
            while True:
                idx = html.find(marker, pos)
                if idx == -1:
                    break
                if idx in seen:
                    pos = idx + len(marker)
                    continue
                seen.add(idx)
                brace = html.find("{", idx, idx + 200)
                if brace != -1:
                    yield brace
                pos = idx + len(marker)

    def _extract_balanced_object(self, text: str, start: int) -> str | None:
        if start >= len(text) or text[start] != "{":
            return None
        depth = 0
        i = start
        in_string = False
        escaped = False
        while i < len(text):
            ch = text[i]
            if in_string:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        if i - start > MAX_OBJECT_LEN:
                            return None
                        return text[start : i + 1]
            i += 1
        return None
