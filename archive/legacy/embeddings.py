"""
Text embeddings, with a local fallback.

The primary encoder is a Hugging Face inference endpoint running
all-MiniLM-L6-v2. That endpoint needs credits, and a network round-trip on
every question is a latency cost the app does not need to pay.

So when the hosted encoder is unavailable, we fall back to a local hashing
embedder. It is not a language model and does not understand synonyms - but
for the two jobs we use embeddings for, keyword overlap is most of the value:

  - schema retrieval: "which artist has the most albums" should match the
    Album table, and that table's text literally contains "album"
  - semantic cache: an almost-identical rephrasing shares most of its words

The fallback is deterministic, needs no network, and costs nothing. When the
hosted encoder is available it is used instead, because it is strictly better.
"""

import hashlib
import math
import re
from typing import List, Optional

VECTOR_SIZE = 384  # must match the collection's vector size

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

# Very common words carry no signal about which table is relevant, and
# including them makes everything look equally similar to everything else.
_STOP_WORDS = frozenset(
    """
    a an and are as at be by for from has have how in is it its of on or that the
    to was were what when where which who whom whose with show me my please
    all any some there here get give find list tell
    """.split()
)


def _tokenise(text: str) -> List[str]:
    """Lower-case word tokens, with stop words removed."""
    tokens = _TOKEN_RE.findall((text or "").lower())
    return [t for t in tokens if t not in _STOP_WORDS and len(t) > 1]


class LocalHashingEmbeddings:
    """
    A deterministic hashing embedder.

    Each token is hashed into one of VECTOR_SIZE buckets and contributes to
    that bucket. A second hash decides the sign, so two different tokens
    landing in the same bucket partially cancel instead of doubling up. Token
    bigrams are included as well, which captures a little word order.

    The result is a bag-of-words vector in the same shape as the hosted
    encoder's output, so the same Qdrant collection holds both.
    """

    def __init__(self, size: int = VECTOR_SIZE):
        self.size = size

    def _hash(self, token: str) -> tuple:
        digest = hashlib.blake2b(token.encode('utf-8'), digest_size=8).digest()
        value = int.from_bytes(digest, 'big')
        return value % self.size, 1.0 if (value >> 63) & 1 else -1.0

    def embed_query(self, text: str) -> List[float]:
        tokens = _tokenise(text)
        vector = [0.0] * self.size

        if not tokens:
            return vector

        for token in tokens:
            index, sign = self._hash(token)
            vector[index] += sign

        # Bigrams capture a little word order, which helps distinguish
        # "album artist" from "artist album".
        for first, second in zip(tokens, tokens[1:]):
            index, sign = self._hash(f"{first}_{second}")
            vector[index] += sign * 0.5

        # L2-normalise, so cosine similarity is a plain dot product.
        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude:
            vector = [value / magnitude for value in vector]

        return vector

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(text) for text in texts]


class FallbackEmbeddings:
    """
    Wraps the hosted encoder and falls back to the local one when the hosted
    call fails. The app never sees an exception from an embedding call.
    """

    def __init__(self, primary=None, size: int = VECTOR_SIZE):
        self.primary = primary
        self.local = LocalHashingEmbeddings(size)
        self.using_primary = primary is not None

    def embed_query(self, text: str) -> List[float]:
        if self.primary is not None:
            try:
                return self.primary.embed_query(text)
            except Exception:
                # A failed hosted call must not break the request. Switch to
                # the local encoder for the rest of the process's life.
                self.primary = None
                self.using_primary = False
        return self.local.embed_query(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_query(text) for text in texts]


def build_embeddings(hf_token: Optional[str] = None, size: int = VECTOR_SIZE) -> FallbackEmbeddings:
    """
    Build the embedder to use. The hosted encoder is used when a token is
    available and it answers; otherwise the local one is.
    """
    primary = None
    if hf_token:
        try:
            from langchain_huggingface import HuggingFaceEndpointEmbeddings

            candidate = HuggingFaceEndpointEmbeddings(
                model="sentence-transformers/all-MiniLM-L6-v2",
                huggingfacehub_api_token=hf_token,
            )
            # Prove it works before relying on it, so a dead token is
            # discovered at startup rather than on the first question.
            candidate.embed_query("connection test")
            primary = candidate
            print("[Embeddings] Using the hosted Hugging Face encoder.")
        except Exception as exc:
            print(f"[Embeddings] Hosted encoder unavailable ({exc}); using the local encoder.")

    if primary is None:
        print("[Embeddings] Using the local encoder. Schema retrieval works on keyword match.")

    return FallbackEmbeddings(primary, size)
