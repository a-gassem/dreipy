from uuid import uuid4
from datetime import datetime
import re
from typing import Union, Dict, Any, Tuple, List, Generic

from Choice import Choice

LONG_FORMAT = "%A %d %B %Y %I:%M:%S%p"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

def makeID() -> str:
    """Generates a random, unique ID by making a UUID 4, converting to hex and
taking its string representation. Note, this is not cryptographically secure,
it's simply for indexing in the database!"""
    return str(uuid4().hex)

def longTime(time_obj: datetime) -> str:
    """Returns the given datetime object as a long-form, user-friendly string.
E.g: Wednesday 30 March 2022 10:45:30AM"""
    return time_obj.strftime(LONG_FORMAT)

def parseTime(time_str: str) -> Union[datetime, None]:
    """Returns a datetime object constructed from parsing the input string. If
the string is not well-formed, returns None."""
    try:
        return datetime.strptime(time_str, TIME_FORMAT)
    except ValueError:
        return None

def mergeTime(year: str, month: str, day: str, hour: str, mins: str,
              secs: str) -> str:
    return f"{year}-{month}-{day} {hour}:{mins}:{secs}" 

def parseForm(respForm: Generic) -> Tuple[Dict, List]:
    errors = []
    questions = {}
    title = None
    # We cannot know the order of the response, we also do not know how many
    # questions and choices there will be, so we need to use regex to figure
    # out what to do.
    try:
        for id, value in respForm.items():
            id = str(id)
            if (id == 'title'):
                if title is None:
                    title = str(value)
                    continue
                else:
                    errors.append("Multiple titles given for this election, please \
only pass one.")
                    continue
            elif (id == 'submit'):
                continue
            qMatch = re.match('^query_([0-9]+)$', id, re.IGNORECASE)
            cMatch = re.match('^choice_([0-9]+)_([0-9]+)$', id, re.IGNORECASE)
            mMatch = re.match('^maxanswers_([0-9]+)$', id, re.IGNORECASE)
            if qMatch:
                questionNum = int(qMatch.group(1))
                if questionNum in questions:
                    if 'query' in questions[questionNum]:
                        errors.append(f"Multiple query text entries found \
for question {questionNum}")
                    else:
                        questions[questionNum]['query'] = str(value)
                else:
                    questions[questionNum] = {'query':str(value)}
            elif cMatch:
                questionNum = int(cMatch.group(1))
                choiceNum = int(cMatch.group(2))
                newChoice = Choice(makeID(), str(value))
                if questionNum in questions:
                    if 'choices' in questions[questionNum]:
                        if choiceNum in questions[questionNum]['choices']:
                            errors.append(f"Multiple entries found for choice number \
{choiceNum} in question {questionNum}")
                        else:
                            questions[questionNum]['choices'][choiceNum] = newChoice
                    else:
                        questions[questionNum]['choices'] = {choiceNum:newChoice}
                else:
                    questions[questionNum] = {f'choice_{choiceNum}':newChoice}
            elif mMatch:
                questionNum = int(mMatch.group(1))
                if questionNum in questions:
                    if 'maxanswers' in questions[questionNum]:
                        errors.append("Multiple entries found for number of choices\
 in question {questionNum}.")
                    else:
                        questions[questionNum]['maxanswers'] = int(value)
                else:
                    questions[questionNum] = {'maxanswers':int(value)}
            else:
                errors.append(f"Badly formed form element: {id}, {value}")
    except ValueError:
        errors.append("Invalid type encountered when parsing the form - please check\
 that all values are of the correct type and try again.")
        return None, errors
    if title is None:
        errors.append("Please enter a title for this election.")
    return {'questions':questions, 'title':title}, errors
