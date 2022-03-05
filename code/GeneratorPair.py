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

from ecdsa import SigningKey, NIST256p
from cryptography.hazmat.primitives import hashes
from . import _hashElection

class GeneratorPair:

    # first generator, g, instantiated with domain parameters of NIST
    g1 = NIST256p.generator
    curve = NIST256p.curve
    a = curve.a
    b = curve.b
    p = curve.p
    cofactor = curve.cofactor
    n = g1.order

    def _hashElection(election_id: str, count: int) -> int:
        """Returns a large integer derived from a SHA-256 hash of the election
id, current iteration of the parent loop, and the generator for the EC being
used."""
        digest = hashes.Hash(hashes.SHA256())
        digest.update(bytearray(a))
        digest.update(bytearray(b))
        digest.update(bytearray(cofactor))
        digest.update(bytearray(p))
        digest.update(bytearray(n))
        
        # use generator, election ID and current iteration for digest
        digest.update(bytearray(g1))
        digest.update(bytearray(election_id))
        digest.update(bytearray(str(count)))
        return int.from_bytes(digest.finalize(), byteorder="big")

    def __init__(self, election_id: str):
        # generate pair of EC points using NIST prime field (length 256b)
        # prime256v1

        # use election id as parameter for uniqueness????
        n = g1.order()
        

        # manually create second generator according to supervisor's algorithm
        count = 0
        while True:
            x = _hashElection(election_id, count)
            
            # Compute z = x^3 + ax + b
            z = (x**3 + a * x + b) % p

            # Check if z has a square root, i.e., the Lengendre symbol = 1
            if _hasSquare(z):

                # We can use Shanks' algorithm to compute a square root of z mod q
                # But since q = 3 mod 4, we can do it in a simpler way:
                # sqr(z) = z^((q+1)/4) mod q

                y = pass

                # check the point is actually on the curve (i.e. in the group
                # we defined)
                g2 = pass
            count += 1
