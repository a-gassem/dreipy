from typing import List, Tuple, Dict, Optional
from Question import Question
from Status import Status, checkStatus
from datetime import datetime

class Election():
    """
This class is responsible for containing the data for an election.

Attributes:
- election_id    -- random, unique identifier for this election
- title          -- the title for the election
- start_time     -- the date/time that the election opens for voting
- end_time       -- the date/time that the election closes for voting
- contact        -- the contact information of the election organiser
- questions      -- list of questions for this election
- num_questions  -- number of questions in the elections
- str_start_time -- long-form, user-friendly form of the election start time
- str_start_time -- long-form, user-friendly form of the election end time
- sql_questions  -- a list of tuples that are formatted to be used with
                    Cursor.executemany() when inserting this object into the
                    database.
- status         -- an integer value representing the state of the election.
                    Status.PENDING if now < self.start_time
                    Status.ONGOING if now >= self.start_time
                                    AND now < self.end_time
                    Status.CLOSED  if now >= self.end_time
"""
    
    def makeQuestionTuples(qList: List[Question], election_id: str) \
        -> List[Tuple[str, str, str, int, int, str, str, str, str]]:
        """
        Returns a list of SQL friendly tuples for all the Questions in the
        Election for easier insertion into the database.
        """
        from helpers import pointToBytestr
        questionTups = []
        for i in range(len(qList)):
            question = qList[i]
            questionTups.append((question.question_id, question.election_id,
                                 question.query, i+1, question.max_answers,
                                 pointToBytestr(question.gen_2)
                                 ))
        return questionTups

    def longTime(time_obj: datetime) -> str:
        """
        Returns the given datetime object as a long-form, user-friendly string.
        E.g: Wednesday 30 March 2022 10:45:30AM
        """
        return time_obj.strftime("%A %d %B %Y %I:%M:%S%p")

    def __init__(self, election_id: str, title: str, questions: List[Question],
                 start_time: datetime, end_time: datetime, contact: str):
        self._election_id = election_id
        self._title = title
        self._questions = questions
        self._start_time = start_time
        self._end_time = end_time
        self._contact = contact
        self._sql_questions = Election.makeQuestionTuples(questions, election_id)

    def getQuestion(self, question_id: str) -> Optional[Question]:
        """
        Given a question ID, returns the appropriate question object or None if
        a question with that ID is not found in the object.
        """
        for question in self.questions:
            if question.question_id == question_id:
                return question
        return None

    @property
    def election_id(self) -> str:
        return self._election_id

    @property
    def title(self) -> str:
        return self._title

    @property
    def questions(self) -> List[Question]:
        return self._questions

    @property
    def num_questions(self) -> int:
        return len(self.questions)

    @property
    def start_time(self) -> datetime:
        return self._start_time

    @property
    def str_start_time(self) -> str:
        return Election.longTime(self.start_time)

    @property
    def end_time(self) -> datetime:
        return self._end_time

    @property
    def str_end_time(self) -> str:
        return Election.longTime(self.end_time)

    @property
    def sql_questions(self) -> List[Tuple[str, str, int, int]]:
        return self._sql_questions

    @property
    def contact(self) -> str:
        return self._contact

    @property
    def status(self) -> Status:
        return checkStatus(self.start_time, self.end_time)
