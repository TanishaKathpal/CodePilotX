import pytest
from bank.account import Account
from bank.errors import InsufficientFunds


def test_withdraw_exact_balance():
    account = Account("Alice", balance=50)
    account.withdraw(50)
    assert account.balance == 0


def test_withdraw_exceeding_balance():
    account = Account("Alice", balance=50)
    with pytest.raises(InsufficientFunds):
        account.withdraw(51)


def test_withdraw_partial_balance():
    account = Account("Alice", balance=50)
    account.withdraw(20)
    assert account.balance == 30
