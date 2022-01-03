from flask import Flask, render_template, redirect, session, url_for, request
from helpers import longTime, parseTime, mergeTime, makeID, clearSession, checkCsv
from datetime import datetime
from forms import (ElectionForm, SubmitForm, validateDates, validateQuestions,
                   validateUpload)
from db import initDB, insertElection
import jsonpickle
import os

# maximum length of the uploaded CSV filename (number of characters)
MAX_FILENAME_LENGTH = 50

# TODO: we need to log ALL THE THINGS!

@main.errorhandler(404)
def not_found(error):
    print(error)
    return render_template("not_found.html", error=error)

@main.errorhandler(413)
def file_too_large(error):
    print(error)
    sizeInMib = main.config['MAX_CONTENT_LENGTH'] // (1024**2)
    session["errors"] = [f"You tried to upload a file that was too large. Please\
 only upload files with size up to {sizeInMib}MiB."]
    return redirect(url_for("create"))

@main.route("/")
def splash():
    # clear any session variables that we should not keep for this page
    clearSession(session)
    session['errors'] = []
    return render_template("splash.html")

@main.route("/about")
def about():
    clearSession(session)
    session['errors'] = []
    return render_template("faq.html")

@main.route("/vote")
def vote():
    clearSession(session)
    # copy the session errors into a local variable, then clear the session
    # errors so that they do not continue to future requests
    errors = session['errors']
    session['errors'] = []
    return render_template("vote.html", errors=errors)

@main.route("/create", methods=['GET', 'POST'])
def create():
    # store any errors before we clear the session variable
    errors = session['errors']
    clearSession(session)
    session['errors'] = []
    form = ElectionForm()
    if ((not errors) and (request.method == 'POST')):
        form = request.form
        # validate the date part of the form
        start_time, end_time, dateErrors = validateDates(form)        
        if not dateErrors:
            # validate the question part of the form
            election, questionErrors = validateQuestions(form, start_time,
                                                         end_time)            
            if not questionErrors:
                # validate the file upload part of the form
                filepath, delim, uploadErrors = validateUpload(form, request.files,
                                                               MAX_FILENAME_LENGTH,
                                                               main.config["UPLOAD_FOLDER"])
                if not uploadErrors:
                    # go to the confirm page after assigning values to session
                    sample, warnEmails, csvErrors = checkCsv(filepath, delim)
                    if not csvErrors:
                        session['new_election'] = jsonpickle.encode(election)
                        session['delim'] = delim
                        session['filename'] = filepath
                        session['warn'] = warnEmails
                        session['sample'] = sample
                        return redirect(url_for("confirmElection"))
                    errors += csvEerrors
                else:
                    errors += uploadErrors
            else:
                errors += questionErrors
        else:
            errors += dateErrors
    return render_template("create.html", form=form, errors=errors)
    

# TODO: make it so that after a POST, if the request fails, the form
# on the webpage maintains the choices, questions etc. ALSO display the errors
# lmao
@main.route("/confirm-election", methods=["GET", "POST"])
def confirmElection():
    samples = session.pop('sample', None)
    warnEmails = session.pop('warn', None)
    session['errors'] = []
    
    # ensure the user has filled out the form properly
    if (not 'new_election' in session):
        session['errors'].append("Election incomplete, ensure that you \
correctly filled out the election details here.")
        return redirect(url_for("create"))
    if ((not 'delim' in session) or (not 'filename' in session)):
        session['errors'].append("Election incomplete, ensure that you \
have uploaded the voter CSV file after filling out the election details.")
        return redirect(url_for("create"))
    if samples is None:
        session['errors'].append("Empty voter file uploaded. Please ensure \
that you have uploaded a valid, non-empty voter CSV file before trying to \
confirm the election.")
        return redirect(url_for("create"))
    election = jsonpickle.decode(session['new_election'])
    if (request.method == 'POST'):
        # if we get a POST with all the checks passed at this point, then insert
        # into the DB
        insertElection(election, session['filename'], session['delim'])
    return render_template("confirm_election.html", form=SubmitForm(),
                           election=election, questions=election.questions,
                           samples=samples, warnings=warnEmails,
                           start=start_time, end=end_time)


@main.route("/view", methods=["GET"])
def view():
    clearSession(session)
    session['errors'] = []
    return render_template("view.html")
