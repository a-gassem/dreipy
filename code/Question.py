class Question:
    """This class is responsible for storing the data needed to display a
question in an election with its query and choices. It assumes that well-
formed input has been passed to the constructor so all data sanitisation
should occur before an instance is created.

Attributes:
- question_id(str)           -- unique identifier string for this Question object
- query(str)                 -- string representation of the question itself
- max_answers(int)           -- the maximum number of answers that can be given for
                                the question (default = 1)
- choices(dict{int:Choice})  -- dictionary of answers for this Question,
                                where the index of the choice maps to its object
- sql_choices(list(3-tuple)) -- a list of tuples that are formatted to be used
                                with Cursor.executemany() when inserting this
                                object into the database

Methods:

Overridden methods:
- __str__(self) -- returns self.query joined with each Choice on a newline

Getters:
- getQuestionId(self) -- returns self.question_id
- getQuery(self)      -- returns self.query
- getMaxAns(self)     -- returns self.max_answers
- getChoices(self)    -- returns self.choices
- getSqlChoices(self) -- returns self.sql_choices

Helpers:
- isMulti(self)             -- returns True iff self.max_answers > 1
- getChoiceByIndex(self, i) -- returns the answer at self.choices[i]
- getNumChoices(self)       -- returns the number of choices available for this
                               question."""

    def _makeChoiceTuples(choiceDict):
        choiceList = []
        for c_index, choice in choiceDict:
            choiceList.append((choice.getChoiceId(), choice.getChoiceText(),
                               c_index))
        return choiceList
    
    # Constructor + getters
    def __init__(self, newID, query, choices, max_answers=1):
        self.question_id = newID
        self.query = query
        self.max_answers = max_answers
        self.choices = choices
        self.sql_choices = _makeChoiceTuples(choices)

    def __str__(self):
        string = self.query
        for index, choice in self.choices:
            string += f"\nChoice {index}: {str(choice)}"
        return string

    def getQuestionId(self):
        return self.question_id

    def getQuery(self):
        return self.query
    
    def getMaxAns(self):
        return self.max_answers

    def getChoices(self):
        return self.choices

    def getSqlChoices(self):
        return self.sql_choices

    # Helpers
    def isMulti(self):
        return self.max_answers > 1

    def getChoiceById(self, index):
        return self.choices[index]

    def getNumChoices(self):
        return len(self.choices)
        
    
