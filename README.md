# DRE-ipy
Implementation of DRE-ip in Python (assuming Python 3.10.0)

# Installation (for Windows, commands should be similar in Linux)
Step 0: Download the source code 

Step 1: Create a virtual environment

Windows:
`py -3 -m venv dreipy`
`dreipy\Scripts\activate`

Step 2: Install dependencies

`pip install -U Flask flask-wtf flask-login jsonpickle cryptography matplotlib MarkupSafe ecdsa gmpy2`

Step 3: Run the app

`set FLASK_APP=main`
`flask run`