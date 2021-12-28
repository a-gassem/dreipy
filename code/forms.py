from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, DateTimeField, IntegerField
from wtforms.validators import DataRequired, Email, ValidationError

from helpers import parseTime

from datetime import datetime
from typing import Union, Callable

def valid_datetime(date_type: str) -> Callable:
    """Returns a callable validator for strings being parsed as dates - you can
specify whether it's a 'start' or 'end' date with the date_type field."""
    def _valid_datetime(form, field):
        date = parseTime(field.data)
        if (date is None):
            raise ValidationError(f"Incorrect format used for {date_type} date/time.")
        if (date <= datetime.now()):
            raise ValidationError("Please input a time after the present.")
            
    return _valid_datetime

class DateForm(FlaskForm):
    start_year = StringField("Start date and time:")
    start_month = StringField("")
    start_day = StringField("")
    start_hour = StringField("")
    start_mins = StringField("")
    start_secs = StringField("")
    
    end_year = StringField("End date and time:")
    end_month = StringField("")
    end_day = StringField("")
    end_hour = StringField("")
    end_mins = StringField("")
    end_secs = StringField("")
    
    submit = SubmitField("Next Page")
