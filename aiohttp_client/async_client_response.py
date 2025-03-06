from dataclasses import dataclass


@dataclass
class AsyncClientResponse:
    code: int = 0
    text: str = ""
    data: dict = None
    error: str = None
    reason: str = ""
    _is_error: bool = False

    def __post_init__(self):
        self.data = {} if not self.data else self.data

        # Iterate of data dictionary fields and see if it contains a non-empty error field
        if any((matched_key := key) in self.data for key in {"error", "errors", "error_message"}):
            if self.data[matched_key]:
                self.error = str(self.data.get(matched_key)) if self.data.get(matched_key) else f"{self.reason} - {self.text}"
                self._is_error = True
        elif self._is_error:
            self.error = self.text
            self._is_error = True

    @property
    def is_empty(self) -> bool:
        """
        Returns a boolean value of whether the response contains valid JSON data or not.

        :return: (bool)
        """
        return not self.data

    @property
    def is_error(self) -> bool:
        """
        Returns a boolean value of whether the request resulted in an error or not.

        :return: (bool)
        """
        return self._is_error or bool(self.error)