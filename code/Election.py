class Election:
    """This class is responsible for containing the general data for a specific
election: its questions, the start/end times and ???

Attributes:
- start_time(datetime.time)     -- the date/time that the election opens for
                                   voting, down to the precision of a second.
- end_time(datetime.time)       -- the date/time that the election closes for
                                   voting, down to the precision of a second.
- questions(dict{int:Question}) -- dictionary of questions for this election,
                                   where index i maps to the i-th Question object. 
"""

    def __init__(self, questions, start_time, end_time):
        self.questions = questions
        self.start_time = start_time
        self.end_time = end_time
