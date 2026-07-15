import lightbulb


class ExtensionDisabledError(lightbulb.CheckFailure):
    def __init__(self, extension: str) -> None:
        super().__init__()
        self.extension = extension


class CommandDisabledError(lightbulb.CheckFailure):
    def __init__(self, command: str) -> None:
        super().__init__()
        self.command = command


class MissingCommandRoleError(lightbulb.CheckFailure):
    def __init__(self, role_id: int) -> None:
        super().__init__()
        self.role_id = role_id
