from engine.core.retrieval.embed import embed_signature, cosine


def test_embed_signature_stability_and_similarity():
    a = embed_signature({"text": "Sign In"}, dim=32)
    b = embed_signature({"text": "sign in"}, dim=32)
    c = embed_signature({"text": "Checkout"}, dim=32)
    # Same tokens except case -> high cosine similarity
    sim_ab = cosine(a, b)
    sim_ac = cosine(a, c)
    assert sim_ab > 0.8
    assert sim_ac < sim_ab
