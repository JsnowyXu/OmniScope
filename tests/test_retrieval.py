from omniscope.retrieval import reciprocal_rank_fusion


def test_rrf_rewards_agreement_between_retrievers():
    fused = reciprocal_rank_fusion([(1, 0.9), (2, 0.8)], [(2, 0.7), (3, 0.6)], rrf_k=60)
    assert fused[2] > fused[1]
    assert fused[2] > fused[3]


def test_rrf_is_deterministic():
    inputs = ([(1, 1.0)], [(2, 1.0)])
    assert reciprocal_rank_fusion(*inputs) == reciprocal_rank_fusion(*inputs)
