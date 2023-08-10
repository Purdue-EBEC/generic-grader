import tokenize
from token import COMMENT, ENCODING, NEWLINE, NL


def get_tokens(test, file_name):
    """Return a list of the tokens in program `file_name`."""

    with tokenize.open(file_name) as fo:
        fail_msg = None
        try:
            tokens = list(tokenize.generate_tokens(fo.readline))
        except tokenize.TokenError as e:
            fail_msg = (
                f"Error while parsing `{file_name}`. "
                + f'The error was "{e.__class__.__name__}: {e}".'
            )
        # Fail outside of the except block
        # so that AssertionError(s) will be handled properly.
        if fail_msg:
            test.fail(fail_msg)
    return tokens


def get_comments(test, file_name):
    """Return the comments in program `file_name`.

    The comments are split into a list of header comments and a list of
    body comments.
    """

    header_comments, body_comments, once = [], [], True
    comments = header_comments
    for t in get_tokens(test, file_name):
        if t.type == COMMENT:
            comments.append(t.string)
        elif once and t.type not in (ENCODING, NEWLINE, NL):
            once = False  # Only run this block once
            comments = body_comments  # Switch to which list we append

    return header_comments, body_comments
