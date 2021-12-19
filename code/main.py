from flask import Flask, render_template
from helpers import longTime

from Election import Election

main = Flask(__name__)

@main.route("/")
def splash():
    return render_template("splash.html")

@main.route("/about")
def about():
    return render_template("faq.html")

@main.route("/vote")
def vote():
    return render_template("vote.html")

@main.route("/create")
def create():
    return render_template("create.html")

@main.route("/view")
def view(election):
    return render_template("view.html", election=election)
