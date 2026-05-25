import pytest
from parameterized import param

from generic_grader.utils.options import Options, options_to_params


def test_single_options_to_params():
    # Arrange
    single_option = Options()

    # Act
    the_params = options_to_params(single_option)

    # Assert
    assert the_params == [param(single_option)]


def test_multiple_options_to_params():
    # Arrange
    sequence_options = (
        Options(),
        Options(),
    )

    # Act
    the_params = options_to_params(sequence_options)

    # Assert
    assert the_params == [param(o) for o in sequence_options]


def test_utils_options():
    """Test that Options can be instantiated."""
    assert Options()


typecheck_options = [
    {
        "options": {"init": ""},
        "error": "`init` must be of type <class 'function'> or <class 'NoneType'>. Got <class 'str'> instead.",
    },
    {
        "options": {"patches": {}},
        "error": "`patches` must be of type <class 'list'>. Got <class 'dict'> instead.",
    },
    {
        "options": {"entries": ""},
        "error": "`entries` must be of type <class 'tuple'>. Got <class 'str'> instead.",
    },
    {
        "options": {"weight": "0"},
        "error": "`weight` must be of type int | float. Got <class 'str'> instead.",
    },
    {
        "options": {"mode": "unknown"},
        "error": "`mode` must be one of 'exactly', 'less than', 'more than', or 'approximately'.",
    },
]


@pytest.mark.parametrize("case", typecheck_options)
def test_typecheck_options(case):
    """Test that the runtime error is raised."""
    with pytest.raises(ValueError) as exc_info:
        Options(**case["options"])
    assert str(exc_info.value) == case["error"]


# Valid init functions (should not raise)
valid_init_cases = [
    lambda test, options: None,  # exactly 2 params
    lambda test, options, extra=None: None,  # 2 required + 1 optional
    lambda *args: None,  # variadic
    lambda test, *args: None,  # 1 + variadic
]


@pytest.mark.parametrize("init", valid_init_cases)
def test_valid_init_signature(init):
    """Test that valid init functions are accepted."""
    Options(init=init)  # should not raise


# Invalid init functions (should raise ValueError)
invalid_init_cases = [
    {
        "init": lambda: None,
        "error": "`init` must accept 2 positional arguments (test, options), but accepts 0.",
    },
    {
        "init": lambda x: None,
        "error": "`init` must accept 2 positional arguments (test, options), but accepts 1.",
    },
]


@pytest.mark.parametrize("case", invalid_init_cases)
def test_invalid_init_signature(case):
    """Test that init functions with wrong signature are rejected."""
    with pytest.raises(ValueError) as exc_info:
        Options(init=case["init"])
    assert str(exc_info.value) == case["error"]


duplicate_file_names = [
    {
        "options": {"filenames": ("a", "a")},
        "error": "Duplicate entries in filenames.",
    },
    {
        "options": {"required_files": ("a", "a")},
        "error": "Duplicate entries in required_files.",
    },
    {
        "options": {"ignored_files": ("a", "a")},
        "error": "Duplicate entries in ignored_files.",
    },
]


@pytest.mark.parametrize("case", duplicate_file_names)
def test_duplicate_file_names(case):
    """Test that the runtime error is raised."""
    with pytest.raises(ValueError) as exc_info:
        Options(**case["options"])
    assert str(exc_info.value) == case["error"]


# ---------------------------------------------------------------------------
# Sandbox opt-in (Layer 3)
# ---------------------------------------------------------------------------


def test_use_sandbox_defaults_to_false():
    assert Options().use_sandbox is False
    assert Options().patch_specs == ()


def test_use_sandbox_alone_is_accepted():
    """Opting into the sandbox with no patches is fine."""
    Options(use_sandbox=True)


def test_use_sandbox_with_patch_specs_is_accepted():
    """`patch_specs` is the sandbox-safe way to ship patches."""
    from generic_grader.sandbox.patch_specs import make_noop_patch_spec

    Options(
        use_sandbox=True,
        patch_specs=(make_noop_patch_spec("m.f"),),
    )


def test_use_sandbox_rejects_legacy_patches_without_specs():
    """Live callables in `patches` cannot cross the sandbox boundary."""
    with pytest.raises(ValueError, match="patch_specs"):
        Options(
            use_sandbox=True,
            patches=[{"args": ["m.f", lambda *a, **k: None]}],
        )


def test_legacy_patches_allowed_when_use_sandbox_false():
    """Layer 1 (in-process) is unaffected by the new check."""
    Options(patches=[{"args": ["m.f", lambda *a, **k: None]}])


# ---------------------------------------------------------------------------
# ref_dir (Layer 3)
# ---------------------------------------------------------------------------


def test_ref_dir_defaults_to_tests():
    """`ref_dir` defaults to `./tests` so the recommended layout works
    out of the box."""
    assert Options().ref_dir == "./tests"


def test_ref_dir_can_be_overridden():
    """`ref_dir` is a writable string field."""
    assert Options(ref_dir="./graders/foo").ref_dir == "./graders/foo"


def test_ref_dir_must_be_a_string():
    """Type validation rejects non-string values."""
    with pytest.raises(ValueError, match="ref_dir"):
        Options(ref_dir=123)
