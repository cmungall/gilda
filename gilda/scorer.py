from .process import replace_dashes, replace_whitespace, normalize, \
    get_capitalization_pattern


class Match(object):
    """Class representing a match between a query and a reference string"""
    def __init__(self, query, ref, exact=None, space_mismatch=None,
                 dash_mismatches=None, cap_combos=None):
        self.query = query
        self.ref = ref
        self.exact = exact
        self.space_mismatch = space_mismatch
        self.dash_mismatches = dash_mismatches
        self.cap_combos = cap_combos

    def __str__(self):
        return 'Match(%s)' % (','.join(['%s=%s' % (k, v) for k, v in
                                        self.__dict__.items()]))

    def _query_cases(self):
        return {c[0] for c in self.cap_combos}

    def _ref_cases(self):
        return {c[1] for c in self.cap_combos}

    def score_short_abbr(self):
        if len(self.ref) <= 3 and \
                (('all_caps', 'all_lower') in self.cap_combos or
                 ('all_lower', 'all_caps') in self.cap_combos):
            return 0
        else:
            return 1

    def score_mixed(self):
        if ('mixed', 'mixed') in self.cap_combos:
            return 0
        elif ('mixed' in self._query_cases()) or \
                ('mixed' in self._ref_cases()):
            return 1
        else:
            return 2

    def score_exact(self):
        return 1 if self.exact is True else 0

    def score_acic(self):
        if self.exact is True and not self.cap_combos:
            return 2
        elif set(self.cap_combos) == {('sentence_initial', 'all_lower')}:
            return 2
        if self.exact is True and set(self.cap_combos) <= \
                {('all_caps', 'sentence_initial_cap'),
                 ('sentence_initial_cap', 'all_caps')}:
            return 1
        else:
            return 0

    def score_combo(self):
        qc = self._query_cases()
        rc = self._ref_cases()
        query_combo = 4 - len(qc)
        ref_combo = 4 - len(rc)
        if 'single_cap_letter' in qc and \
                ('all_caps' in qc or 'initial_cap' in qc):
            query_combo += 1
        if 'single_cap_letter' in rc and \
                ('all_caps' in rc or 'initial_cap' in rc):
            ref_combo += 1
        if 'sentence_initial_cap' in qc and \
                (len(qc) == 1 and
                 ('sentence_initial_cap', 'all_lower') in self.cap_combos) \
                or \
                 {'single_cap_letter', 'initial_cap', 'all_lower'} & qc:
            query_combo += 1
        combo = max(query_combo, ref_combo)
        return combo

    def score_dash(self):
        return 2 - len(self.dash_mismatches)


def generate_match(query, ref, beginning_of_sentence):
    """Return a match data structure based on comparing a query to a ref str.

    Parameters
    ----------
    query : str
        The string to be compared against a reference string.
    ref : str
        The reference string against which the incoming query string is
        compared.
    beginning_of_sentence : bool
        True if the query_str appears at the beginning of a sentence, relevant
        for how capitalization is evaluated.

    Returns
    -------
    Match
        A Match object characterizing the match between the two strings.
    """
    # First of all, this function assumes that both the query and the ref have
    # been normalized and so if that is not the case, we raise an error
    if normalize(query) != normalize(ref):
        raise ValueError('Normalized query "%s" does not match normalized'
                         ' reference "%s"' % (query, ref))

    # Pre-process both strings first by replacing multiple white spaces
    # with a single ASCII space, and all kinds of dashes with a single
    # ASCII dash.
    query = replace_dashes(replace_whitespace(query))
    ref = replace_dashes(replace_whitespace(ref))

    # If we have an exact match at this point then we can return immediately
    if not beginning_of_sentence and query == ref:
        return Match(query, ref, exact=True)

    query_suffix = query
    ref_suffix = ref
    query_pieces = ['']
    ref_pieces = ['']
    dash_mismatches = set()
    while query_suffix and ref_suffix:
        # Deal with spaces first
        qs = (query_suffix[0] == ' ')
        rs = (ref_suffix[0] == ' ')
        # If both have spaces, we start new pieces and skip the spaces
        if qs and rs:
            query_suffix = query_suffix[1:]
            ref_suffix = ref_suffix[1:]
            query_pieces.append('')
            ref_pieces.append('')
        # This means that there is a space inconsistency which we don't allow
        # and return immediately
        elif qs and not rs or rs and not qs:
            return Match(query, ref, space_mismatch=True)

        # We next deal with dashes
        qd = (query_suffix[0] == '-')
        rd = (ref_suffix[0] == '-')
        # If both are dashes, we skip them
        if qd and rd:
            query_suffix = query_suffix[1:]
            ref_suffix = ref_suffix[1:]
            query_pieces.append('')
            ref_pieces.append('')
        # If there is a mismatch, we introduce new pieces but only skip the one
        # dash and record the inconsistency
        elif qd and not rd:
            dash_mismatches.add('query')
            query_suffix = query_suffix[1:]
            query_pieces.append('')
            ref_pieces.append('')
        elif not qd and rd:
            dash_mismatches.add('ref')
            ref_suffix = ref_suffix[1:]
            query_pieces.append('')
            ref_pieces.append('')
        # Otherwise both strings start with a non space/dash character that we
        # add to the latest piece
        else:
            query_pieces[-1] += query_suffix[0]
            ref_pieces[-1] += ref_suffix[0]
            ref_suffix = ref_suffix[1:]
            query_suffix = query_suffix[1:]

    # Now that we have the final pieces in place, we can count the matches and
    # capitalization relationships
    combinations = []
    first = True
    exact = False
    for qp, rp in zip(query_pieces, ref_pieces):
        first_bos = first and beginning_of_sentence
        first = False
        if qp == rp and not first_bos:
            exact = True
        else:
            qcp = get_capitalization_pattern(qp, first_bos)
            rcp = get_capitalization_pattern(rp, False)
            if qcp == rcp and qp == rp:
                exact = True
            else:
                combinations.append((qcp, rcp))
    return Match(query, ref, dash_mismatches=dash_mismatches,
                 exact=exact, cap_combos=combinations)


def score_string_match(match):
    """Return a score between 0 and 1 for the goodness of a match.

    This score is purely based on the relationship of the two strings and
    does not take the status of the reference into account.

    Parameters
    ----------
    match : gilda.scorer.Match
        The Match object characterizing the relationship of the query and
        reference strings.

    Returns
    -------
    float
        A match score between 0 and 1.
    """
    terms = [
        (match.get_short_abbr, 2),
        (match.get_mixed, 3),
        (match.get_exact, 2),
        (match.get_acic, 3),
        (match.get_combo, 5),
        (match.get_dash, 3)
    ]
    score = 0
    norm = 1
    for fun, coeff in terms:
        score = coeff * score + fun()
        norm *= coeff
    score /= (norm -1)
    return score



