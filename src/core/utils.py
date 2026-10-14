import csv
import io
from abc import ABC, abstractmethod
from typing import Iterable, Iterator


class InvalidFileError(ValueError):
    pass


class IOReader(ABC):
    @abstractmethod
    def read(self) -> Iterator[dict[str, str]]:
        """Yield each record as a key/value dict."""


class CSVReader(IOReader):
    def __init__(self, content: bytes, required_columns: Iterable[str] = ()):
        self.content = content
        self.required_columns = set(required_columns)

    def read(self) -> Iterator[dict[str, str]]:
        try:
            text = self.content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise InvalidFileError("File must be UTF-8 encoded") from exc

        reader = csv.DictReader(io.StringIO(text))
        headers = {h.strip().lower() for h in (reader.fieldnames or [])}

        missing = self.required_columns - headers
        if missing:
            raise InvalidFileError(f"Missing columns: {', '.join(sorted(missing))}")

        for raw in reader:
            yield {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items()}
