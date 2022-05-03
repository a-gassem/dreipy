from datetime import datetime

class Voter():
    """This class wraps each voter's data whenever we insert or extra from the
database.

Attributes:
- voter_id    -- unique identifier string for this Voter object
- election_id -- election that this voter belongs to
- name        -- voter's first and last names concatenated with a space between
- postcode    -- voter's postcode
- uname       -- voter's username
- dob         -- voter's date of birth
- voted       -- whether or not this Voter has completed the election
"""

    # Constructor
    def __init__(self, voter_id: str, election_id: str, name: str,
                 postcode: str, uname: str, dob: datetime, hash: str,
                 voted: bool = False, current_q: int = 0):
        self._voter_id = voter_id
        self._election_id = election_id
        self._name = name
        self._postcode = postcode
        self._uname = uname
        self._dob = dob
        self._voted = voted
        self._hash = hash
        self._current = current_q

    def nextQuestion(self) -> None:
        """Increments the question counter for the voter"""
        self._current += 1

    def completeVoting(self) -> None:
        """Marks the voter as having finished the election"""
        self._voted = True

    # required properties and methods for LoginManager
    def get_id(self) -> str:
        try:
            return self.voter_id
        except AttributeError:
            raise NotImplementedError("No 'id' attribute - override 'get_id'") \
                  from None

    @property
    def is_active(self) -> bool:
        return True

    @property
    def is_authenticated(self) -> bool:
        return self.is_active

    @property
    def is_anonymous(self) -> bool:
        return False

    # ease of access properties
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
    def uname(self) -> str:
        return self._uname

    @property
    def dob(self) -> str:
        return self._dob

    @property
    def voted(self) -> bool:
        return self._voted

    @property
    def hash(self) -> str:
        return self._hash

    @property
    def current(self) -> int:
        return self._current
    
