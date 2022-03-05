from typing import List, Tuple, Dict
from Question import Question
from Status import Status, checkStatus
from datetime import datetime

class Election():
    """This class is responsible for containing the general data for a specific
election: its questions, the start/end times and ???

Attributes:
- election_id   -- random, unique identifier for this election
- title         -- the title for the election
- start_time    -- the date/time that the election opens for voting
- end_time      -- the date/time that the election closes for voting
- questions     -- list of questions for this election
- sql_questions -- a list of tuples that are formatted to be used with Cursor.executemany()
                   when inserting this object into the database.
- status        -- an integer value representing the state of the election.
                   Status.PENDING if now < self.start_time
                   Status.ONGOING if now >= self.start_time AND now < self.end_time
                   Status.CLOSED  if now >= self.end_time

Methods:
"""
    
    def makeQuestionTuples(questionList) -> List[Tuple[str, str, int, int]]:
        """Returns a list of SQL friendly tuples for all the Questions in the
Election, i.e: (question_id, query, question_num, num_answers)"""
        questionTups = []
        for i in range(len(questionList)):
            questionTups.append((questionList[i].question_id, questionList[i].query, i+1,
                                 questionList[i].max_answers))
        return questionTups

    def longTime(time_obj: datetime) -> str:
        """Returns the given datetime object as a long-form, user-friendly string.
E.g: Wednesday 30 March 2022 10:45:30AM"""
        return time_obj.strftime("%A %d %B %Y %I:%M:%S%p")

    def __init__(self, election_id: str, title: str,questions: List[Question],
                 start_time: datetime, end_time: datetime):
        self._election_id = election_id
        self._title = title
        self._questions = questions
        self._start_time = start_time
        self._end_time = end_time
        self._sql_questions = Election.makeQuestionTuples(questions)

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
    def status(self) -> Status:
        return checkStatus(self.start_time, self.end_time)

    def __str__(self):
        string = f"Election ID: {self.election_id}\n"
        string += f"Title: {self.title}\n\n"
        string += f"Starts: {self.str_start_time}\n"
        string += f"Ends: {self.str_end_time}\n"
        string += f"Status: {self.status.name}\n"
        for i in range(len(self.questions)):
            string += f"\nQuestion {i}: {str(self.questions[i])}\n"
        return string
