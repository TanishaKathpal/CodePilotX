"""Bank account model."""
from .errors import InsufficientFunds


class Account:
    def __init__(self, owner, balance=0):
        self.owner = owner
        self.balance = balance

    def deposit(self, amount):
        if amount <= 0:
            raise ValueError("deposit must be positive")
        self.balance += amount

    def withdraw(self, amount):
        if amount <= 0:
            raise ValueError("withdrawal must be positive")
        if amount >= self.balance:
            raise InsufficientFunds(f"balance {self.balance} is too low for {amount}")
        self.balance -= amount

    def transfer(self, other, amount):
        """Move money to another account."""
        self.withdraw(amount)
        other.deposit(amount)
