"""Erros do cliente Bling. As mensagens nunca carregam tokens, códigos ou segredos."""


class BlingError(Exception):
    """Base dos erros da integração Bling."""


class BlingNotConnectedError(BlingError):
    def __init__(self, message: str = "Bling não conectado.") -> None:
        super().__init__(message)


class BlingReconnectRequiredError(BlingError):
    def __init__(self, message: str = "Reconexão com o Bling necessária.") -> None:
        super().__init__(message)


class BlingRateLimitedError(BlingError):
    def __init__(self, message: str = "Limite de requisições do Bling excedido.") -> None:
        super().__init__(message)


class BlingUnavailableError(BlingError):
    def __init__(self, message: str = "Bling indisponível.") -> None:
        super().__init__(message)


class BlingRejectedError(BlingError):
    """Resposta 4xx definitiva; ``error_type``/``message`` vêm do corpo de erro do Bling."""

    def __init__(self, status: int, error_type: str | None = None, message: str = "") -> None:
        self.status = status
        self.error_type = error_type
        self.message = message
        super().__init__(f"Bling recusou a requisição ({status}, {error_type or 'sem tipo'}).")
