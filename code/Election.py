from Status import Status

class Election():
    """This class is responsible for containing the general data for a specific
election: its questions, the start/end times and ???

Attributes:
- election_id(str)              -- random, unique identifier for this election
- start_time(datetime.time)     -- the date/time that the election opens for
                                   voting, down to the precision of a second.
- end_time(datetime.time)       -- the date/time that the election closes for
                                   voting, down to the precision of a second.
- questions(dict{int:Question}) -- dictionary of questions for this election,
                                   where index i maps to the i-th Question object. 
- sql_questions(list(4-tuples)) -- a list of tuples that are formatted to be used
                                   with Cursor.executemany() when inserting this
                                   object into the database.
- status({PENDING, ONGOING, CLOSED}) -- an integer value

Methods:

Helpers:
- getStatus(self) -- returns a Status: PENDING if now < self.start_time
                                       ONGOING if now >= self.start_time
                                           AND now < self.end_time
                                       CLOSED  if now >= self.end_time
                     where PENDING/ONGOING/CLOSED are enums in Status
Getters:
- getElectionId(self)   -- returns self.election_id
- getQuestions(self)    -- returns self.questions
- getStartTime(self)    -- returns self.start_time
- getEndTime(self)      -- returns self.end_time
- getSqlQuestions(self) -- returns self.sql_questions
"""

    def _makeQuestionTuples(questionDict):
        questionList = []
        for q_index, question in questionDict:
            questionList.append((question.getQuestionId(), question.getQuery(),
                                 q_index, question.getMaxAns()))
        return questionList

    def __init__(self, election_id, questions, start_time, end_time):
        self.election_id = election_id
        self.questions = questions
        self.start_time = start_time
        self.end_time = end_time
        self.sql_questions = _makeQuestionTuples(questions)

    def getElectionId(self):
        return self.election_id

    def getQuestions(self):
        return self.questions

    def getStartTime(self):
        return self.start_time

    def getEndTime(self):
        return self.end_time

    # Helpers
    def getStatus(self):
        #TODO
    
