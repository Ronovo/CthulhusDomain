from signing import Signer

signer = Signer("test")


def test_a_signed_value_comes_back_without_its_signature():
    assert signer.verify(signer.sign({"sanity": 5})) == {"sanity": 5}


def test_a_tuple_is_signed_like_the_list_the_browser_sends_back():
    import json
    signed = signer.sign({"devours": [("a" * 16, 1, "quick")]})
    assert signer.verify(json.loads(json.dumps(signed))) is not None


def test_data_that_cannot_be_signed_counts_as_edited():
    assert signer.verify({"signature": "0" * 64, "worlds": {1, 2}}) is None


def test_deeply_nested_data_counts_as_edited():
    nested = []
    for _ in range(5_000):
        nested = [nested]
    assert signer.verify({"signature": "0" * 64, "worlds": nested}) is None
