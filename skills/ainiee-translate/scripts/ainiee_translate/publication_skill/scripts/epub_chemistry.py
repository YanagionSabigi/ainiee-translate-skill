"""Conservative typography for source-reviewed chemical text.

This is a bounded formula parser, not a detector for chemistry in ordinary prose.
Callers must opt in only after reviewing the text against its source. Unsupported
or ambiguous tokens are preserved whole; use a caret for explicit charge or
isotope information (``SO4^2-``, ``O2^-``, ``^14C``).
"""
import re


SUBSCRIPT_TRANSLATION = str.maketrans('0123456789+-−', '₀₁₂₃₄₅₆₇₈₉₊₋₋')
SUPERSCRIPT_TRANSLATION = str.maketrans('0123456789+-−', '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁻')
_ELEMENTS = set('H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og'.split())
_SUB_DIGITS = '₀₁₂₃₄₅₆₇₈₉'
_SUP_DIGITS = '⁰¹²³⁴⁵⁶⁷⁸⁹'
# Keep broad candidates whole so malformed or decimal formulas are not partly
# rewritten. A plus directly followed by another formula is a reaction separator.
_TOKEN = re.compile(
    r'(?<![\w.^₀-₉⁰¹²³⁴⁵⁶⁷⁸⁹])'
    r'[A-Za-z0-9^().\[\]·₀-₉⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+'
    r'(?:[+\-−](?![A-Za-z0-9(\[]))?'
    r'(?![\w^])'
)


def _formula(formula: str) -> str | None:
    """Parse balanced element/group syntax without guessing chemical validity."""
    output = []
    stack = []
    atoms = 0
    previous_unit = False
    position = 0
    while position < len(formula):
        char = formula[position]
        if char in '([':
            stack.append((char, atoms))
            output.append(char)
            previous_unit = False
            position += 1
        elif char in ')]':
            if not stack or stack[-1][0] != {')': '(', ']': '['}[char]:
                return None
            _, start_atoms = stack.pop()
            if atoms == start_atoms:
                return None
            output.append(char)
            previous_unit = True
            position += 1
        elif char in '0123456789' + _SUB_DIGITS:
            if not previous_unit:
                return None
            end = position + 1
            while end < len(formula) and formula[end] in '0123456789' + _SUB_DIGITS:
                end += 1
            count = formula[position:end]
            # A zero or a leading zero is not an atomic count in this grammar.
            if count[0] in '0₀':
                return None
            output.append(count.translate(SUBSCRIPT_TRANSLATION))
            previous_unit = False
            position = end
        else:
            isotope = re.match(r'\^([1-9][0-9]*)|([' + _SUP_DIGITS + r']+)', formula[position:])
            if isotope:
                end = position + len(isotope.group())
                if end >= len(formula) or not formula[end].isupper():
                    return None
                output.append((isotope.group(1) or isotope.group(2)).translate(SUPERSCRIPT_TRANSLATION))
                position = end
            element = re.match(r'[A-Z][a-z]?', formula[position:])
            if not element or element.group() not in _ELEMENTS:
                return None
            output.append(element.group())
            position += len(element.group())
            atoms += 1
            previous_unit = True
    return ''.join(output) if atoms and not stack else None


def _token(match: re.Match) -> str:
    original = match.group()
    # Sentence punctuation is outside the formula, but a period inside it is
    # retained for validation (Fe0.5O must not become Fe₀.5O).
    body = original.rstrip('.')
    punctuation = original[len(body):]
    charge = ''
    explicit = re.search(r'\^([1-9][0-9]*)?([+\-−])$', body)
    existing = re.search('[' + _SUP_DIGITS + ']*[⁺⁻]$', body)
    if explicit:
        charge = ((explicit.group(1) or '') + explicit.group(2)).translate(SUPERSCRIPT_TRANSLATION)
        body = body[:explicit.start()]
    elif existing:
        charge = existing.group()
        body = body[:existing.start()]
    elif body.endswith(('+', '-', '−')):
        sign = body[-1].translate(SUPERSCRIPT_TRANSLATION)
        body = body[:-1]
        # A monatomic ion or bracketed complex spells out its charge magnitude.
        magnitude = re.fullmatch(r'([A-Z][a-z]?|.*\])([1-9][0-9]*)', body)
        if magnitude:
            body = magnitude.group(1)
            charge = magnitude.group(2).translate(SUPERSCRIPT_TRANSLATION) + sign
        else:
            # SO42- could mean SO4^2- or SO42^-; preserve the ambiguous token.
            if re.search(r'[0-9]{2,}$', body) or re.search(r'\)[0-9]+$', body):
                return original
            charge = sign
    parts = []
    for component in body.split('·'):
        coefficient = re.match(r'[0-9]+(?:\.[0-9]+)?', component)
        prefix = coefficient.group() if coefficient else ''
        parsed = _formula(component[len(prefix):])
        if parsed is None:
            return original
        parts.append(prefix + parsed)
    return '·'.join(parts) + charge + punctuation


def format_chemical_text(text: str) -> str:
    """Format annotated chemistry, leaving unsupported tokens unchanged.

    Leading numbers and hydrate multipliers stay baseline. ASCII atomic counts
    become subscripts, explicit charges/isotopes become superscripts. Bare
    monatomic ions (Fe3+) and square-bracket complex charges are supported; other
    ambiguous multi-digit terminal counts with a sign require a caret. Existing
    Unicode subscripts and superscripts are preserved. Reversible arrows use ⇆.
    """
    text = text.replace('<=>', '⇆').replace('<->', '⇆').replace('⇌', '⇆').replace('->', '→')
    return _TOKEN.sub(_token, text)
