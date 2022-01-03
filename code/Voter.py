from datetime import datetime

class Voter:
    """This class wraps each voter's data whenever we insert or extra from the
database.

Attributes:
- voter_id    -- unique identifier string for this Voter object
- election_id -- election that this voter belongs to
- name        -- voter's first and last names concatenated with a space between
- postcode    -- voter's postcode
- email       -- voter's email
- dob         -- voter's date of birth
- voted       -- whether or not this Voter has completed the election
"""

    # Constructor
    def __init__(self, voter_id: str, election_id: str, fname: str, lname: str,
                 postcode: str, email: str, dob: datetime, hash: str):
        self._voter_id = voter_id
        self._election_id = election_id
        self._name = fname[0].upper() + fname[1:] + ' ' +\
                     lname[0].upper() + lname[1:]
        self._postcode = postcode
        self._email = email
        self._dob = dob
        self._voted = False
        self._hash = hash
    
    @property
    def voter_id(self) -> str:
        return self._voter_id

    @property
    def election_id(self) -> str:
        return self._election_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def postcode(self) -> str:
        return self._postcode

    @property
    def email(self) -> str:
        return self._email

    @property
    def dob(self) -> str:
        return self._dob

    @property
    def voted(self) -> bool:
        return self._voted

    @property
    def hash(self) -> str:
        return self._hash
    
