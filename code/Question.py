from typing import List, Tuple

class Question:
    """This class is responsible for storing the data needed to display a
question in an election with its query and choices. It assumes that well-
formed input has been passed to the constructor so all data sanitisation
should occur before an instance is created.

Attributes:
- question_id -- unique identifier string for this Question object
- query       -- string representation of the question itself
- max_answers -- the maximum number of answers that can be given for the question
- choices     -- list of Choices for this Question.
- sql_choices -- list of tuples that formatted for use with
                 Cursor.executemany() when inserting this object into the
                 database.
- num_choices -- the number of choices that are available for this Question.
- is_multi    -- whether this Question allows for multiple choices or not.

Methods:

Overridden:
- __str__(self) -- returns self.query joined with each Choice on a newline
"""
    
    # Constructor
    def __init__(self, question_id: str, query: str, max_answers: int,
                 choices: List[str]):
        self._question_id = question_id
        self._query = query
        self._max_answers = max_answers
        self._choices = choices
        self._sql_choices = [(question_id, i, choices[i]) \
                             for i in range(len(choices))]

    @property
    def question_id(self) -> str:
        return self._question_id

    @property
    def query(self) -> str:
        return self._query

    @property
    def max_answers(self) -> str:
        return self._max_answers

    @property
    def choices(self) -> List[str]:
        return self._choices

    @property
    def sql_choices(self) -> List[Tuple[str, int, str]]:
        return self._sql_choices

    @property
    def num_choices(self) -> int:
        return len(self.choices)

    @property
    def is_multi(self) -> bool:
        return self.max_answers > 1

    def __str__(self):
        string = self.query
        for i in range(len(self.choices)):
            string += f"\nChoice {i}: {str(self.choices[i])}"
        return string

    
        
    
