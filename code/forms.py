from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, SelectField, FileField
from wtforms.validators import DataRequired, Email, ValidationError
from werkzeug.utils import secure_filename

from helpers import parseTime, mergeTime, makeID, newFilename, isCsv
from Election import Election, parseElection
from Choice import Choice
from Question import Question

from datetime import datetime
from typing import Union, Callable, List, Tuple, Generic, Dict
import re
import os

class ElectionForm(FlaskForm):
    """Form that we use when a user chooses the starting date/time for their new
election. Note that we do not have a requirement about inputting all the fields
because otherwise there will be an error for every separate field -- the
parseTime() function will disallow any empty inputs anyway."""
    # for the election date/time
    start_year = StringField("Start date and time:")
    start_month = StringField()
    start_day = StringField()
    start_hour = StringField()
    start_mins = StringField()
    start_secs = StringField()
    
    end_year = StringField("End date and time:")
    end_month = StringField()
    end_day = StringField()
    end_hour = StringField()
    end_mins = StringField()
    end_secs = StringField()
    
    # for the election questions and title
    title = StringField("Election Title:", [DataRequired()])
    query_1 = StringField("Question text:", [DataRequired()])
    choice_1_1 = StringField("Choice:", [DataRequired()])
    choice_1_2 = StringField("Choice:", [DataRequired()])
    maxanswers_1 = SelectField("Number of answers:",
                              choices=[(1, 1)])

    # for uploading the voter CSV file
    file = FileField("Voter CSV File:", [DataRequired()])
    delimiter = StringField("Delimiter:", [DataRequired()], default=',')
    submit = SubmitField("Create Election")

class SubmitForm(FlaskForm):
    submit = SubmitField("Submit")

def validateDates(form) -> Tuple[Union[datetime, None],
                                 Union[datetime, None], List[str]]:
    errors = []
    start_time = None
    end_time = None
    try:
        start_time = parseTime(mergeTime(form['start_year'], form['start_month'],
                               form['start_day'], form['start_hour'],
                               form['start_mins'], form['start_secs']))
        end_time = parseTime(mergeTime(form['end_year'], form['end_month'],
                             form['end_day'], form['end_hour'],
                             form['start_mins'], form['start_secs']))
        if (start_time is None):
            errors.append("Badly formatted start date/time.")
        if (end_time is None):
            errors.append("Badly formatted end date/time.")
    except KeyError:
        errors.append("Empty form field found when creating start and end times\
. Please ensure that all fields are filled out")
    if not errors:
        if (start_time <= datetime.now()):
            errors.append("Please input a start date/time after the present.")
        if (end_time <= datetime.now()):
            errors.append("Please input an end date/time after the present.")
        if (start_time >= end_time):
            errors.append("Please input a time after the chosen start time.")
    return start_time, end_time, errors

def validateQuestions(form: Generic, start_time: datetime,
                      end_time: datetime) -> Tuple[Union[Election, None],
                                                   List[str]]:
    errors = []
    questions = {}
    title = None
    # We cannot know the order of the response, we also do not know how many
    # questions and choices there will be, so we need to use regex to figure
    # out what to do.
    try:
        for id, value in form.items():
            id = str(id)
            if (id == 'title'):
                if title is None:
                    title = str(value)
                    continue
                else:
                    errors.append("Multiple titles given for this election, please \
only pass one.")
                    continue
            qMatch = re.fullmatch('^query_([0-9]+)$', id, re.IGNORECASE)
            cMatch = re.fullmatch('^choice_([0-9]+)_([0-9]+)$', id, re.IGNORECASE)
            mMatch = re.fullmatch('^maxanswers_([0-9]+)$', id, re.IGNORECASE)
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
                # for all other form elements just ignore them
                continue
    except ValueError:
        errors.append("Invalid type encountered when parsing the questions - please check\
 that all values are of the correct type and try again.")

    # did we find an election title after iterating through everything?
    if title is None:
        errors.append("Please enter a title for this election.")
    if not errors:
        election = parseElection({'questions':questions, 'title':title},
                                 start_time, end_time)
        if election is None:
            errors.append("Something went wrong when parsing the form data.")
    return election, errors

def validateUpload(form, files: Dict, MAX_FILENAME_LENGTH: int,
                   UPLOAD_FOLDER: str) -> Tuple[Union[str, None],
                                                Union[str, None], List[str]]:
    errors = []
    newName = None
    delim = None
    if ((not 'delimiter' in form) or (len(form['delimiter']) != 1)):
        errors.append("Please enter a delimiter that is 1 character long for\
your CSV file.")
    if 'file' not in files:
        errors.append("No file found in form response.")
    if not errors:
        file = files['file']
        filename = file.filename
        if (len(filename) > MAX_FILENAME_LENGTH):
            errors.append("Please limit your filename length to 50 characters.")
        else:
            filename = secure_filename(filename)
            if not filename:
                errors.append("Empty file sent to server.")
            elif not isCsv(filename):
                errors.append("Please only upload a CSV file.")
    if not errors:
        # note we save the file with a filename we generate
        # ourselves and put it in session so we can refer back
        # to it on the next page
        filepath = os.path.join(UPLOAD_FOLDER, newFilename())
        delim = form['delimiter']
        file.save(filepath))
    return filepath, delim, errors
