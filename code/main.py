from flask import Flask, render_template, redirect, session, url_for, request
from helpers import longTime, parseTime, mergeTime, makeID, parseForm
from datetime import datetime
from forms import DateForm, ElectionForm

from Election import parseElection

main = Flask(__name__)

# make sure we securely generate these -- maybe environment variable?
main.config["SECRET_KEY"] = "TODO"
main.secret_key = b'_5#y2L"F4Q8z\n\xec]/'

# TODO: we need to log ALL THE THINGS!

@main.errorhandler(404)
def not_found(error):
    print(error)
    return render_template("not_found.html", error=error)

@main.route("/")
def splash():
    return render_template("splash.html")

@main.route("/about")
def about():
    return render_template("faq.html")

@main.route("/vote")
def vote():
    return render_template("vote.html")

@main.route("/create", methods=['GET', 'POST'])
def create():
    form = DateForm()
    # Note form.validate_on_submit() returns True iff:
    # 1. It was a POST request.
    # 2. The data is valid.
    # ==> GET requests and invalid inputs don't change the page.
    if (form.validate_on_submit()):
        start_time = parseTime(mergeTime(form.start_year.data, form.start_month.data,
                               form.start_day.data, form.start_hour.data,
                               form.start_mins.data, form.start_secs.data))
        end_time = parseTime(mergeTime(form.end_year.data, form.end_month.data,
                             form.end_day.data, form.end_hour.data,
                             form.start_mins.data, form.start_secs.data))

        if (start_time is None):
            form.form_errors.append("Badly formatted start date/time (are any fields empty?).")
        if (end_time is None):
            form.form_errors.append("Badly formatted end date/time (are any fields empty?).")

        if ((not start_time is None) and (not end_time is None)):
            if (start_time <= datetime.now()):
                form.form_errors.append("Please input a start date/time after the present.")
            if (end_time <= datetime.now()):
                form.form_errors.append("Please input an end date/time after the present.")
            if (start_time >= end_time):
                form.form_errors.append("Please input a time after the chosen start time.")
            if not form.errors:
                session['start_time'] = start_time
                session['end_time'] = end_time
                return redirect(url_for("createQuestions"))
    return render_template("create.html", form=form)

@main.route("/create-questions", methods=['GET', 'POST'])
def createQuestions():
    form = ElectionForm()
    errors = []
    if (request.method == 'POST'):
        print(request.form)
        
        # TODO: make it so that after a POST, if the request fails, the form
        # on the webpage maintains the choices, questions etc.
        electionDict, errors = parseForm(request.form)
        if not errors:
            # Now that we've parsed the unordered form response into a dictionary
            # that makes more sense, parse it all into an Election object
            election = parseElection(electionDict, session['start_time'],
                                     session['end_time'])
            print(election)
            if not election is None:
                #session['new_election'] = election
                # needs to be JSON serialisable??
                return redirect(url_for('voterUpload'))
            errors.append("Something went wrong when parsing the form data.")
    return render_template("create_questions.html", form=form, errors=errors)

@main.route("/create-voters", methods=['GET', 'POST'])
def voterUpload():
    return render_template("create_voters.html")

@main.route("/view")
def view(election):
    return render_template("view.html")
