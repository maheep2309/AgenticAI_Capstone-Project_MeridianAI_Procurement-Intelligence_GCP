"""Write init_embeddings.json: one dummy 768-dim vector (id init_0001).

Vertex AI Vector Search needs at least one datapoint when the index is created.
The deploy workflow uploads this file, creates the index, then removes init_0001.
"""
import json
import random

DIMENSIONS = 768  # must match "dimensions" in .github/workflows/deploy.yml and settings.embedding_dimensions

embedding = [random.gauss(0, 1) for _ in range(DIMENSIONS)]

with open("init_embeddings.json", "w") as f:
    json.dump({"id": "init_0001", "embedding": embedding}, f)

print(f"Wrote init_embeddings.json ({DIMENSIONS} dims)")
