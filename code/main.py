from flask import (Flask, render_template, redirect, session, url_for,
                   request, g, abort, flash)
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, login_user, current_user, login_required

from wtforms.validators import ValidationError
from werkzeug.datastructures import CombinedMultiDict

from Voter import Voter
from helpers import (parseTime, mergeTime, makeID, clearSession, firstReceipt,
                     checkCsv, makeFolder, bytestrToVKey, sKeyToBytestr,
                     auditBallot, prettyReceipt, isSafeUrl, parseElection)
from forms import (ElectionForm, SubmitForm, ViewElectionForm, LoginForm,
                   QuestionForm, AuditForm)
from db import (initApp, insertElection, getElectionFromDb, getVoterFromDb,
                isElectionInDb, getElectionStatus, validSessionData,
                getQuestionByNum, getNewBallotID, getPrivateKey,
                updateVoteReceipt, deleteBallot, updateAuditReceipt,
                updateAuditBallot, incrementTallies, deleteSecrets,
                getVoterFromSession, nextQuestion, completeVoting,
                totalQuestions, getAuditedReceipts, getQuestionTallies,
                getConfirmedReceipts)
from crypto import signData, hashString, verifyData

from typing import Optional
from datetime import datetime
from markupsafe import escape
from secrets import token_bytes, token_hex
import json
import jsonpickle
import os

DB_NAME = "dreipy.sqlite"
UPLOAD_FOLDER = "uploads/"

# maximum size of the uploaded CSV file (MiB)
MAX_FILE_SIZE_LIMIT = 5


# number of bytes to use when generating secrets
SECRET_BYTES = 32

## THINGS TO DO BEFORE DRAFT:
# TODO: delete CSV file after uploaded and data inserted into database
# TODO: bulletin board stuff -- graph of results for candidates;
#       sort receipts by ballot ID for ease of searching;
#       remove voter id from database as not needed
# TODO: contact in case of bad verification
#      (contact email address in Election object/db)
# TODO: multi-vote shit
# TODO: CSS so it's  p r e t t y

# FINISH LOGIN MANAGEMENT --> return Voter from Db call

# TODO: proper hashing/validation of stuff
# TODO: unit tests?

## general QoL improvements
# TODO: logging

## FLASK APP SETUP
main = Flask(__name__)

dbPath = os.path.join(main.instance_path, DB_NAME)
uploadPath = os.path.join(main.instance_path, UPLOAD_FOLDER)

# randomly generate a new secret key 
main.secret_key = token_bytes(SECRET_BYTES)
main.config.from_mapping(
    SECRET_KEY = token_hex(SECRET_BYTES),
    DATABASE = dbPath,
    UPLOAD_FOLDER = uploadPath,
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_LIMIT * 1024 * 1024,
    SESSION_COOKIE_SECURE = False   # we're not using HTTPS
)

# force the use of CSRF tokens in forms
CSRFProtect(main)

# create all the relevant folders
makeFolder(main.instance_path, permissions=750)
makeFolder(uploadPath, permissions=750)

# start the app and add the login manager
initApp(main)
login_manager = LoginManager()
login_manager.init_app(main)

@login_manager.user_loader
def load_voter(user_id) -> Optional[Voter]:
    return Voter.get(user_id)

@login_manager.unauthorized_handler
def unauthorised():
    flash("Unauthorised! Please login before trying to vote in an election.")
    return redirect(url_for('view'))

@main.errorhandler(404)
def not_found(error):
    return render_template("not_found.html", error=error)

@main.errorhandler(413)
def file_too_large(error):
    print(error)
    sizeInMib = main.config['MAX_CONTENT_LENGTH'] // (1024**2)
    flash(f"You tried to upload a file that was too large. Please only upload files with size up to {sizeInMib}MiB.", "error")
    return redirect(url_for("create"))

@main.route("/")
def splash():
    return render_template("splash.html")

@main.route("/about")
def about():
    return render_template("faq.html")

@main.route("/view", methods=['GET', 'POST'])
def view():
    form = ViewElectionForm(request.form)
    election = None
    if request.method == 'POST':
        election = getElectionFromDb(escape(form.election_id.data))
    return render_template("view.html", form=form, election=election)

@main.route("/create", methods=['GET', 'POST'])
def create():
    form = ElectionForm(CombinedMultiDict((request.files, request.form)))
    if form.validate_on_submit():
        title = form.title.data
        contact = form.contact.data
        delim = form.delimiter.data
        # validate the dates part of the form and construct datetimes
        time_tup = ElectionForm.validateDates(form)
        # validate the questions and choices in the form and construct
        # question dictionary
        questions = ElectionForm.validateQuestions(form.data)
        # validate the uploaded file and construct the new file location
        filepath = ElectionForm.validateFile(form)
        election_id = makeID()
        voters = checkCsv(election_id, filepath, delim)
        if time_tup is not None \
           and questions is not None \
           and filepath is not None \
           and voters is not None:
            # create election and redirect to confirmation
            start_time, end_time = time_tup
            election = parseElection(election_id, questions, start_time, end_time,
                                     title, contact)
            session['new_election'] = jsonpickle.encode(election)
            session['voters'] = jsonpickle.encode(voters)
            session['filepath'] = filepath
            return redirect(url_for("confirmElection"))
    return render_template("create.html", form=form, errors=form.errors)
    
@main.route("/confirm-election", methods=["GET", "POST"])
def confirmElection():
    
    # ensure the user has filled out the form properly
    if not 'new_election' in session:
        flash("Election incomplete, ensure that you correctly filled out the election details here.",
              "error")
        return redirect(url_for("create"))
    
    if not 'filepath' in session:
        flash("Election incomplete, ensure that you have uploaded the voter CSV file after filling out the election details.",
              "error")
        return redirect(url_for("create"))

    if not 'voters' in session:
        flash("Election incomplete, ensure that you uploaded a non-empty file for voters.",
              "error")
        return redirect(url_for("create"))

    election = jsonpickle.decode(session['new_election'])
    filepath = session['filepath']
    voters = jsonpickle.decode(session['voters'])
    if request.method == 'POST':
        # if we get a POST with all the checks passed at this point, then insert
        # into the DB
        inserted = insertElection(election, voters)
        if inserted is None:
            flash("Election was not inserted successfully", "error")
        else:
            # delete user file after inserting voters
            os.remove(filepath)
            flash("Election inserted successfully!", "info")
            session.pop('new_election')
            session.pop('filepath')
            session.pop('voters')
            return redirect(url_for("splash"))
    
    return render_template("confirm_election.html", form=SubmitForm(),
                           election=election, questions=election.questions)


@main.route("/login", methods=["GET", "POST"])
def voteLogin():
    # use GET request to parse and check the election ID we're trying to login with
    errors = session.pop("errors", [])
    clearSession(session)
    election_id = escape(request.args.get("election_id", ""))
    if not election_id:
        session['errors'] = ["No election ID given, please pass an election ID \
and try again."]
        return redirect(url_for("view"))

    status = getElectionStatus(election_id)
    
    if status is None:
        session['errors'] = [f"Invalid election ID passed: No election found \
with that ID."]
        return redirect(url_for("view"))
    
    if status.name == "PENDING":
        session['errors'] = [f"Election ID {election_id} has not started yet! Come back after\
{election.str_start_time}."]
        return redirect(url_for("view"))
    if status.name == "CLOSED":
        session['errors'] = [f"Election ID {election_id} has closed! Check out its results."]
        return redirect(url_for("view"))

    # if user is already logged in then send to next page
    if current_user.is_authenticated():
        return redirect(url_for("voting", election_id=election_id,
                                    question_num=voter_data['question']))

    # check login details on login
    form = LoginForm(request.form)
    if form.validate_on_submit():
        voter = getVoterFromDb(escape(form.email.data), escape(form.code.data),
                                    election_id)
        if voter is not None:
            # log user in after authentication
            login_user(voter)

            # protect against open redirects
            #next_endpoint = request.args.get('next')
            #if not isSafeUrl(next_endpoint):
            #    return abort(400)

            # if the user has finished voting, send to results page
            return redirect(url_for("voting", election_id=election_id,
                                    question_num=voter_data['question']))
        else:
            errors.append("Your email address and/or election code are incorrect.")
    return render_template("login.html", form=form, election_id=election_id,
                           errors=errors)

@main.route("/<string:election_id>/vote/<int:question_num>", methods=["GET", "POST"])
@login_required
def voting(election_id: str, question_num: int):
    # for users that have finished voting, send them to the results page
    if current_user.voted:
        return redirect(url_for("results", election_id=election_id))

    clean_id = escape(election_id)
    clean_num = int(escape(question_num))
    
    # make a Form from the Question object
    question = getQuestionByNum(clean_id, clean_num)
    if question is None:
        session['errors'] = ['Something went wrong when trying to fetch that question']
        return redirect(url_for("voteLogin", election_id=clean_id))
    form = QuestionForm(question, request.form)
    errors = []
    if form.validate_on_submit():
        if question.is_multi:
            choice = form.q_multi_choice.data
        else:
            choice = [form.q_single_choice.data]

        # do proofs, make receipts, sign data etc. etc.
        receipt = firstReceipt(question, clean_id, session['id'], choice)
        if receipt is None:
            errors.append('Something went wrong with your ballot, try again.')
        else:
            private_key = getPrivateKey()
            # note we truncate the the hash to 50 hex characters for ease of
            # validation. This does not seriously affect the security of the
            # program!
            session['hash'] = hashString(json.dumps(receipt)).upper()[:50]
            session['receipt'] = receipt
            session['first_sign'] = signData(session['hash'], private_key)    
            session['public_key'] = sKeyToBytestr(private_key.verifying_key)
            if updateVoteReceipt(session['first_sign'], session['hash'],
                                 receipt['ballot_id']) is None:
                deleteBallot(receipt['ballot_id'])
                errors.append("Could not sign your ballot, please try again.")
            else:
                return redirect(url_for("auditOrConfirm", election_id=clean_id,
                                        question_num=clean_num))
    return render_template("voting.html", form=form, errors=form.errors,
                           election_id=clean_id)

@main.route("/<string:election_id>/vote/<int:question_num>/audit", methods=["GET", "POST"])
@login_required
def auditOrConfirm(election_id: str, question_num: int):
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))
    if 'id' not in session:
        session['errors'] = ['Please login before trying to vote.']
        return redirect(url_for("voteLogin", election_id=clean_id))
    if not validSessionData(session['id'], clean_id, clean_num):
        session['errors'] = ['Invalid session data passed, login again.']
        return redirect(url_for("voteLogin", election_id=clean_id))
    if 'public_key' not in session or 'first_sign' not in session \
       or 'hash' not in session:
        session['errors'] = ['Bad session data, please try again.']
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    public_key = bytestrToVKey(session['public_key'])
    if not verifyData(session['hash'], public_key, session['first_sign']):
        session['errors'] = ['Could not verify vote receipt, please try again.']
        clearSession(session, ['hash', 'public_key', 'first_sign', 'receipt'])
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    form = AuditForm(request.form)
    errors = []
    if form.validate_on_submit():
        private = getPrivateKey()
        if form.audit.data and not form.confirm.data:
            # audit the ballot and go back to question
            receipt_data = auditBallot(session['question_id'],
                                       session['ballot_id'])
            if receipt_data is None:
                errors.append('Could not fetch ballot data, try again.')
            else:
                # sign the ballot in JSON form
                #new_receipt = json.dumps(receipt_data)
                #new_signature = signData(new_receipt, private)
                #if updateAuditReceipt(session['ballot_id'], new_signature) \
                #   is None:
                #    errors.append('Could not sign audited ballot.')
                #else:
                #clearSession(session, ['receipt', 'signature'])
                session['audited'] = prettyReceipt(session['receipt'])
                session['secret'] = receipt_data['choices'][0]['secret']
                session['vote'] = receipt_data['choices'][0]['vote']
                session['audit_sign'] = session['signature']
                return redirect(url_for('voting', election_id=clean_id,
                                        question_num=clean_num))
        elif not form.audit.data and form.confirm.data:
            # confirm selection and go to next question
            updateAuditBallot(session['ballot_id'], audited=False)
            incrementTallies(session['ballot_id'])
            deleteSecrets(session['ballot_id'])
            voter_id = getVoterFromSession(session['id'])
            new_num = nextQuestion(voter_id)
            session['confirmed'] = prettyReceipt(hashString(session['json']).upper()[:50])
            session['confirm_sign'] = signData(session['confirmed'], private)
            # if all questions have been completed then move to bulletin board
            if new_num > totalQuestions(clean_id):
                completeVoting(voter_id)
                return redirect(url_for('results', election_id=clean_id))
            return redirect(url_for('voting', election_id=clean_id,
                                    question_num=new_num))
        else:
            errors.append('Please either choose to audit or confirm your ballot.')
    return render_template("audit.html", form=form, errors=errors, clean_id=clean_id,
                           receipt=prettyReceipt(session['receipt']))

@main.route("/<string:election_id>/results", methods=["GET"])
def results(election_id: str):
    clean_id = escape(election_id)
    if 'id' not in session:
        session['errors'] = ['Please login before trying to access the bulletin board.']
        return redirect(url_for('voteLogin', election_id=clean_id))
    voter_id = getVoterFromSession(session['id'])
    audited = getAuditedReceipts(clean_id)
    confirmed = getConfirmedReceipts(clean_id)
    user_receipts = {"audited":[],
                     "confirmed":[]}
    for d in audited:
        if d['voter'] == voter_id:
            user_receipts['audited'].append(d['receipt'])
    for d in confirmed:
        if d['voter'] == voter_id:
            user_receipts['confirmed'].append(d['receipt'])
    election, errors = getElectionFromDb(clean_id)
    # each question has a different tally for each choice
    totals = {}
    for question in election.questions:
        totals[question.question_id] = []
        question_tallies = getQuestionTallies(question.question_id)
        for choice, tally, sum in question_tallies:
            totals[question.question_id].append({"choice":choice,
                                                 "tally":tally,
                                                 "sum":sum})
    return render_template("bulletin.html", user_receipts=user_receipts,
                           audited=audited, confirmed=confirmed,
                           election=election, totals=totals)
