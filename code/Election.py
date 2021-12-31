from typing import List, Tuple, Dict
from Question import Question
from Status import Status
from datetime import datetime
from helpers import longTime, makeID

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
    
    def _makeQuestionTuples(questionList):
        questionTups = []
        for i in range(len(questionList)):
            questionTups.append((questionList[i].question_id, questionList[i].query, i,
                                 questionList[i].max_answers))
        return questionTups

    def __init__(self, election_id: str, title: str,questions: List[Question],
                 start_time: datetime, end_time: datetime):
        self._election_id = election_id
        self._title = title
        self._questions = questions
        self._start_time = start_time
        self._end_time = end_time
        self._sql_questions = Election._makeQuestionTuples(questions)

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
    def end_time(self) -> datetime:
        return self._end_time

    @property
    def sql_questions(self) -> List[Tuple[str, str, int, int]]:
        return self._sql_questions

    @property
    def status(self) -> Status:
        now = datetime.now()
        # ensure that we use matching time zone information for calculations
        now = now.replace(tzinfo=self.start_time.tzinfo)
        if (now < self.start_time):
            return Status.PENDING
        elif (now >= self.start_time and now < self.end_time):
            return Status.ONGOING
        return Status.CLOSED

    def __str__(self):
        string = f"Election ID: {self.election_id}\n
        string += f"Title: {self.title}\n\n"
        string += f"Starts: {longTime(self.start_time)}\n"
        string += f"Ends: {longTime(self.end_time)}\n"
        string += f"Status: {self.status.name}\n"
        for i in range(len(self.questions)):
            string += f"\nQuestion {i}: {str(self.questions[i])}\n"
        return string

# bazinga
def parseElection(electionDict: Dict, start_time: datetime,
              end_time: datetime) -> Election:
    questionObjs = []
    questions = electionDict['questions']
    # note that we sort all our dictionaries to ensure that we get the correct
    # ordering of our lists when we iterate through them
    try:
        for questionNum, qDict in sorted(questions.items()):
            choiceObjs = []
            for choiceNum, choice in sorted(qDict['choices'].items()):
                choiceObjs.append(choice)
            questionObjs.append(Question(makeID(), qDict['query'],
                                         qDict['maxanswers'], choiceObjs))
        return Election(makeID(), electionDict['title'], questionObjs,
                        start_time, end_time)
    except Exception as e:
        # there shouldn't be any errors, but print to console just in case
        print(e)
        return None
