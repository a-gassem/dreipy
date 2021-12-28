class Choice:
    """Class to contain each choice/answer possible for a given question.

Attributes:
- choice_id(str) -- random, unique identifier string for this Choice object
- text(str)      -- text that represents this choice/answer

Methods:

Overridden:
- __str__(self) -- returns self.text

"""

    def __init__(self, choice_id: str, text: str):
        self._choice_id = choice_id
        self._text = text

    @property
    def choice_id(self) -> str:
        return self._choice_id

    @property
    def text(self) -> str:
        return self._text

    def __str__(self):
        return self.text


