# DRE-ipy
Implementation of DRE-ip in Python

# Installation
Step 0: Download the source code 

Step 1: Create a virtual environment for the dependencies here (assuming Python 3.7+)

Windows:
py -3 -m venv dreipy&
dreipy\Scripts\activate&

Step 2: Install dependencies (Flask, WTForms, probs some cryptography libraries too)

pip install Flask&
pip install flask-wtf&

Step 3: Run the app (note that the venv is called dreipy)

set FLASK_APP=main&
flask run&