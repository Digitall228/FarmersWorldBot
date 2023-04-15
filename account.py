class Account:

    def __init__(self, account_name, private_keys, public_keys,
                 tables=[['tools', 2], ['animals', 2], ['crops', 2], ['breedings', 2], ['buildings', 2], ['mbs', 2]]):
        self.private_keys = private_keys
        self.public_keys = public_keys
        self.account_name = account_name
        self.tables = tables
        self.items = []
        self.key = None
