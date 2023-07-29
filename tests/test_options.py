from generic_grader.utils.options import Options


def test_defaults():
    o = Options()

    assert o.init is None
    assert o.ref_module == "tests.reference"
    assert o.sub_module == ""
    assert o.required_files == ()
    assert o.ignored_files == ()
    assert o.hint == ""
    assert o.patches == ""
