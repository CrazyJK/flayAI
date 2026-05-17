"""M0 smoke test: bge-m3 embedding shape check"""

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("BAAI/bge-m3")
vecs = model.encode(["test sentence one", "test sentence two"])
assert vecs.shape == (2, 1024), f"Unexpected shape: {vecs.shape}"
print(f"OK shape={vecs.shape}")
