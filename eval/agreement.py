"""Agreement statistics, reused from the Project 1 harness (harness/agreement.py).

Written out by hand so the whole team can explain them. Here the scale is the judge's
correctness grade (0 / 0.5 / 1); `to_cat` maps it onto P1's ordered 1-2-3 categories so
the same quadratic weighted kappa applies unchanged.
"""

CATS = [1, 2, 3]


def to_cat(grade: float) -> int:
    """0 -> 1, 0.5 -> 2, 1 -> 3."""
    return {0.0: 1, 0.5: 2, 1.0: 3}[float(grade)]


def confusion(pairs):
    """3x3 count matrix. pairs is a list of (grade_x, grade_y)."""
    m = {a: {b: 0 for b in CATS} for a in CATS}
    for a, b in pairs:
        m[a][b] += 1
    return m


def exact_pct(pairs):
    """Both raters picked the same grade."""
    return 100 * sum(a == b for a, b in pairs) / len(pairs) if pairs else 0.0


def quadratic_weighted_kappa(pairs):
    """Cohen's kappa with quadratic weights.

    The scale is ordered, so a two-step disagreement (correct vs wrong) hurts more than
    a one-step one (correct vs partly correct). 1.0 = perfect, 0.0 = chance, < 0 = worse.
    """
    n = len(pairs)
    if n == 0:
        return float("nan")

    obs = confusion(pairs)
    row = {c: sum(obs[c].values()) for c in CATS}
    col = {c: sum(obs[a][c] for a in CATS) for c in CATS}

    k = len(CATS) - 1
    num = den = 0.0
    for a in CATS:
        for b in CATS:
            w = ((a - b) ** 2) / (k**2)
            expected = row[a] * col[b] / n
            num += w * obs[a][b]
            den += w * expected
    if den == 0:  # both raters used a single grade only
        return float("nan")
    return 1 - num / den


def matrix_rows(pairs):
    """Confusion matrix as printable rows of (count, percent-of-total)."""
    obs = confusion(pairs)
    n = len(pairs) or 1
    return [[(obs[a][b], 100 * obs[a][b] / n) for b in CATS] for a in CATS]
