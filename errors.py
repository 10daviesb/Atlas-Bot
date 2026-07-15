class ExtensionDisabledError(Exception):
    def __init__(self, extension: str) -> None:
        super().__init__(f"Extension '{extension}' is disabled.")
        self.extension = extension


class CommandDisabledError(Exception):
    def __init__(self, command: str) -> None:
        super().__init__(f"Command '{command}' is disabled.")
        self.command = command


class MissingCommandRoleError(Exception):
    def __init__(self, role_id: int) -> None:
        super().__init__(f"Missing role {role_id} to use this command.")
        self.role_id = role_id
