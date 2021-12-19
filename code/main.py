from flask import Flask

main = Flask(__name__)

@main.route("/")
def splash():
    return "<p>Hello, World!</p>"
