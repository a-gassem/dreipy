class Choice:
    """Class to contain each choice/answer possible for a given question.

Attributes:
- choice_id(str) -- random, unique identifier string for this Choice object
- text(str)      -- text that represents this choice/answer

Methods:

Overridden:
- __str__(self) -- returns self.text

Getters:
- getChoiceId(self)   -- returns self.choice_id
- getChoiceText(self) -- returns self.text"""

    def __init__(self, choice_id, text):
        self.choice_id = choice_id
        self.text = text

    def __str__(self):
        return self.text

    def getChoiceId(self):
        return self.choice_id

    def getChoiceText(self):
        return self.text
