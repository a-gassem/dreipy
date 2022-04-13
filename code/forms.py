from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms import (StringField, SubmitField, SelectField,
                     SelectMultipleField, RadioField, widgets)
from wtforms.validators import DataRequired, Email, ValidationError
from werkzeug.utils import secure_filename
from flask import current_app, flash

from helpers import parseTime, parseElection, mergeTime, makeID, newFilename
from Election import Election
from Question import Question

from datetime import datetime
from typing import Union, List, Tuple, Generic, Dict, Optional, Callable
import re
import os

# maximum length of the uploaded CSV filename (number of characters)
MAX_FILENAME_LENGTH = 50

class ElectionForm(FlaskForm):
    """Form that we use when a user chooses the starting date/time for their new
election. Note that we do not have a requirement about inputting all the fields
because otherwise there will be an error for every separate field -- the
parseTime() function will disallow any empty inputs anyway."""
    # for the election date/time
    start_year = StringField("Start date and time:", validators=[DataRequired()])
    start_month = StringField(validators=[DataRequired()])
    start_day = StringField(validators=[DataRequired()])
    start_hour = StringField(validators=[DataRequired()])
    
    end_year = StringField("End date and time:", validators=[DataRequired()])
    end_month = StringField(validators=[DataRequired()])
    end_day = StringField(validators=[DataRequired()])
    end_hour = StringField(validators=[DataRequired()])
    
    # for the election questions and title
    title = StringField("Election Title:", [DataRequired()])
    contact = StringField("Election organiser email address:", [DataRequired()])
    query_1 = StringField("Question text:", [DataRequired()])
    choice_1_1 = StringField("Choice:", [DataRequired()])
    choice_1_2 = StringField("Choice:", [DataRequired()])
    
    # note we do not validate the choice since we do that in the validator method
    # and this allows for dynamic choices to be added
    maxanswers_1 = SelectField("Number of answers:", choices=[(1, 1)],
                               validators=[DataRequired()], validate_choice=False)

    # for uploading the voter CSV file
    file = FileField("Voter CSV File:", validators=[FileRequired(),
                                                    FileAllowed(['csv'], "Only CSV files allowed.")])
    delimiter = StringField("Delimiter:", [DataRequired()], default=',')
    submit = SubmitField("Create Election")

    def validate_delimiter(form: FlaskForm, field: StringField) -> None:
        """Validation for the delimiter, ensure it is some 1-char string."""
        if len(field.data) != 1:
            raise ValidationError("Please enter a delimiter that is 1 character long for your CSV file.")

    def validateFile(form: FlaskForm) -> Optional[str]:
        """Make sure a CSV file of an appropriate filename length has been uploaded,
            and save the file under a new, random file name."""
        new_file = form.file.data
        if len(secure_filename(new_file.filename)) > MAX_FILENAME_LENGTH:
            flash(f"Please limit your filename length to {MAX_FILENAME_LENGTH} characters.", "error")
            return None
        filepath = os.path.join(current_app.config["UPLOAD_FOLDER"],
                                newFilename())
        new_file.save(filepath)
        return filepath

    def validateDates(form: FlaskForm) -> Optional[Tuple[datetime, datetime]]:
        """Parse start/end times while validating them."""
        try:
            start_time = parseTime(mergeTime(
                form.start_year.data, form.start_month.data, form.start_day.data,
                form.start_hour.data))
            end_time = parseTime(mergeTime(
                form.end_year.data, form.end_month.data, form.end_day.data,
                form.end_hour.data))
            if (start_time is None):
                flash("Badly formatted start date/time.", "error")
                return None
            if (end_time is None):
                flash("Badly formatted end date/time.", "error")
                return None
        except AttributeError:
            flash("Empty form field found. Please ensure that all fields are filled out", "error")
            return None
        if (start_time <= datetime.now()):
            flash("Please input a start date/time after the present.", "error")
            return None
        if (end_time <= datetime.now()):
            flash("Please input an end date/time after the present.", "error")
            return None
        if (start_time >= end_time):
            flash("Please input an end time after the chosen start time.", "error")
            return None
        return (start_time, end_time)

    def validateQuestions(form_data: dict) -> Optional[dict]:
        questions = {}
        try:
            for id, value in form_data.items():
                id = str(id)
                q_match = re.fullmatch('^query_([0-9]+)$', id, re.IGNORECASE)
                c_match = re.fullmatch('^choice_([0-9]+)_([0-9]+)$', id, re.IGNORECASE)
                m_match = re.fullmatch('^maxanswers_([0-9]+)$', id, re.IGNORECASE)
                if q_match:
                    question_num = int(q_match.group(1))
                    new_query = str(value)
                    if question_num in questions:
                        if 'query' in questions[question_num]:
                            flash(f"Multiple query text entries found for question {question_num}", "error")
                            return None
                        else:
                            questions[question_num]['query'] = new_query
                    else:
                        questions[question_num] = {'query': new_query}
                elif c_match:
                    question_num = int(c_match.group(1))
                    choice_num = int(c_match.group(2))
                    new_choice = str(value)
                    if question_num in questions:
                        if 'choices' in questions[question_num]:
                            if choice_num in questions[question_num]['choices']:
                                flash(f"Multiple entries found for choice number {choice_num} in question {question_num}", "error")
                                return None
                            else:
                                questions[question_num]['choices'][choice_num] = new_choice
                        else:
                            questions[question_num]['choices'] = {choice_num:new_choice}
                    else:
                        questions[question_num] = {f'choice_{choice_num}':new_choice}
                elif m_match:
                    question_num = int(m_match.group(1))
                    num_answers = int(value)
                    if num_answers < 1:
                        raise ValidationError("The number of choices for a question must be at least 1.")
                    if question_num in questions:
                        if 'numanswers' in questions[question_num]:
                            flash("Multiple entries found for number of choices in question {question_num}.", "error")
                            return None
                        else:
                            questions[question_num]['numanswers'] = num_answers
                    else:
                        questions[question_num] = {'numanswers':num_answers}
            # after for loop, ensure that no questions ask N or more answers
            # where N = number of answers
            for question_num, question_dict in questions.items():
                if question_dict['numanswers'] >= len(question_dict['choices'].items()):
                    flash("The number of choices must be less than the number of answers", "error")
                    return None
            return questions
        except ValueError:
            flash("Invalid type encountered when parsing the questions - please check that all values are of the correct type and try again.", "error")
            return None

class ViewElectionForm(FlaskForm):
    election_id = StringField("Election ID:", [DataRequired()])
    submit = SubmitField("Search")

class LoginForm(FlaskForm):
    email = StringField("Enter your email address:", [DataRequired()])
    code = StringField("Enter your code:", [DataRequired()])
    submit = SubmitField("Login")

class SubmitForm(FlaskForm):
    submit = SubmitField("Submit")

# from https://gist.github.com/ectrimble20/468156763a1389a913089782ab0f272e
class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class QuestionForm(FlaskForm):
    # initialise Form with default attributes that we overwrite in the
    # constructor
    q_multi_choice = MultiCheckboxField("Default", choices=[(0, "default")],
                                        coerce=int, validate_choice=False)
    q_single_choice = RadioField("Default", choices=[(0, "default")],
                                 coerce=int, validate_choice=False)
    expected_choices = 1
    choice_list = []
    submit = SubmitField("Vote")

    def __init__(self, question: Question, *args, **kwargs) -> FlaskForm:
        super().__init__(*args, **kwargs)
        self.choice_list = [(i, question.choices[i]) \
                            for i in range(len(question.choices))]
        if question.is_multi:
            self.q_multi_choice.label.text = question.query
            self.q_multi_choice.choices = self.choice_list
        else:
            self.q_single_choice.label.text = question.query
            self.q_single_choice.choices = self.choice_list
        self.expected_choices = question.max_answers

    def validate_q_single_choice(form: FlaskForm, field: RadioField) \
        -> Optional[ValidationError]:
        """Validator for questions that only allow 1 choice."""
        if form.expected_choices != 1:
            return
        try:
            choice_index = int(field.data)
            if choice_index < 0 or choice_index >= len(form.choice_list):
                raise ValidationError("Choice index outside question range")
        except TypeError:
            raise ValidationError("Choice index must be an integer")

    def validate_q_multi_choice(form: FlaskForm, field: MultiCheckboxField) \
        -> Optional[ValidationError]:
        """Validator for questions that require more than 1 choices."""
        if form.expected_choices == 1:
            return
        if field is None or len(field.data) != form.expected_choices:
            raise ValidationError(f"Bad number of choices (expected {form.expected_choices})")
        try:
            for entry in field.data:
                choice_index = int(entry)
                if choice_index < 0 or choice_index >= len(form.choice_list):
                    raise ValidationError("Choice index outside question range")
        except TypeError:
            raise ValidationError("All choice indices must be integers")

class AuditForm(FlaskForm):
    audit = SubmitField("Audit")
    confirm = SubmitField("Confirm")
