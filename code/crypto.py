"""
A **multiplicative cyclic** group G is one where EVERY ELEMENT IS THE
POWER OF A PARTICULAR ELEMENT IN THE GROUP (g). I.e. g is a generator
if for all y in G, there exists k: y = g^k.

**additive cyclic** groups are those where g is a generator if:
for all y in G, there exists k such that y = gk

This is the same as G = <g>

Note that groups can have multiple generators.

A subgroup S is simply a subset of a group, G.

The order of a group, G is denoted |G| and is defined as:
The smallest positive integer n such that a^n = e (where e = identity,
usually 0)

If G is a finite cyclic group of order n, all elements in G have order,
t, such that t | n

Generators of Z

Subgroup G_q of group Z_p means:
- 

We pick two large primes where q | (p-1) --> p = rq + 1

For a cyclic group G_n (order n)

Elliptic curves:
1. Choose two initial points, A and B on curve of form y^2 = x^3 + ax + b
    reflect from the third point on the curve on that line
    to other side of x-axis. Let this new point be A'. Repeat n times between
    A' and A. Just having first and last point means it's hard to know n
    without doing the whole series.

2. choose values that are in a multiplicative cyclic group with a large prime
    as the maximum, curve equation, public point on the curve.

3. privately select a number, n, that is the number of times we dot on the
    curve

Recommended prime field elliptic curves:
https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.186-4.pdf
    
"""

import gmpy2
from gmpy2 import mpz, powmod, divexact

from ecdsa import NIST256p, SigningKey, VerifyingKey
from ecdsa.ellipticcurve import Point, INFINITY
from cryptography.hazmat.primitives import hashes

from secrets import randbelow
from base64 import b64encode
from typing import Tuple, List

# first generator, g, instantiated with domain parameters of NIST
# ecdsa.ellipticcurve.PointJacobi
g1 = NIST256p.generator

# ecdsa.ellipticcurve.CurveFp
curve = NIST256p.curve

# curve.a() was returning -3 which is incorrect???
a = mpz(int("ffffffff00000001000000000000000000000000fffffffffffffffffffffffc",
            16))
b = mpz(curve.b())
q = mpz(curve.p())
cofactor = mpz(curve.cofactor())
n = mpz(g1.order())

def hashString(string: str) -> str:
    """Returns hex representation of input string hashes with SHA-512"""
    digest = hashes.Hash(hashes.SHA512())
    digest.update(bytes(string, 'utf-8'))
    return digest.finalize().hex()

def signData(string: str, private: SigningKey) -> str:
    """Signs the passed string with the stored private key, return as b64 encoded
string."""
    return str(b64encode(private.sign(bytes(string, 'utf-8'))))

def generateKeyPair() -> Tuple[mpz, mpz]:
    """Generates a public/private key pair for the current curve"""
    private = SigningKey.generate(curve=NIST256p)
    public = private.verifying_key
    return private, public

def hashElectionString(election_string: str, count: int = None) -> mpz:
    """Returns a large integer derived from a SHA-256 hash of the election
id, current iteration of the parent loop, and the generator for the EC being
used."""
    digest = hashes.Hash(hashes.SHA256())
    digest.update(bytes.fromhex(hex(a)[2:]))
    digest.update(bytes.fromhex(hex(b)[2:]))
    digest.update(bytes(str(cofactor), 'utf-8'))
    digest.update(bytes.fromhex(hex(q)[2:]))
    digest.update(bytes.fromhex(hex(n)[2:]))
    
    # use generator, election ID and current iteration for digest
    digest.update(g1._compressed_encode())
    digest.update(bytes(election_string, 'utf-8'))
    if count is not None:
        digest.update(bytes(str(count), 'utf-8'))
    return mpz(int.from_bytes(digest.finalize(), byteorder="big"))

def eulerCriterion(num: mpz) -> bool:
    """Euler's criterion. q is an odd prime > 2. https://en.wikipedia.org/wiki/Euler%27s_criterion"""
    return powmod(num, divexact(q-1, 2), q)

def generatePair(election_string: str) -> Tuple[Point, Point]:
    """Returns a pair of EC points using the NIST256p field (length 256b)."""
    
    # manually create second generator according to supervisor's algorithm
    count = 0
    while True:
        x = hashElectionString(election_string, count)
        # Compute z = x^3 + ax + b
        z = (powmod(x, 3, q) + (a*x + b)) % q

        # Check if z has a square root, i.e., the Lengendre symbol = 1
        if eulerCriterion(z) == 1:

            # We can use Shanks' algorithm to compute a square root of z mod q
            # But since q = 3 mod 4, we can do it in a simpler way:
            # sqr(z) = z^((q+1)/4) mod q
            y = powmod(z, divexact(q+1, 4), q)

            # check the point is actually on the curve (i.e. in the group
            # we defined)
            g2 = Point(curve, x, y)
            
            if (g2 != INFINITY) and ((g2 * cofactor) != INFINITY):
                return g1, g2
        count += 1

def generateRandSecret() -> mpz:
    """Returns an mpz object in the range [1, n-1]"""
    r = 0
    while r == 0:
        r = randbelow(n)
    return mpz(r)

def generateR(g2: Point, r: mpz) -> Point:
    """Returns a Point p = g2^rand"""
    return g2 * r

def generateZ(r: mpz, v: int) -> Point:
    """Returns a Point p = g1^r * g1^v"""
    return (g1 * r) + (g1 * v)

def generateZKProof(g2: Point, R: Point, Z: Point, r: mpz, voted: bool,
                    question_id: str, vote_id: int, ballot_id: str) \
                    -> Tuple[mpz, mpz, mpz, mpz]:
    """Zero-knowledge proof of knowledge of r
0. r is random in [1, n-1]; R = g2^r
1. choose random c in [1, n-1]
2. calculate t = (r + cw) mod p; user checks g^t = rR^c
"""     
    w = generateRandSecret()

    if voted:
        r_1 = generateRandSecret()
        c_1 = generateRandSecret()
        
        t_1 = (g1 * r_1) + (Z * c_1)
        t_2 = (g2 * r_1) + (R * c_1)
        t_3 = g1 * w
        t_4 = g2 * w

        message = f"""{question_id},{vote_id},{ballot_id},
{self.g1.to_bytes().hex()},{self.g2.to_bytes().hex()},
{Z.to_bytes().hex()},{R.to_bytes().hex()},
{t_1.to_bytes().hex()},{t_2.to_bytes().hex()},
{t_3.to_bytes().hex()},{t_4.to_bytes().hex()}"""

        c = hashElectionString(message)
        c_2 = mpz((c - c_1) % n)
        r_2 = mpz((w - (c_2 * r)) % n)
        
    else:
        r_2 = generateRandSecret()
        c_2 = generateRandSecret()
        
        t_1 = g1 * w
        t_2 = g2 * w
        t_3 = (g1 * r_2) + ((Z + (-g1)) * c_2)
        t_4 = (g2 * r_2) + (R * c_2)
        
        message = f"""{question_id},{vote_id},{ballot_id},
{g1.to_bytes().hex()},{g2.to_bytes().hex()},
{Z.to_bytes().hex()},{R.to_bytes().hex()},
{t_1.to_bytes().hex()},{t_2.to_bytes().hex()},
{t_3.to_bytes().hex()},{t_4.to_bytes().hex()}"""

        c = hashElectionString(message)
        c_1 = mpz((c - c_2) % n)
        r_1 = mpz((w - (c_1 * r)) % n)
    return (r_1, r_2, c_1, c_2)

def generateNumProof(self, R: List[Point], Z: List[Point]) -> List[mpz]:
    return
