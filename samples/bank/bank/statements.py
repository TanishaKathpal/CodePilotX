"""Plain-text statements."""


def render_statement(account, transactions):
    lines = [f"Statement for {account.owner}"]
    for label, amount in transactions:
        lines.append(f"  {label:<12}{amount:>10.2f}")
    lines.append(f"  {'Balance':<12}{account.balance:>10.2f}")
    return "\n".join(lines)
