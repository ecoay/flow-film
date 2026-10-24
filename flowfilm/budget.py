"""Credit parsing and the spend guard. Pure functions, so they are unit-tested offline."""
import re

_NUM = re.compile(r"(\d[\d,]*)\s*(?:AI\s+)?credits?", re.I)


def parse_credits(text):
    m = _NUM.search(text or "")
    if not m:
        m = re.search(r"(\d[\d,]*)", text or "")
    return int(m.group(1).replace(",", "")) if m else None


def parse_balance(*texts):
    """Balance must come from an explicit 'N (AI) credits' label; never fall back to a stray digit."""
    for t in texts:
        m = _NUM.search(t or "")
        if m:
            return int(m.group(1).replace(",", ""))
    return None


class OverBudget(Exception):
    pass


def guard(quote, limit, balance=None):
    """Raise OverBudget unless the quoted price is known and fits both the per-shot limit and the balance."""
    if quote is None:
        raise OverBudget("Flow showed no price for this shot, so nothing was generated (refusing to spend blind).")
    if quote > limit:
        raise OverBudget(f"Flow quotes {quote} credits, over your limit of {limit}. Nothing was generated.")
    if balance is not None and quote > balance:
        raise OverBudget(f"Flow quotes {quote} credits but only {balance} are left. Nothing was generated.")
    return quote


def plan_cost(shots, per_shot):
    return len(shots) * per_shot
