import unittest

from bank import Account, InsufficientFunds


class AccountTests(unittest.TestCase):
    def test_deposit(self):
        acc = Account("ana", 10)
        acc.deposit(5)
        self.assertEqual(acc.balance, 15)

    def test_partial_withdraw(self):
        acc = Account("ana", 100)
        acc.withdraw(30)
        self.assertEqual(acc.balance, 70)

    def test_overdraft_rejected(self):
        acc = Account("ana", 10)
        with self.assertRaises(InsufficientFunds):
            acc.withdraw(50)

    def test_negative_deposit_rejected(self):
        with self.assertRaises(ValueError):
            Account("ana").deposit(-1)


if __name__ == "__main__":
    unittest.main()
