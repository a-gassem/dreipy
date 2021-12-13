class Question:
    """This class is responsible for storing the data needed to display a
question in an election with its query and choices. It assumes that well-
formed input has been passed to the constructor so all data sanitisation
should occur before an instance is created.

Attributes:
- question_id(str)          -- unique identifier string for this Question object
- query(str)                -- string representation of the question itself
- max_answers(int)          -- the maximum number of answers that can be given for
                               the question (default = 1)
- choices(dict{int:string}) -- dictionary of answers for this Question,
                               where the index of the choice maps to its answer

Methods:

Overridden methods:
- __str__(self) -- returns self.query joined with each Choice on a newline

Getters:
- getQID(self)     -- returns self.question_id
- getQuery(self)   -- returns self.query
- getMaxAns(self)  -- returns self.max_answers
- getChoices(self) -- returns self.choices

Helpers:
- isMulti(self)             -- returns True iff self.max_answers > 1
- getChoiceByIndex(self, i) -- returns the answer at self.choices[i]
- getNumChoices(self)       -- returns the number of choices available for this
                               question."""
    
    # Constructor + getters
    def __init__(self, newID, query, choices, max_answers=1):
        self.question_id = newID
        self.query = query
        self.max_answers = max_answers
        self.choices = choices

    def __str__(self):
        string = self.query
        for index, choice in self.choices:
            string += f"\nChoice {index}: {choice}"
        return string

    def getQID(self):
        return self.question_id

    def getQuery(self):
        return self.query
    
    def getMaxAns(self):
        return self.max_answers

    def getChoices(self):
        return self.choices

    # Helpers
    def isMulti(self):
        return self.max_answers > 1

    def getChoiceById(self, index):
        return self.choices[index]

    def getNumChoices(self):
        return len(self.choices)
    
