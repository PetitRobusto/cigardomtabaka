class DividendActionError(Exception):
    """分红动作的稳定错误码，供 API 边界序列化。"""

    def __init__(self, code: str, details: dict[str, object] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or {}
